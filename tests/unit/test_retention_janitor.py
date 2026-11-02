"""Unit tests for RetentionJanitorService, time-based pruning, size caps, and protected segment immunity."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, RecordingSettings, Segment
from vizenlink_nvr.services.janitor import enforce_camera_retention
from vizenlink_nvr.timeutil import UTC, utc_now


@pytest.fixture
async def janitor_db(tmp_path: Path):
    """Database fixture for janitor retention unit tests."""
    db_file = tmp_path / "test_janitor.db"
    engine = create_engine_for(db_file)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = utc_now()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        cam = Camera(
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
        session.add(cam)
        await session.commit()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_time_based_retention_pruning(janitor_db: AsyncSession, tmp_path: Path) -> None:
    """Janitor deletes segments older than retention_days, but strictly protects is_protected=True."""
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    # 14 days retention
    settings = RecordingSettings(
        camera_serial="VZL-CAM-001",
        mode="continuous",
        schedule_json="{}",
        audio_enabled=False,
        retention_days=14,
        retention_max_gb=None,
        created_at=now,
        updated_at=now,
    )
    janitor_db.add(settings)

    # Segment 1: 20 days old (unprotected -> should be deleted)
    t1_start = now - timedelta(days=20)
    t1_file = tmp_path / "seg1.mp4"
    t1_file.write_bytes(b"data" * 1024)
    seg1 = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path=str(t1_file),
        start_time=t1_start,
        end_time=t1_start + timedelta(seconds=60),
        duration_seconds=60.0,
        file_size_bytes=4096,
        status="active",
        is_protected=False,
        created_at=t1_start,
    )

    # Segment 2: 20 days old (PROTECTED -> MUST NOT BE DELETED!)
    t2_file = tmp_path / "seg2_protected.mp4"
    t2_file.write_bytes(b"protected" * 1024)
    seg2 = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path=str(t2_file),
        start_time=t1_start,
        end_time=t1_start + timedelta(seconds=60),
        duration_seconds=60.0,
        file_size_bytes=9216,
        status="active",
        is_protected=True,
        protection_reason="Incident report #123",
        created_at=t1_start,
    )

    # Segment 3: 5 days old (recent -> should be kept)
    t3_start = now - timedelta(days=5)
    t3_file = tmp_path / "seg3.mp4"
    t3_file.write_bytes(b"recent" * 1024)
    seg3 = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path=str(t3_file),
        start_time=t3_start,
        end_time=t3_start + timedelta(seconds=60),
        duration_seconds=60.0,
        file_size_bytes=6144,
        status="active",
        is_protected=False,
        created_at=t3_start,
    )

    janitor_db.add_all([seg1, seg2, seg3])
    await janitor_db.commit()

    # Enforce retention
    report = await enforce_camera_retention(janitor_db, "VZL-CAM-001", now=now)

    assert str(t1_file) in report.deleted_files
    assert str(t2_file) not in report.deleted_files
    assert str(t3_file) not in report.deleted_files
    assert report.freed_bytes == 4096

    # Verify physical file deletion
    assert not t1_file.exists()
    assert t2_file.exists(), "Protected file was erroneously deleted!"
    assert t3_file.exists()

    # Verify database state
    remaining = (await janitor_db.execute(select(Segment))).scalars().all()
    remaining_paths = {s.file_path for s in remaining}
    assert str(t1_file) not in remaining_paths
    assert str(t2_file) in remaining_paths
    assert str(t3_file) in remaining_paths


@pytest.mark.asyncio
async def test_size_based_retention_pruning(janitor_db: AsyncSession, tmp_path: Path) -> None:
    """Janitor prunes oldest unprotected segments when camera storage exceeds retention_max_gb."""
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    # Max 1 GB cap
    settings = RecordingSettings(
        camera_serial="VZL-CAM-001",
        mode="continuous",
        schedule_json="{}",
        audio_enabled=False,
        retention_days=None,
        retention_max_gb=1,  # 1 GB cap = 1,073,741,824 bytes
        created_at=now,
        updated_at=now,
    )
    janitor_db.add(settings)

    # 3 segments of 500 MB each = 1.5 GB total (500 MB over cap)
    # 500 MB = 500 * 1024 * 1024 = 524,288,000 bytes
    size_500mb = 524_288_000

    f_oldest = tmp_path / "oldest.mp4"
    f_oldest.write_bytes(b"x")  # stub file
    seg_oldest = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path=str(f_oldest),
        start_time=now - timedelta(hours=3),
        end_time=now - timedelta(hours=2),
        duration_seconds=3600.0,
        file_size_bytes=size_500mb,
        status="active",
        is_protected=False,
        created_at=now - timedelta(hours=3),
    )

    f_middle = tmp_path / "middle.mp4"
    f_middle.write_bytes(b"x")
    seg_middle = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path=str(f_middle),
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1),
        duration_seconds=3600.0,
        file_size_bytes=size_500mb,
        status="active",
        is_protected=False,
        created_at=now - timedelta(hours=2),
    )

    f_newest = tmp_path / "newest.mp4"
    f_newest.write_bytes(b"x")
    seg_newest = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path=str(f_newest),
        start_time=now - timedelta(hours=1),
        end_time=now,
        duration_seconds=3600.0,
        file_size_bytes=size_500mb,
        status="active",
        is_protected=False,
        created_at=now - timedelta(hours=1),
    )

    janitor_db.add_all([seg_oldest, seg_middle, seg_newest])
    await janitor_db.commit()

    report = await enforce_camera_retention(janitor_db, "VZL-CAM-001", now=now)

    # Deleting oldest 500 MB segment brings total down to 1.0 GB (within 1 GB cap)
    assert report.deleted_files == [str(f_oldest)]
    assert report.freed_bytes == size_500mb

    assert not f_oldest.exists()
    assert f_middle.exists()
    assert f_newest.exists()

