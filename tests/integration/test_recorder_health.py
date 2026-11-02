"""Integration tests for recorder health evaluation and dual camera badges (HLTH-01, HLTH-06)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.status import (
    evaluate_system_recorder_health,
    render_recorder_status_table,
)
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, RecordingSettings, Segment
from vizenlink_nvr.services.health import (
    OnlineState,
    RecorderHealthStatus,
    RecordingState,
)
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
def recorder_env(tmp_path: Path, cli: CliRunner) -> Path:
    """Initialize test environment with seeded cameras representing diverse health states."""
    data_dir = tmp_path / "nvr_recorder_health_data"
    rec_dir = data_dir / "recordings"

    # Initialize DB migrations
    init_res = cli.invoke(app, ["status", "--data-dir", str(data_dir)])
    assert init_res.exit_code == 0, init_res.output

    settings = load_settings(data_dir=data_dir)

    async def _seed() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                now = utc_now()
                # 1. Healthy online camera recording normally
                cam1 = Camera(
                    serial="CAM-NORMAL",
                    host="192.168.1.10",
                    https_port=443,
                    mac="AA:BB:CC:10:10:10",
                    name="Normal Cam",
                    location="Front Yard",
                    group_tag="front",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    tls_fingerprint_sha256="fp_normal",
                    state="active",
                    added_at=now - timedelta(hours=1),
                    host_updated_at=now,
                )
                seg1 = Segment(
                    camera_serial="CAM-NORMAL",
                    stream_type="main",
                    file_path=str(rec_dir / "cam1.mp4"),
                    start_time=now - timedelta(seconds=70),
                    end_time=now - timedelta(seconds=10),  # recent (10s ago)
                    duration_seconds=60.0,
                    file_size_bytes=4096,
                    status="active",
                    created_at=now,
                )

                # 2. Online camera with stream drop / gap (>150s)
                cam2 = Camera(
                    serial="CAM-GAP",
                    host="192.168.1.11",
                    https_port=443,
                    mac="AA:BB:CC:11:11:11",
                    name="Gap Cam",
                    location="Back Yard",
                    group_tag="back",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    tls_fingerprint_sha256="fp_gap",
                    state="active",
                    added_at=now - timedelta(hours=1),
                    host_updated_at=now,
                )
                seg2 = Segment(
                    camera_serial="CAM-GAP",
                    stream_type="main",
                    file_path=str(rec_dir / "cam2.mp4"),
                    start_time=now - timedelta(seconds=300),
                    end_time=now - timedelta(seconds=240),  # 240s ago (>150s)
                    duration_seconds=60.0,
                    file_size_bytes=4096,
                    status="active",
                    created_at=now,
                )

                # 3. Offline camera
                cam3 = Camera(
                    serial="CAM-OFFLINE",
                    host="192.168.1.12",
                    https_port=443,
                    mac="AA:BB:CC:12:12:12",
                    name="Offline Cam",
                    location="Side Garage",
                    group_tag="garage",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    tls_fingerprint_sha256="fp_offline",
                    state="unreachable",
                    added_at=now - timedelta(hours=1),
                    host_updated_at=now,
                )

                # 4. Camera with recording disabled
                cam4 = Camera(
                    serial="CAM-DISABLED",
                    host="192.168.1.13",
                    https_port=443,
                    mac="AA:BB:CC:13:13:13",
                    name="Disabled Cam",
                    location="Storage Room",
                    group_tag="storage",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    tls_fingerprint_sha256="fp_disabled",
                    state="active",
                    added_at=now - timedelta(hours=1),
                    host_updated_at=now,
                )
                settings4 = RecordingSettings(
                    camera_serial="CAM-DISABLED",
                    mode="off",
                    created_at=now,
                    updated_at=now,
                )

                session.add_all([cam1, seg1, cam2, seg2, cam3, cam4, settings4])
                await session.commit()

    import asyncio

    asyncio.run(_seed())
    return data_dir


def test_cli_recording_status_human(cli: CliRunner, recorder_env: Path) -> None:
    """nvr recording status prints rich table with dual badges and gap alarms."""
    res = cli.invoke(app, ["recording", "status", "--data-dir", str(recorder_env)])
    assert res.exit_code == 0, res.output
    assert "Camera Recording & Health Status" in res.output
    assert "CAM-NORMAL" in res.output
    assert "CAM-GAP" in res.output
    assert "CAM-OFFLINE" in res.output
    assert "CAM-DISABLED" in res.output

    # Check badges
    assert "ONLINE" in res.output
    assert "OFFLINE" in res.output
    assert "RECORDI" in res.output
    assert "DISABLED" in res.output
    assert "ALARM" in res.output


def test_cli_recording_status_json(cli: CliRunner, recorder_env: Path) -> None:
    """nvr recording status --json emits structured per-camera health data (HLTH-01)."""
    res = cli.invoke(app, ["recording", "status", "--json", "--data-dir", str(recorder_env)])
    assert res.exit_code == 0, res.output

    data = json.loads(res.stdout)
    assert "cameras" in data
    cam_map = {c["camera_serial"]: c for c in data["cameras"]}

    # Cam 1: Online + Recording
    c1 = cam_map["CAM-NORMAL"]
    assert c1["online_state"] == OnlineState.ONLINE
    assert c1["recording_state"] == RecordingState.RECORDING
    assert c1["gap_alarm"] is False

    # Cam 2: Online + Not Recording (HLTH-01 proof)
    c2 = cam_map["CAM-GAP"]
    assert c2["online_state"] == OnlineState.ONLINE
    assert c2["recording_state"] == RecordingState.NOT_RECORDING
    assert c2["gap_alarm"] is True

    # Cam 3: Offline + Not Recording
    c3 = cam_map["CAM-OFFLINE"]
    assert c3["online_state"] == OnlineState.OFFLINE
    assert c3["recording_state"] == RecordingState.NOT_RECORDING

    # Cam 4: Online + Disabled
    c4 = cam_map["CAM-DISABLED"]
    assert c4["online_state"] == OnlineState.ONLINE
    assert c4["recording_state"] == RecordingState.DISABLED
    assert c4["gap_alarm"] is False


@pytest.mark.asyncio
async def test_recorder_degraded_state(recorder_env: Path) -> None:
    """Recorder health returns DEGRADED when MediaMTX is down or gaps exist (HLTH-06)."""
    settings = load_settings(data_dir=recorder_env)

    # 1. When MediaMTX is explicitly down
    status_media_down = await evaluate_system_recorder_health(settings, mediamtx_alive=False)
    assert status_media_down.status == RecorderHealthStatus.DEGRADED
    assert status_media_down.mediamtx_ok is False

    # 2. Render helper outputs table without errors
    render_recorder_status_table(status_media_down)
