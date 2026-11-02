"""Unit tests for recording gap watchdog (HLTH-01, HLTH-03)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, RecordingSettings, Segment
from vizenlink_nvr.services.health import OnlineState, RecordingState
from vizenlink_nvr.services.watchdog import WatchdogService, check_camera_gaps
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def memory_session(tmp_path: Path):
    """In-memory SQLite async session with schema initialized."""
    db_file = tmp_path / "watchdog_test.db"
    engine = create_engine_for(db_file)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = AsyncSession(engine, expire_on_commit=False)
    yield session
    await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_gap_watchdog_healthy_recording(memory_session: AsyncSession) -> None:
    """Camera with segment within expected window is marked RECORDING with no gap alarm."""
    now = utc_now()
    cam = Camera(
        serial="CAM-HEALTHY",
        host="192.168.1.50",
        https_port=443,
        mac="AA:BB:CC:50:50:50",
        name="Healthy Cam",
        manufacturer="NuraEye",
        model="NE-4K",
        tls_fingerprint_sha256="fp_healthy",
        state="active",
        added_at=now - timedelta(minutes=10),
        host_updated_at=now - timedelta(minutes=10),
    )
    settings = RecordingSettings(
        camera_serial="CAM-HEALTHY",
        mode="continuous",
        created_at=now,
        updated_at=now,
    )
    seg = Segment(
        camera_serial="CAM-HEALTHY",
        stream_type="main",
        file_path="/data/seg_healthy.mp4",
        start_time=now - timedelta(seconds=90),
        end_time=now - timedelta(seconds=30),  # 30s ago (< 150s threshold)
        duration_seconds=60.0,
        file_size_bytes=1024,
        status="active",
        is_protected=False,
        created_at=now - timedelta(seconds=30),
    )
    memory_session.add_all([cam, settings, seg])
    await memory_session.commit()

    health_map = await check_camera_gaps(memory_session, now=now)
    assert "CAM-HEALTHY" in health_map
    health = health_map["CAM-HEALTHY"]

    assert health.online_state == OnlineState.ONLINE
    assert health.recording_state == RecordingState.RECORDING
    assert health.gap_alarm is False
    assert health.last_segment_at is not None
    assert health.segment_age_seconds == pytest.approx(30.0, abs=1.0)


@pytest.mark.asyncio
async def test_gap_watchdog_detects_gap_alarm(memory_session: AsyncSession) -> None:
    """Camera with last segment older than 150s raises gap_alarm and flags NOT_RECORDING (HLTH-03)."""
    now = utc_now()
    cam = Camera(
        serial="CAM-GAP",
        host="192.168.1.51",
        https_port=443,
        mac="AA:BB:CC:51:51:51",
        name="Gap Cam",
        manufacturer="NuraEye",
        model="NE-4K",
        tls_fingerprint_sha256="fp_gap",
        state="active",
        added_at=now - timedelta(hours=1),
        host_updated_at=now - timedelta(hours=1),
    )
    settings = RecordingSettings(
        camera_serial="CAM-GAP",
        mode="continuous",
        created_at=now,
        updated_at=now,
    )
    # Segment completed 200s ago (> 150s window)
    seg = Segment(
        camera_serial="CAM-GAP",
        stream_type="main",
        file_path="/data/seg_gap.mp4",
        start_time=now - timedelta(seconds=260),
        end_time=now - timedelta(seconds=200),
        duration_seconds=60.0,
        file_size_bytes=1024,
        status="active",
        is_protected=False,
        created_at=now - timedelta(seconds=200),
    )
    memory_session.add_all([cam, settings, seg])
    await memory_session.commit()

    health_map = await WatchdogService.check_camera_gaps(memory_session, now=now)
    assert "CAM-GAP" in health_map
    health = health_map["CAM-GAP"]

    # Prohibition verified: online green badge does NOT mask recording gap
    assert health.online_state == OnlineState.ONLINE
    assert health.recording_state == RecordingState.NOT_RECORDING
    assert health.gap_alarm is True
    assert health.segment_age_seconds == pytest.approx(200.0, abs=1.0)


@pytest.mark.asyncio
async def test_gap_watchdog_disabled_mode(memory_session: AsyncSession) -> None:
    """Camera in recording mode 'off' shows DISABLED state with no gap alarm."""
    now = utc_now()
    cam = Camera(
        serial="CAM-OFF",
        host="192.168.1.52",
        https_port=443,
        mac="AA:BB:CC:52:52:52",
        name="Off Cam",
        manufacturer="NuraEye",
        model="NE-4K",
        tls_fingerprint_sha256="fp_off",
        state="active",
        added_at=now - timedelta(hours=1),
        host_updated_at=now - timedelta(hours=1),
    )
    settings = RecordingSettings(
        camera_serial="CAM-OFF",
        mode="off",
        created_at=now,
        updated_at=now,
    )
    memory_session.add_all([cam, settings])
    await memory_session.commit()

    health_map = await check_camera_gaps(memory_session, now=now)
    assert "CAM-OFF" in health_map
    health = health_map["CAM-OFF"]

    assert health.online_state == OnlineState.ONLINE
    assert health.recording_state == RecordingState.DISABLED
    assert health.gap_alarm is False


@pytest.mark.asyncio
async def test_gap_watchdog_newly_added_camera_startup_window(memory_session: AsyncSession) -> None:
    """Camera added recently (e.g. 20s ago) with no segments is in startup window without gap alarm."""
    now = utc_now()
    cam = Camera(
        serial="CAM-NEW",
        host="192.168.1.53",
        https_port=443,
        mac="AA:BB:CC:53:53:53",
        name="New Cam",
        manufacturer="NuraEye",
        model="NE-4K",
        tls_fingerprint_sha256="fp_new",
        state="active",
        added_at=now - timedelta(seconds=20),
        host_updated_at=now - timedelta(seconds=20),
    )
    memory_session.add(cam)
    await memory_session.commit()

    health_map = await check_camera_gaps(memory_session, now=now)
    health = health_map["CAM-NEW"]

    assert health.online_state == OnlineState.ONLINE
    assert health.recording_state == RecordingState.NOT_RECORDING
    assert health.gap_alarm is False
    assert health.last_segment_at is None
