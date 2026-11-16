"""Two-source recording segment indexer: real-time hook processing and disk scanner."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from vizenlink_nvr.db.models import Camera, Segment
from vizenlink_nvr.timeutil import UTC, default_site_zone_name, utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Matches YYYY-MM-DD followed by T or _ followed by HH-MM-SS or HH:MM:SS
DATETIME_PATTERN = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T_](\d{2})[-:](\d{2})[-:](\d{2})"
)

MIN_VALID_SEGMENT_BYTES = 1024


@dataclass(frozen=True)
class SegmentMetadata:
    """Parsed metadata for a recorded fMP4 segment file."""

    camera_serial: str
    stream_type: str
    file_path: Path
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    file_size_bytes: int
    status: str


@dataclass(frozen=True)
class ScanReport:
    """Summary of reconciliation scanner run."""

    adopted: int
    missing_marked: int
    truncated_marked: int
    total_valid: int


def parse_mtx_path(mtx_path: str) -> tuple[str, str]:
    """Extract camera serial and stream role from MTX_PATH e.g. 'cam/vzl-cam-001/main'."""
    clean = mtx_path.strip().strip("/")
    if not clean:
        return "UNKNOWN", "main"
    parts = clean.split("/")
    if len(parts) >= 3 and parts[0] == "cam":
        return parts[1].upper(), parts[2].lower()
    if len(parts) >= 2:
        return parts[0].upper(), parts[1].lower()
    if len(parts) == 1:
        return parts[0].upper(), "main"
    return "UNKNOWN", "main"


def parse_start_time_from_path(file_path: Path) -> datetime:
    """Extract UTC start timestamp from segment filename or fall back to mtime."""
    stem = file_path.stem
    match = DATETIME_PATTERN.search(stem)
    if match:
        year, month, day, hour, minute, second = (int(x) for x in match.groups())
        timestamp = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
        try:
            # Older MediaMTX processes used host-local time in filenames ending in Z.
            # File creation time distinguishes those files from correctly stamped UTC files.
            birth = getattr(file_path.stat(), "st_birthtime", None)
            local_start = timestamp.replace(tzinfo=ZoneInfo(default_site_zone_name())).astimezone(UTC)
            if (
                birth is not None
                and abs(local_start.timestamp() - birth) < 5
                and abs(timestamp.timestamp() - birth) > 5
            ):
                return local_start
        except OSError:
            pass
        return timestamp

    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC)
    except Exception:
        return utc_now()


def parse_segment_metadata(
    env_dict: dict[str, str],
) -> SegmentMetadata:
    """Parse segment metadata from MediaMTX environment variables."""
    mtx_path = env_dict.get("MTX_PATH", "")
    segment_path_str = env_dict.get("MTX_SEGMENT_PATH", "")
    duration_str = env_dict.get("MTX_SEGMENT_DURATION", "60.0")

    serial, stream_type = parse_mtx_path(mtx_path)
    file_path = Path(segment_path_str).resolve()

    try:
        duration = float(duration_str)
        if duration <= 0:
            duration = 60.0
    except ValueError:
        duration = 60.0

    start_time = parse_start_time_from_path(file_path)
    end_time = start_time + timedelta(seconds=duration)

    file_size = 0
    if file_path.exists():
        try:
            file_size = file_path.stat().st_size
        except Exception:
            file_size = 0

    status = "truncated" if file_size < MIN_VALID_SEGMENT_BYTES else "active"

    return SegmentMetadata(
        camera_serial=serial,
        stream_type=stream_type,
        file_path=file_path,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration,
        file_size_bytes=file_size,
        status=status,
    )


async def record_segment_from_hook(
    session: AsyncSession,
    env_dict: dict[str, str],
) -> Segment | None:
    """Index completed segment from real-time MediaMTX completion hook."""
    meta = parse_segment_metadata(env_dict)

    if not str(meta.file_path) or meta.camera_serial == "UNKNOWN":
        logger.warning("Invalid hook metadata received: %s", env_dict)
        return None

    # Check if camera exists in database (case-insensitive)
    cam_stmt = select(Camera).where(Camera.serial == meta.camera_serial)
    cam_res = await session.execute(cam_stmt)
    cam = cam_res.scalar_one_or_none()
    if cam is None:
        # Try matching lower serial
        all_cams_res = await session.execute(select(Camera))
        all_cams = all_cams_res.scalars().all()
        for c in all_cams:
            if c.serial.upper() == meta.camera_serial:
                cam = c
                break

    if cam is None:
        logger.warning(
            "Segment received for unregistered camera serial %s: %s",
            meta.camera_serial,
            meta.file_path,
        )
        return None

    # Resolve exact casing of camera serial
    actual_serial = cam.serial
    norm_path = str(meta.file_path)

    # The completion hook supplies precise timing even if a simultaneous scan adopted the file.
    timing = dict(
        start_time=meta.start_time,
        end_time=meta.end_time,
        status=meta.status,
        duration_seconds=meta.duration_seconds,
        file_size_bytes=meta.file_size_bytes,
    )
    stmt = insert(Segment).values(
        camera_serial=actual_serial, stream_type=meta.stream_type, file_path=norm_path, **timing
    )
    await session.execute(stmt.on_conflict_do_update(index_elements=[Segment.file_path], set_=timing))
    await session.commit()
    return await session.scalar(select(Segment).where(Segment.file_path == norm_path))


async def scan_and_reconcile(
    session: AsyncSession,
    storage_path: Path,
    serial_filter: str | None = None,
) -> ScanReport:
    """Reconcile SQLite segment index with actual video files present on disk."""
    # 1. Fetch registered cameras
    cam_stmt = select(Camera).execution_options(include_archived=True)
    if serial_filter:
        cam_stmt = cam_stmt.where(Camera.serial == serial_filter)
    cam_res = await session.execute(cam_stmt)
    cameras = cam_res.scalars().all()
    known_serials: dict[str, str] = {c.serial.upper(): c.serial for c in cameras}

    # 2. Check existing database rows for missing or truncated files
    seg_stmt = select(Segment)
    if serial_filter:
        seg_stmt = seg_stmt.where(Segment.camera_serial == serial_filter)
    seg_res = await session.execute(seg_stmt)
    db_segments = seg_res.scalars().all()

    indexed_paths: set[str] = set()
    missing_marked = 0
    truncated_marked = 0
    total_valid = 0

    for seg in db_segments:
        p = Path(seg.file_path)
        indexed_paths.add(str(p.resolve()))  # noqa: ASYNC240

        if not p.exists():  # noqa: ASYNC240
            if seg.status != "missing":
                seg.status = "missing"
                missing_marked += 1
        else:
            try:
                parsed_start = parse_start_time_from_path(p)
                filename_time = DATETIME_PATTERN.search(p.stem)
                if filename_time:
                    year, month, day, hour, minute, second = (int(part) for part in filename_time.groups())
                    stored_filename_start = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
                    if seg.start_time == stored_filename_start and parsed_start != seg.start_time:
                        delta = parsed_start - seg.start_time
                        seg.start_time = parsed_start
                        seg.end_time += delta
                sz = p.stat().st_size  # noqa: ASYNC240
                seg.file_size_bytes = sz
                if sz < MIN_VALID_SEGMENT_BYTES:
                    if seg.status != "truncated":
                        seg.status = "truncated"
                        truncated_marked += 1
                else:
                    if seg.status != "active":
                        seg.status = "active"
                    total_valid += 1
            except Exception as exc:
                logger.debug("Could not stat %s: %s", p, exc)

    # 3. Walk storage directory to adopt unindexed .mp4 files
    adopted = 0
    resolved_storage = storage_path.resolve()  # noqa: ASYNC240

    if resolved_storage.exists():
        for root, _, files in os.walk(resolved_storage):
            for file_name in files:
                if not file_name.lower().endswith(".mp4"):
                    continue

                full_path = (Path(root) / file_name).resolve()
                norm_full = str(full_path)

                if norm_full in indexed_paths:
                    continue

                # Identify camera serial from path hierarchy
                matched_serial = None
                for part in full_path.parts:
                    part_upper = part.upper()
                    if part_upper in known_serials:
                        matched_serial = known_serials[part_upper]
                        break

                if matched_serial is None:
                    continue

                # Determine stream type
                stream_type = "sub" if "sub" in full_path.parts else "main"

                # Parse timing and size
                start_time = parse_start_time_from_path(full_path)
                try:
                    file_size = full_path.stat().st_size
                except Exception:
                    file_size = 0

                # Default 60s duration for adopted segments
                duration = 60.0
                end_time = start_time + timedelta(seconds=duration)
                status = "truncated" if file_size < MIN_VALID_SEGMENT_BYTES else "active"

                adoption = insert(Segment).values(
                    camera_serial=matched_serial,
                    stream_type=stream_type,
                    file_path=norm_full,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    file_size_bytes=file_size,
                    status=status,
                    is_protected=False,
                    protection_reason=None,
                    created_at=utc_now(),
                )
                inserted_id = await session.scalar(
                    adoption.on_conflict_do_nothing(index_elements=[Segment.file_path]).returning(Segment.id)
                )
                indexed_paths.add(norm_full)
                if inserted_id is not None:
                    adopted += 1
                if status == "active":
                    total_valid += 1

    await session.commit()
    return ScanReport(
        adopted=adopted,
        missing_marked=missing_marked,
        truncated_marked=truncated_marked,
        total_valid=total_valid,
    )
