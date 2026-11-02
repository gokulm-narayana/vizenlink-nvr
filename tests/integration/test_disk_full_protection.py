"""Integration tests for disk full protection and low-water mark oldest segment pruning (REC-07)."""

from __future__ import annotations

import shutil
from collections import namedtuple
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, Segment
from vizenlink_nvr.services.janitor import enforce_disk_low_water_mark
from vizenlink_nvr.timeutil import utc_now

DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])


@pytest.mark.asyncio
async def test_low_water_mark_pruning_protects_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When disk free space drops below reserve, janitor prunes oldest unprotected segments."""
    db_file = tmp_path / "test_low_water.db"
    engine = create_engine_for(db_file)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = utc_now()
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        cam1 = Camera(
            serial="VZL-CAM-001",
            host="192.168.1.10",
            https_port=443,
            mac="AA:BB:CC:DD:EE:01",
            name="Front",
            state="active",
            tls_fingerprint_sha256="fp1",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="VZL-CAM-002",
            host="192.168.1.20",
            https_port=443,
            mac="AA:BB:CC:DD:EE:02",
            name="Back",
            state="active",
            tls_fingerprint_sha256="fp2",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])

        # Create segments of 500 MB each
        size_500mb = 500 * 1024 * 1024

        # Cam1 - Oldest (unprotected -> eligible for pruning)
        f1 = rec_dir / "cam1_oldest.mp4"
        f1.write_bytes(b"x")
        seg1 = Segment(
            camera_serial="VZL-CAM-001",
            stream_type="main",
            file_path=str(f1),
            start_time=now - timedelta(hours=5),
            end_time=now - timedelta(hours=4),
            duration_seconds=3600.0,
            file_size_bytes=size_500mb,
            status="active",
            is_protected=False,
            created_at=now - timedelta(hours=5),
        )

        # Cam2 - Very old but PROTECTED (MUST NOT BE PRUNED!)
        f2 = rec_dir / "cam2_protected.mp4"
        f2.write_bytes(b"x")
        seg2 = Segment(
            camera_serial="VZL-CAM-002",
            stream_type="main",
            file_path=str(f2),
            start_time=now - timedelta(hours=4),
            end_time=now - timedelta(hours=3),
            duration_seconds=3600.0,
            file_size_bytes=size_500mb,
            status="active",
            is_protected=True,
            protection_reason="Critical evidence",
            created_at=now - timedelta(hours=4),
        )

        # Cam2 - Medium old (unprotected -> eligible)
        f3 = rec_dir / "cam2_medium.mp4"
        f3.write_bytes(b"x")
        seg3 = Segment(
            camera_serial="VZL-CAM-002",
            stream_type="main",
            file_path=str(f3),
            start_time=now - timedelta(hours=3),
            end_time=now - timedelta(hours=2),
            duration_seconds=3600.0,
            file_size_bytes=size_500mb,
            status="active",
            is_protected=False,
            created_at=now - timedelta(hours=3),
        )

        # Cam1 - Recent (unprotected)
        f4 = rec_dir / "cam1_recent.mp4"
        f4.write_bytes(b"x")
        seg4 = Segment(
            camera_serial="VZL-CAM-001",
            stream_type="main",
            file_path=str(f4),
            start_time=now - timedelta(hours=1),
            end_time=now,
            duration_seconds=3600.0,
            file_size_bytes=size_500mb,
            status="active",
            is_protected=False,
            created_at=now - timedelta(hours=1),
        )

        session.add_all([seg1, seg2, seg3, seg4])
        await session.commit()

        # Mock disk usage: Total 100 GB, Free 9.5 GB
        # Reserve required: 10 GB. Free 9.5 GB is below reserve!
        # Target to reach: 10 GB + 1 GB hysteresis = 11 GB (need to free 1.5 GB = 3 segments)
        mock_usage = DiskUsage(
            total=100 * 1024 * 1024 * 1024,
            used=90500 * 1024 * 1024,
            free=9500 * 1024 * 1024,  # 9.5 GB free (< 10 GB reserve)
        )
        monkeypatch.setattr(shutil, "disk_usage", lambda p: mock_usage)

        report = await enforce_disk_low_water_mark(
            session,
            storage_path=rec_dir,
            reserve_bytes=10 * 1024 * 1024 * 1024,
        )

        assert report.triggered is True
        assert report.deleted_count > 0

        # Physical file verification
        assert not f1.exists(), "Oldest segment was not pruned!"
        assert f2.exists(), "PROTECTED segment was pruned during low-water mark cleanup!"

        # Database record verification
        remaining = (await session.execute(select(Segment))).scalars().all()
        remaining_paths = {s.file_path for s in remaining}
        assert str(f1) not in remaining_paths
        assert str(f2) in remaining_paths

    await engine.dispose()
