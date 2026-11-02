"""Unit tests for dual camera health badges and recorder health evaluator (HLTH-01, HLTH-06)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, RecordingSettings, Segment
from vizenlink_nvr.services.health import (
    OnlineState,
    RecorderHealthService,
    RecorderHealthStatus,
    RecordingState,
)
from vizenlink_nvr.services.storage import StorageHealthState
from vizenlink_nvr.services.watchdog import check_camera_gaps
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def memory_session(tmp_path: Path):
    """In-memory SQLite async session with schema initialized."""
    db_file = tmp_path / "badges_test.db"
    engine = create_engine_for(db_file)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = AsyncSession(engine, expire_on_commit=False)
    yield session
    await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_dual_health_badges_matrix(memory_session: AsyncSession) -> None:
    """Validate dual independent badges across reachability and recording states (HLTH-01).

    Combinations:
    1. Active camera + active segments -> ONLINE + RECORDING
    2. Active camera + recording gap (>150s) -> ONLINE + NOT_RECORDING
       (proves online does NOT mask recording failure)
    3. Unreachable camera -> OFFLINE + NOT_RECORDING
    4. Auth failed camera -> AUTH_FAILED + NOT_RECORDING
    5. Active camera + mode 'off' -> ONLINE + DISABLED
    """
    now = utc_now()

    # 1. Cam 1: Online + Recording
    cam1 = Camera(
        serial="CAM-ON-REC",
        host="192.168.1.101",
        https_port=443,
        mac="AA:BB:CC:01:01:01",
        tls_fingerprint_sha256="fp_1",
        state="active",
        added_at=now - timedelta(hours=1),
        host_updated_at=now,
    )
    seg1 = Segment(
        camera_serial="CAM-ON-REC",
        stream_type="main",
        file_path="/data/c1.mp4",
        start_time=now - timedelta(seconds=70),
        end_time=now - timedelta(seconds=10),
        duration_seconds=60.0,
        file_size_bytes=2048,
        status="active",
        created_at=now,
    )

    # 2. Cam 2: Online + Not Recording (gap > 150s)
    cam2 = Camera(
        serial="CAM-ON-NOTREC",
        host="192.168.1.102",
        https_port=443,
        mac="AA:BB:CC:02:02:02",
        tls_fingerprint_sha256="fp_2",
        state="active",
        added_at=now - timedelta(hours=1),
        host_updated_at=now,
    )
    seg2 = Segment(
        camera_serial="CAM-ON-NOTREC",
        stream_type="main",
        file_path="/data/c2.mp4",
        start_time=now - timedelta(seconds=300),
        end_time=now - timedelta(seconds=240),  # 240s ago
        duration_seconds=60.0,
        file_size_bytes=2048,
        status="active",
        created_at=now,
    )

    # 3. Cam 3: Offline + Not Recording
    cam3 = Camera(
        serial="CAM-OFFLINE",
        host="192.168.1.103",
        https_port=443,
        mac="AA:BB:CC:03:03:03",
        tls_fingerprint_sha256="fp_3",
        state="unreachable",
        added_at=now - timedelta(hours=1),
        host_updated_at=now,
    )

    # 4. Cam 4: Auth Failed + Not Recording
    cam4 = Camera(
        serial="CAM-AUTHFAIL",
        host="192.168.1.104",
        https_port=443,
        mac="AA:BB:CC:04:04:04",
        tls_fingerprint_sha256="fp_4",
        state="auth_failed",
        added_at=now - timedelta(hours=1),
        host_updated_at=now,
    )

    # 5. Cam 5: Online + Disabled
    cam5 = Camera(
        serial="CAM-DISABLED",
        host="192.168.1.105",
        https_port=443,
        mac="AA:BB:CC:05:05:05",
        tls_fingerprint_sha256="fp_5",
        state="active",
        added_at=now - timedelta(hours=1),
        host_updated_at=now,
    )
    settings5 = RecordingSettings(
        camera_serial="CAM-DISABLED",
        mode="off",
        created_at=now,
        updated_at=now,
    )

    memory_session.add_all([cam1, seg1, cam2, seg2, cam3, cam4, cam5, settings5])
    await memory_session.commit()

    health_map = await check_camera_gaps(memory_session, now=now)

    # Verify Cam 1
    h1 = health_map["CAM-ON-REC"]
    assert h1.online_state == OnlineState.ONLINE
    assert h1.recording_state == RecordingState.RECORDING
    assert h1.gap_alarm is False

    # Verify Cam 2: ONLINE but NOT RECORDING
    h2 = health_map["CAM-ON-NOTREC"]
    assert h2.online_state == OnlineState.ONLINE
    assert h2.recording_state == RecordingState.NOT_RECORDING
    assert h2.gap_alarm is True

    # Verify Cam 3: OFFLINE
    h3 = health_map["CAM-OFFLINE"]
    assert h3.online_state == OnlineState.OFFLINE
    assert h3.recording_state == RecordingState.NOT_RECORDING

    # Verify Cam 4: AUTH_FAILED
    h4 = health_map["CAM-AUTHFAIL"]
    assert h4.online_state == OnlineState.AUTH_FAILED
    assert h4.recording_state == RecordingState.NOT_RECORDING

    # Verify Cam 5: ONLINE + DISABLED
    h5 = health_map["CAM-DISABLED"]
    assert h5.online_state == OnlineState.ONLINE
    assert h5.recording_state == RecordingState.DISABLED
    assert h5.gap_alarm is False


@pytest.mark.asyncio
async def test_recorder_health_evaluation(memory_session: AsyncSession) -> None:
    """Recorder health evaluates healthy, degraded, and critical subsystems (HLTH-06)."""
    # 1. All healthy
    res_healthy = await RecorderHealthService.get_recorder_status(
        session=memory_session,
        media_status=True,
        storage_status=True,
        gap_count=0,
    )
    assert res_healthy.status == RecorderHealthStatus.HEALTHY
    assert res_healthy.db_ok is True
    assert res_healthy.mediamtx_ok is True
    assert res_healthy.storage_ok is True

    # 2. MediaMTX down -> DEGRADED
    res_media_down = await RecorderHealthService.get_recorder_status(
        session=memory_session,
        media_status=False,
        storage_status=True,
        gap_count=0,
    )
    assert res_media_down.status == RecorderHealthStatus.DEGRADED
    assert res_media_down.mediamtx_ok is False

    # 3. Storage full / unhealthy -> DEGRADED
    res_storage_down = await RecorderHealthService.get_recorder_status(
        session=memory_session,
        media_status=True,
        storage_status=StorageHealthState.FULL,
        gap_count=0,
    )
    assert res_storage_down.status == RecorderHealthStatus.DEGRADED
    assert res_storage_down.storage_ok is False

    # 4. Recording gaps active -> DEGRADED
    res_gaps = await RecorderHealthService.get_recorder_status(
        session=memory_session,
        media_status=True,
        storage_status=True,
        gap_count=2,
    )
    assert res_gaps.status == RecorderHealthStatus.DEGRADED

    # 5. Database uncontactable -> CRITICAL
    res_db_down = await RecorderHealthService.get_recorder_status(
        session=None,
        media_status=True,
        storage_status=True,
    )
    assert res_db_down.status == RecorderHealthStatus.CRITICAL
    assert res_db_down.db_ok is False
