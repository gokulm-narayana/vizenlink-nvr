"""Unit tests for StorageService, telemetry, and health evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base
from vizenlink_nvr.services.storage import (
    DEFAULT_RESERVE_BYTES,
    StorageHealthState,
    StorageTelemetry,
    estimate_retention_days,
    evaluate_storage_health,
    get_storage_config,
    get_storage_telemetry,
    set_storage_path,
)


def test_get_storage_telemetry_valid(tmp_path: Path) -> None:
    """Telemetry returns positive integer values for an existing directory."""
    telemetry = get_storage_telemetry(tmp_path)
    assert telemetry is not None
    assert telemetry.total_bytes > 0
    assert telemetry.free_bytes >= 0
    assert telemetry.used_bytes >= 0
    assert telemetry.reserve_bytes == DEFAULT_RESERVE_BYTES


def test_get_storage_telemetry_nonexistent_ancestor(tmp_path: Path) -> None:
    """Telemetry resolves to an existing parent if directory does not exist yet."""
    target = tmp_path / "deep" / "nested" / "dir"
    telemetry = get_storage_telemetry(target)
    assert telemetry is not None
    assert telemetry.total_bytes > 0


def test_evaluate_storage_health_system_disk_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Refuses recording to system root partition without --allow-system-disk."""
    monkeypatch.setattr("vizenlink_nvr.services.storage.is_system_drive", lambda p: True)

    health, reason = evaluate_storage_health(tmp_path, allow_system_disk=False)
    assert health == StorageHealthState.SYSTEM_DISK_REFUSED
    assert reason is not None
    assert "refused" in reason.lower()

    # With allow_system_disk=True, it should proceed past system disk check
    health_ok, _ = evaluate_storage_health(tmp_path, allow_system_disk=True)
    assert health_ok == StorageHealthState.OK


def test_evaluate_storage_health_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Detects read-only storage directory when canary write fails."""
    monkeypatch.setattr("vizenlink_nvr.services.storage.is_system_drive", lambda p: False)

    # Mock Path.write_text to simulate PermissionError / OSError
    orig_write = Path.write_text

    def mock_write(self: Path, *args: object, **kwargs: object) -> int:
        if self.name == ".canary_write_test":
            raise PermissionError("Read-only file system")
        return orig_write(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", mock_write)

    health, reason = evaluate_storage_health(tmp_path, allow_system_disk=False)
    assert health == StorageHealthState.READ_ONLY
    assert reason is not None
    assert "not writable" in reason.lower()


def test_evaluate_storage_health_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns FULL when free space is below reserve_bytes."""
    monkeypatch.setattr("vizenlink_nvr.services.storage.is_system_drive", lambda p: False)

    mock_telemetry = StorageTelemetry(
        total_bytes=100 * 1024 * 1024 * 1024,
        used_bytes=95 * 1024 * 1024 * 1024,
        free_bytes=5 * 1024 * 1024 * 1024,  # 5 GiB free
        reserve_bytes=10 * 1024 * 1024 * 1024,  # 10 GiB reserve required
    )
    monkeypatch.setattr("vizenlink_nvr.services.storage.get_storage_telemetry", lambda p, r: mock_telemetry)

    health, reason = evaluate_storage_health(
        tmp_path,
        allow_system_disk=False,
        reserve_bytes=10 * 1024 * 1024 * 1024,
    )
    assert health == StorageHealthState.FULL
    assert reason is not None
    assert "below reserve" in reason.lower()


def test_evaluate_storage_health_unmounted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns UNMOUNTED when target path cannot be created."""
    target = Path("/nonexistent/readonly_mount/rec")

    def mock_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("Mount point missing")

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    health, reason = evaluate_storage_health(target, allow_system_disk=True)
    assert health == StorageHealthState.UNMOUNTED
    assert reason is not None
    assert "cannot be created" in reason.lower()


def test_estimate_retention_days() -> None:
    """Calculates estimated retention days accurately based on free space above reserve."""
    # 4 Mbps = 500 KB/sec = 43.2 GB/day for 1 camera
    # 43.2 GB = 43.2 * 86400 * 500,000 bytes = 43,200,000,000 bytes
    # If 86.4 GB free above reserve, should be ~2.0 days
    telemetry = StorageTelemetry(
        total_bytes=200_000_000_000,
        used_bytes=100_000_000_000,
        free_bytes=100_000_000_000,
        reserve_bytes=13_600_000_000,
    )
    # Available = 86,400,000,000 bytes
    # 4000 kbps = 4,000,000 bps = 500,000 B/s * 86400 = 43,200,000,000 B/day
    # 86,400,000,000 / 43,200,000,000 = 2.0 days
    est = estimate_retention_days(telemetry, total_active_cameras=1, avg_bitrate_kbps=4000)
    assert est == 2.0

    # When free space is below reserve, retention is 0.0
    telemetry_empty = StorageTelemetry(
        total_bytes=100_000_000_000,
        used_bytes=95_000_000_000,
        free_bytes=5_000_000_000,
        reserve_bytes=10_000_000_000,
    )
    est_zero = estimate_retention_days(telemetry_empty, total_active_cameras=1)
    assert est_zero == 0.0

    # None telemetry returns None
    assert estimate_retention_days(None) is None


@pytest.mark.asyncio
async def test_storage_database_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """get_storage_config and set_storage_path load and save storage settings."""
    # Mock system drive check to allow local tmp path
    monkeypatch.setattr("vizenlink_nvr.services.storage.is_system_drive", lambda p: False)

    db_file = tmp_path / "test_storage.db"
    engine = create_engine_for(db_file)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    recordings_dir = tmp_path / "recordings"

    async with AsyncSession(engine) as session:
        # Default config when no row exists yet
        cfg = await get_storage_config(session, default_path=recordings_dir)
        assert cfg.storage_path == recordings_dir
        assert cfg.allow_system_disk is False
        assert cfg.reserve_bytes == DEFAULT_RESERVE_BYTES
        assert cfg.health_state == StorageHealthState.OK

        # Update storage path
        new_dir = tmp_path / "external_rec"
        updated_cfg = await set_storage_path(
            session,
            target_path=new_dir,
            allow_system_disk=True,
            reserve_bytes=20 * 1024 * 1024 * 1024,
        )
        assert updated_cfg.storage_path == new_dir.resolve()
        assert updated_cfg.allow_system_disk is True
        assert updated_cfg.reserve_bytes == 20 * 1024 * 1024 * 1024

        # Read back in new session
        read_cfg = await get_storage_config(session, default_path=recordings_dir)
        assert read_cfg.storage_path == new_dir.resolve()
        assert read_cfg.allow_system_disk is True
        assert read_cfg.reserve_bytes == 20 * 1024 * 1024 * 1024

    await engine.dispose()
