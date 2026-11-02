"""Integration tests for nvr recording CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
def seeded_data_dir(tmp_path: Path, cli: CliRunner) -> Path:
    """Initialize NVR database with cameras for CLI integration tests."""
    data_dir = tmp_path / "nvr_cli_recording"
    # Run status command to trigger database creation and schema migrations
    init_res = cli.invoke(app, ["status", "--data-dir", str(data_dir)])
    assert init_res.exit_code == 0, init_res.output

    settings = load_settings(data_dir=data_dir)

    async def _seed() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                now = utc_now()
                cam1 = Camera(
                    serial="VZL-CAM-TEST1",
                    host="192.168.1.100",
                    https_port=443,
                    mac="AA:BB:CC:DD:EE:01",
                    name="Test Camera 1",
                    location="Front Entrance",
                    group_tag="front",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    firmware_version="v2.1.0",
                    hardware_id="HW-01",
                    tls_fingerprint_sha256="abc",
                    camera_id_check=True,
                    added_at=now,
                    host_updated_at=now,
                )
                session.add(cam1)

                cam_mute = Camera(
                    serial="VZL-CAM-MUTE",
                    host="192.168.1.102",
                    https_port=443,
                    mac="AA:BB:CC:DD:EE:02",
                    name="Mute Camera",
                    location="Back Yard",
                    group_tag="back",
                    manufacturer="NuraEye",
                    model="NE-2K",
                    firmware_version="v1.0.0",
                    hardware_id="HW-02",
                    tls_fingerprint_sha256="def",
                    camera_id_check=False,
                    added_at=now,
                    host_updated_at=now,
                )
                session.add(cam_mute)

                caps_mute = CameraCapabilitiesRow(
                    serial="VZL-CAM-MUTE",
                    raw_json=json.dumps({"audio_capable": False}),
                    probed_at=now,
                    firmware_version_at_probe="v1.0.0",
                )
                session.add(caps_mute)

                await session.commit()

    import asyncio

    asyncio.run(_seed())
    return data_dir


def test_cli_recording_set_mode(cli: CliRunner, seeded_data_dir: Path) -> None:
    """Test nvr recording set-mode updates mode and reports status."""
    # 1. Update mode to scheduled
    res = cli.invoke(
        app,
        [
            "recording",
            "set-mode",
            "--serial",
            "VZL-CAM-TEST1",
            "--mode",
            "scheduled",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "scheduled" in res.output

    # 2. Update mode with --json
    res_json = cli.invoke(
        app,
        [
            "recording",
            "set-mode",
            "--serial",
            "VZL-CAM-TEST1",
            "--mode",
            "event",
            "--json",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_json.exit_code == 0, res_json.output
    data = json.loads(res_json.stdout)
    assert data["camera_serial"] == "VZL-CAM-TEST1"
    assert data["mode"] == "event"

    # 3. Invalid mode rejected
    res_inv = cli.invoke(
        app,
        [
            "recording",
            "set-mode",
            "--serial",
            "VZL-CAM-TEST1",
            "--mode",
            "invalid_mode",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_inv.exit_code == int(ExitCode.INVALID_INPUT)

    # 4. Unknown camera serial fails with NOT_FOUND
    res_nf = cli.invoke(
        app,
        [
            "recording",
            "set-mode",
            "--serial",
            "VZL-CAM-UNKNOWN",
            "--mode",
            "continuous",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_nf.exit_code == int(ExitCode.NOT_FOUND)


def test_cli_recording_set_schedule(cli: CliRunner, seeded_data_dir: Path) -> None:
    """Test nvr recording set-schedule updates schedule with presets and custom specs."""
    # Preset
    res = cli.invoke(
        app,
        [
            "recording",
            "set-schedule",
            "--serial",
            "VZL-CAM-TEST1",
            "--schedule",
            "business_hours",
            "--json",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    sched = json.loads(data["schedule_json"])
    assert "monday" in sched

    # Invalid preset
    res_inv = cli.invoke(
        app,
        [
            "recording",
            "set-schedule",
            "--serial",
            "VZL-CAM-TEST1",
            "--schedule",
            "not_a_schedule",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_inv.exit_code == int(ExitCode.INVALID_INPUT)


def test_cli_recording_set_audio(cli: CliRunner, seeded_data_dir: Path) -> None:
    """Test nvr recording set-audio toggles audio and validates camera capabilities."""
    # Enable audio on supported camera
    res_on = cli.invoke(
        app,
        [
            "recording",
            "set-audio",
            "--serial",
            "VZL-CAM-TEST1",
            "--enabled",
            "--json",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_on.exit_code == 0, res_on.output
    data = json.loads(res_on.stdout)
    assert data["audio_enabled"] is True

    # Disable audio
    res_off = cli.invoke(
        app,
        [
            "recording",
            "set-audio",
            "--serial",
            "VZL-CAM-TEST1",
            "--disabled",
            "--json",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_off.exit_code == 0, res_off.output
    data_off = json.loads(res_off.stdout)
    assert data_off["audio_enabled"] is False

    # Refuse enabling audio on camera with no audio hardware capability
    res_refuse = cli.invoke(
        app,
        [
            "recording",
            "set-audio",
            "--serial",
            "VZL-CAM-MUTE",
            "--enabled",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_refuse.exit_code == int(ExitCode.INVALID_INPUT)
    assert "does not support audio" in res_refuse.output


def test_cli_recording_set_retention(cli: CliRunner, seeded_data_dir: Path) -> None:
    """Test nvr recording set-retention configures limits."""
    res = cli.invoke(
        app,
        [
            "recording",
            "set-retention",
            "--serial",
            "VZL-CAM-TEST1",
            "--days",
            "14",
            "--max-gb",
            "50",
            "--json",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["retention_days"] == 14
    assert data["retention_max_gb"] == 50

    # Negative value rejected
    res_neg = cli.invoke(
        app,
        [
            "recording",
            "set-retention",
            "--serial",
            "VZL-CAM-TEST1",
            "--days",
            "-1",
            "--data-dir",
            str(seeded_data_dir),
        ],
    )
    assert res_neg.exit_code == int(ExitCode.INVALID_INPUT)


def test_cli_recording_positional_rejected(cli: CliRunner, seeded_data_dir: Path) -> None:
    """Assert positional parameters are rejected (D-16)."""
    res = cli.invoke(
        app,
        ["recording", "set-mode", "VZL-CAM-TEST1", "continuous", "--data-dir", str(seeded_data_dir)],
    )
    assert res.exit_code != 0
    assert "Got unexpected extra argument" in res.output or "Error" in res.output
