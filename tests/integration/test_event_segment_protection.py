"""Integration tests for event pre-roll/post-roll segment protection and janitor immunity (REC-04)."""

from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.db.models import Base, Camera, Segment
from vizenlink_nvr.events.protection import SegmentProtectionService
from vizenlink_nvr.services.janitor import enforce_disk_low_water_mark
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_event_segment_protection_and_low_water_immunity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test overlapping segments are protected by pre/post-roll window and immune to low-water pruning."""
    db_path = tmp_path / "test_protection.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = utc_now()

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True)

    # Create dummy segment files on disk
    file1 = storage_root / "seg1.mp4"
    file2 = storage_root / "seg2.mp4"
    file3 = storage_root / "seg3.mp4"
    file1.write_bytes(b"\x00" * 4096)
    file2.write_bytes(b"\x00" * 4096)
    file3.write_bytes(b"\x00" * 4096)

    serial = "CAM-PROT-01"

    async with session_factory() as session:
        cam = Camera(
            serial=serial,
            host="192.168.1.80",
            name="Front Gate",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)

        # Segment 1: T-60s to T
        seg1 = Segment(
            camera_serial=serial,
            stream_type="main",
            file_path=str(file1),
            start_time=now - timedelta(seconds=60),
            end_time=now,
            duration_seconds=60.0,
            file_size_bytes=4096,
            status="active",
            is_protected=False,
            created_at=now - timedelta(seconds=60),
        )
        # Segment 2: T to T+60s
        seg2 = Segment(
            camera_serial=serial,
            stream_type="main",
            file_path=str(file2),
            start_time=now,
            end_time=now + timedelta(seconds=60),
            duration_seconds=60.0,
            file_size_bytes=4096,
            status="active",
            is_protected=False,
            created_at=now,
        )
        # Segment 3: T+60s to T+120s
        seg3 = Segment(
            camera_serial=serial,
            stream_type="main",
            file_path=str(file3),
            start_time=now + timedelta(seconds=60),
            end_time=now + timedelta(seconds=120),
            duration_seconds=60.0,
            file_size_bytes=4096,
            status="active",
            is_protected=False,
            created_at=now + timedelta(seconds=60),
        )
        session.add_all([seg1, seg2, seg3])
        await session.commit()

        # 1. Event occurs at T+10s with 15s pre-roll and 15s post-roll
        # Protected window: [T - 5s, T + 25s]
        # Seg 1 overlaps: start=T-60s, end=T (T > T-5s)
        # Seg 2 overlaps: start=T, end=T+60s (T < T+25s and T+60s > T-5s)
        # Seg 3 does NOT overlap: start=T+60s (T+60s > T+25s)
        event_time = now + timedelta(seconds=10)
        protected_ids = await SegmentProtectionService.protect_event_segments(
            session=session,
            camera_serial=serial,
            event_id=101,
            start_time=event_time,
            end_time=event_time,
            pre_roll_seconds=15,
            post_roll_seconds=15,
        )
        assert len(protected_ids) == 2
        assert seg1.id in protected_ids
        assert seg2.id in protected_ids
        assert seg3.id not in protected_ids

        # Refresh segments
        await session.refresh(seg1)
        await session.refresh(seg2)
        await session.refresh(seg3)

        assert seg1.is_protected is True
        assert seg1.protection_reason == "event:101"
        assert seg2.is_protected is True
        assert seg2.protection_reason == "event:101"
        assert seg3.is_protected is False

        # 2. Mock disk usage to trigger low-water pruning: 5 GB free < 10 GB reserve
        DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])
        monkeypatch.setattr(
            "shutil.disk_usage",
            lambda p: DiskUsage(total=100 * 1024**3, used=95 * 1024**3, free=5 * 1024**3),
        )

        # Run janitor low-water mark pruning
        report = await enforce_disk_low_water_mark(
            session=session,
            storage_path=storage_root,
            reserve_bytes=10 * 1024**3,
        )
        assert report.triggered is True
        assert report.deleted_count == 1

        # Unprotected seg3 must be deleted
        assert not file3.exists()

        # Crucial REC-04 invariant: protected segments 1 and 2 MUST survive
        assert file1.exists()
        assert file2.exists()

        # 3. Release event protection
        released = await SegmentProtectionService.release_event_segments(session, event_id=101)
        assert len(released) == 2

        await session.refresh(seg1)
        await session.refresh(seg2)
        assert seg1.is_protected is False
        assert seg2.is_protected is False

    await engine.dispose()
