"""Retention enforcement, low-water mark pruning, and storage estimation engine."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from vizenlink_nvr.db.models import RecordingSettings, Segment
from vizenlink_nvr.services.storage import DEFAULT_RECORDING_BITRATE_KBPS, DEFAULT_RESERVE_BYTES
from vizenlink_nvr.timeutil import utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

HYSTERESIS_BUFFER_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


def _safe_unlink(p: Path) -> bool:
    """Safely unlink a file synchronously."""
    try:
        if p.exists():
            p.unlink()
            return True
    except Exception as exc:
        logger.warning("Could not delete file %s: %s", p, exc)
    return False


def _resolve_existing_parent(storage_path: Path) -> Path:
    """Resolve nearest existing parent synchronously."""
    resolved = storage_path.resolve()
    while not resolved.exists() and resolved != resolved.parent:
        resolved = resolved.parent
    return resolved


def _cleanup_camera_dirs(storage_path: Path, camera_serial: str) -> None:
    """Remove empty or purged camera directories synchronously."""
    cam_dir_patterns = [
        storage_path / camera_serial,
        storage_path / camera_serial.lower(),
        storage_path / "cam" / camera_serial.lower(),
        storage_path / "cam" / camera_serial,
    ]
    for d in cam_dir_patterns:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)



@dataclass(frozen=True)
class PruneReport:
    """Summary of camera retention pruning."""

    camera_serial: str
    deleted_files: list[str]
    freed_bytes: int


@dataclass(frozen=True)
class LowWaterReport:
    """Summary of disk low-water mark pruning run."""

    freed_bytes: int
    remaining_free: int
    triggered: bool
    deleted_count: int


@dataclass(frozen=True)
class RetentionEstimate:
    """Storage footprint and retention duration projection for a camera."""

    camera_serial: str
    gb_per_day: float
    configured_days: int | None
    configured_max_gb: int | None
    effective_days: float | None


async def enforce_camera_retention(
    session: AsyncSession,
    camera_serial: str,
    now: datetime | None = None,
) -> PruneReport:
    """Enforce per-camera retention policies (days and max GB cap), deleting oldest unprotected first."""
    if now is None:
        now = utc_now()

    # Load camera recording settings
    set_stmt = select(RecordingSettings).where(RecordingSettings.camera_serial == camera_serial)
    set_res = await session.execute(set_stmt)
    settings = set_res.scalar_one_or_none()

    if settings is None or (settings.retention_days is None and settings.retention_max_gb is None):
        return PruneReport(camera_serial=camera_serial, deleted_files=[], freed_bytes=0)

    deleted_files: list[str] = []
    freed_bytes = 0

    # 1. Time-based retention (retention_days)
    if settings.retention_days is not None:
        cutoff = now - timedelta(days=settings.retention_days)
        # Query oldest unprotected segments where end_time < cutoff
        stmt = (
            select(Segment)
            .where(
                Segment.camera_serial == camera_serial,
                Segment.is_protected.is_(False),
                Segment.end_time < cutoff,
            )
            .order_by(Segment.start_time.asc())
        )
        res = await session.execute(stmt)
        expired_segments = res.scalars().all()

        for seg in expired_segments:
            _safe_unlink(Path(seg.file_path))
            deleted_files.append(seg.file_path)
            freed_bytes += seg.file_size_bytes
            await session.delete(seg)

        if expired_segments:
            await session.commit()

    # 2. Size-based retention cap (retention_max_gb)
    if settings.retention_max_gb is not None:
        max_bytes = settings.retention_max_gb * 1024 * 1024 * 1024

        # Calculate current total usage for camera
        sum_stmt = select(func.coalesce(func.sum(Segment.file_size_bytes), 0)).where(
            Segment.camera_serial == camera_serial,
            Segment.status == "active",
        )
        total_used = (await session.execute(sum_stmt)).scalar_one()

        if total_used > max_bytes:
            bytes_to_free = total_used - max_bytes
            stmt = (
                select(Segment)
                .where(
                    Segment.camera_serial == camera_serial,
                    Segment.is_protected.is_(False),
                )
                .order_by(Segment.start_time.asc())
            )
            res = await session.execute(stmt)
            oldest_segments = res.scalars().all()

            for seg in oldest_segments:
                if bytes_to_free <= 0:
                    break
                _safe_unlink(Path(seg.file_path))
                deleted_files.append(seg.file_path)
                freed_bytes += seg.file_size_bytes
                bytes_to_free -= seg.file_size_bytes
                await session.delete(seg)

            await session.commit()

    return PruneReport(
        camera_serial=camera_serial,
        deleted_files=deleted_files,
        freed_bytes=freed_bytes,
    )


async def enforce_disk_low_water_mark(
    session: AsyncSession,
    storage_path: Path,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> LowWaterReport:
    """Proactively purge oldest unprotected segments across cameras if free space drops below reserve."""
    try:
        resolved = _resolve_existing_parent(storage_path)
        usage = shutil.disk_usage(resolved)
    except Exception as exc:
        logger.error("Could not read disk usage for %s: %s", storage_path, exc)
        return LowWaterReport(freed_bytes=0, remaining_free=0, triggered=False, deleted_count=0)

    # Dynamic reserve: 10 GB or 5% of total disk capacity, whichever is larger (D-33)
    dynamic_reserve = max(reserve_bytes, int(usage.total * 0.05))
    target_free = dynamic_reserve + HYSTERESIS_BUFFER_BYTES

    if usage.free >= dynamic_reserve:
        return LowWaterReport(
            freed_bytes=0,
            remaining_free=usage.free,
            triggered=False,
            deleted_count=0,
        )

    bytes_needed = target_free - usage.free
    total_freed = 0
    deleted_count = 0

    # Query oldest unprotected segments across all cameras
    stmt = (
        select(Segment)
        .where(
            Segment.is_protected.is_(False),
            Segment.status != "missing",
        )
        .order_by(Segment.start_time.asc())
    )
    res = await session.execute(stmt)
    oldest_segments = res.scalars().all()

    for seg in oldest_segments:
        if bytes_needed <= 0:
            break
        _safe_unlink(Path(seg.file_path))
        freed = seg.file_size_bytes
        total_freed += freed
        bytes_needed -= freed
        deleted_count += 1
        await session.delete(seg)

    await session.commit()
    return LowWaterReport(
        freed_bytes=total_freed,
        remaining_free=usage.free + total_freed,
        triggered=True,
        deleted_count=deleted_count,
    )


async def estimate_retention(
    session: AsyncSession,
    camera_serial: str,
    avg_bitrate_kbps: int = DEFAULT_RECORDING_BITRATE_KBPS,
) -> RetentionEstimate:
    """Estimate daily storage footprint and retention span for camera (REC-06)."""
    set_stmt = select(RecordingSettings).where(RecordingSettings.camera_serial == camera_serial)
    set_res = await session.execute(set_stmt)
    settings = set_res.scalar_one_or_none()

    bytes_per_sec = (avg_bitrate_kbps * 1000) / 8
    bytes_per_day = bytes_per_sec * 86400
    gb_per_day = round(bytes_per_day / (1024 * 1024 * 1024), 2)

    configured_days = settings.retention_days if settings else None
    configured_max_gb = settings.retention_max_gb if settings else None

    effective_days: float | None = None
    if configured_max_gb is not None and gb_per_day > 0:
        days_from_gb = round(configured_max_gb / gb_per_day, 1)
        if configured_days is not None:
            effective_days = min(float(configured_days), days_from_gb)
        else:
            effective_days = days_from_gb
    elif configured_days is not None:
        effective_days = float(configured_days)

    return RetentionEstimate(
        camera_serial=camera_serial,
        gb_per_day=gb_per_day,
        configured_days=configured_days,
        configured_max_gb=configured_max_gb,
        effective_days=effective_days,
    )


async def delete_camera_recordings(
    session: AsyncSession,
    camera_serial: str,
    storage_path: Path,
) -> int:
    """Purge all segment files and database index records for a removed camera (CAM-09)."""
    stmt = select(Segment).where(Segment.camera_serial == camera_serial)
    res = await session.execute(stmt)
    segments = res.scalars().all()

    deleted_count = 0
    for seg in segments:
        if _safe_unlink(Path(seg.file_path)):
            deleted_count += 1
        await session.delete(seg)

    _cleanup_camera_dirs(storage_path, camera_serial)
    await session.commit()
    return deleted_count
