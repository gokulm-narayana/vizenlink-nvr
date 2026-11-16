"""Storage configuration, disk space telemetry, and system drive protection service."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from vizenlink_nvr.db.models import StorageSettings
from vizenlink_nvr.timeutil import utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_RESERVE_BYTES: int = 10 * 1024 * 1024 * 1024  # 10 GiB
DEFAULT_RECORDING_BITRATE_KBPS: int = 4000  # 4 Mbps per stream default


class StorageHealthState(StrEnum):
    """Storage volume health and readiness states."""

    OK = "ok"
    SYSTEM_DISK_REFUSED = "system_disk_refused"
    UNMOUNTED = "unmounted"
    READ_ONLY = "read_only"
    FULL = "full"


@dataclass(frozen=True)
class StorageTelemetry:
    """Disk space metrics for recording volume."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    reserve_bytes: int


@dataclass(frozen=True)
class StorageConfig:
    """Consolidated storage configuration and health status."""

    storage_path: Path
    allow_system_disk: bool
    reserve_bytes: int
    health_state: StorageHealthState
    health_reason: str | None
    telemetry: StorageTelemetry | None
    estimated_retention_days: float | None


def is_system_drive(target_path: Path) -> bool:
    """Detect whether target_path resides on the operating system host root partition."""
    resolved = target_path.resolve()

    if os.name == "nt":
        system_drive = os.environ.get("SystemDrive", "C:").upper()
        # Ensure format like "C:"
        if not system_drive.endswith(":"):
            system_drive = f"{system_drive}:"
        target_drive = resolved.drive.upper()
        return target_drive == system_drive

    # POSIX: compare filesystem device ID (st_dev) against root "/"
    try:
        p = resolved
        while not p.exists() and p != p.parent:
            p = p.parent
        root_stat = os.stat("/")
        target_stat = os.stat(p)
        return root_stat.st_dev == target_stat.st_dev
    except Exception:
        return False


def get_storage_telemetry(
    target_path: Path,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> StorageTelemetry | None:
    """Fetch filesystem disk usage for target_path."""
    try:
        p = target_path.resolve()
        while not p.exists() and p != p.parent:
            p = p.parent
        usage = shutil.disk_usage(p)
        return StorageTelemetry(
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            reserve_bytes=reserve_bytes,
        )
    except Exception:
        return None


def evaluate_storage_health(
    target_path: Path,
    allow_system_disk: bool = False,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> tuple[StorageHealthState, str | None]:
    """Evaluate storage volume health and accessibility per D-32 and D-33."""
    resolved = target_path.resolve()

    # 1. System drive protection guard (D-32). Checked before anything is
    #    created, so a refused path leaves no directory behind.
    if is_system_drive(resolved) and not allow_system_disk:
        return (
            StorageHealthState.SYSTEM_DISK_REFUSED,
            "Recording to system root disk is refused without --allow-system-disk",
        )

    # 2. Existence / Directory creation test
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return (
            StorageHealthState.UNMOUNTED,
            f"Storage path does not exist and cannot be created: {exc}",
        )

    # 3. Read-only / Write permissions test
    canary = resolved / ".canary_write_test"
    try:
        canary.write_text("ok", encoding="utf-8")
        canary.unlink(missing_ok=True)
    except Exception as exc:
        return (
            StorageHealthState.READ_ONLY,
            f"Storage path is not writable: {exc}",
        )

    # 4. Low-water mark reserve test (D-33)
    telemetry = get_storage_telemetry(resolved, reserve_bytes)
    if telemetry is not None:
        if telemetry.free_bytes < reserve_bytes:
            return (
                StorageHealthState.FULL,
                f"Free space ({telemetry.free_bytes} B) is below reserve ({reserve_bytes} B)",
            )

    return (StorageHealthState.OK, None)


def estimate_retention_days(
    telemetry: StorageTelemetry | None,
    total_active_cameras: int = 1,
    avg_bitrate_kbps: int = DEFAULT_RECORDING_BITRATE_KBPS,
) -> float | None:
    """Estimate retention span in days based on available disk space and camera bitrates."""
    if telemetry is None:
        return None

    if total_active_cameras <= 0:
        total_active_cameras = 1

    # Bytes per second across active cameras: (bitrate * 1000 / 8) * cameras
    bytes_per_sec = (avg_bitrate_kbps * 1000 / 8) * total_active_cameras
    bytes_per_day = bytes_per_sec * 86400

    available_bytes = max(0, telemetry.free_bytes - telemetry.reserve_bytes)
    if bytes_per_day <= 0:
        return None

    return round(available_bytes / bytes_per_day, 1)


async def get_storage_config(
    session: AsyncSession,
    default_path: Path,
) -> StorageConfig:
    """Load persisted storage settings and evaluate current health status."""
    stmt = select(StorageSettings).where(StorageSettings.id == 1)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is not None:
        target_path = Path(row.storage_path)
        allow_sys = row.allow_system_disk
        reserve = row.reserve_bytes
    else:
        target_path = default_path
        allow_sys = False
        reserve = DEFAULT_RESERVE_BYTES

    health_state, health_reason = evaluate_storage_health(
        target_path,
        allow_system_disk=allow_sys,
        reserve_bytes=reserve,
    )
    telemetry = get_storage_telemetry(target_path, reserve)
    est_days = estimate_retention_days(telemetry)

    return StorageConfig(
        storage_path=target_path,
        allow_system_disk=allow_sys,
        reserve_bytes=reserve,
        health_state=health_state,
        health_reason=health_reason,
        telemetry=telemetry,
        estimated_retention_days=est_days,
    )


async def set_storage_path(
    session: AsyncSession,
    target_path: Path,
    allow_system_disk: bool = False,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
) -> StorageConfig:
    """Persist new storage path configuration and return evaluated config."""
    resolved = target_path.resolve()  # noqa: ASYNC240

    health_state, health_reason = evaluate_storage_health(
        resolved,
        allow_system_disk=allow_system_disk,
        reserve_bytes=reserve_bytes,
    )

    now = utc_now()
    stmt = select(StorageSettings).where(StorageSettings.id == 1)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = StorageSettings(
            id=1,
            storage_path=str(resolved),
            allow_system_disk=allow_system_disk,
            reserve_bytes=reserve_bytes,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.storage_path = str(resolved)
        row.allow_system_disk = allow_system_disk
        row.reserve_bytes = reserve_bytes
        row.updated_at = now

    await session.commit()

    telemetry = get_storage_telemetry(resolved, reserve_bytes)
    est_days = estimate_retention_days(telemetry)

    return StorageConfig(
        storage_path=resolved,
        allow_system_disk=allow_system_disk,
        reserve_bytes=reserve_bytes,
        health_state=health_state,
        health_reason=health_reason,
        telemetry=telemetry,
        estimated_retention_days=est_days,
    )
