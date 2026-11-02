"""Integration tests for nvr cameras remove with keep vs delete recordings (CAM-09)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import Camera, Segment
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
def seeded_env(tmp_path: Path, cli: CliRunner) -> tuple[Path, Path]:
    """Initialize database and create sample camera with recording segments."""
    data_dir = tmp_path / "nvr_cam_remove_data"
    rec_dir = data_dir / "recordings"

    # Initialize DB migrations
    init_res = cli.invoke(app, ["status", "--data-dir", str(data_dir)])
    assert init_res.exit_code == 0, init_res.output

    settings = load_settings(data_dir=data_dir)

    async def _seed() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                now = utc_now()
                # Create cameras
                cam1 = Camera(
                    serial="CAM-KEEP-01",
                    host="192.168.1.10",
                    https_port=443,
                    mac="AA:BB:CC:11:22:33",
                    name="Keep Camera",
                    location="Front Door",
                    group_tag="front",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    firmware_version="v2.1.0",
                    hardware_id="HW-KEEP-01",
                    tls_fingerprint_sha256="sha256_keep_01",
                    camera_id_check=True,
                    added_at=now,
                    host_updated_at=now,
                )
                cam2 = Camera(
                    serial="CAM-DEL-02",
                    host="192.168.1.11",
                    https_port=443,
                    mac="AA:BB:CC:11:22:44",
                    name="Delete Camera",
                    location="Back Door",
                    group_tag="back",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    firmware_version="v2.1.0",
                    hardware_id="HW-DEL-02",
                    tls_fingerprint_sha256="sha256_del_02",
                    camera_id_check=True,
                    added_at=now,
                    host_updated_at=now,
                )
                session.add(cam1)
                session.add(cam2)
                await session.flush()

                # Create segments for both cameras
                seg1_file = rec_dir / "cam" / "cam-keep-01" / "main" / "seg1.mp4"
                seg1_file.parent.mkdir(parents=True, exist_ok=True)
                seg1_file.write_bytes(b"\x00" * 4096)

                seg1 = Segment(
                    camera_serial="CAM-KEEP-01",
                    stream_type="main",
                    file_path=str(seg1_file),
                    start_time=now,
                    end_time=now + timedelta(seconds=60),
                    duration_seconds=60.0,
                    file_size_bytes=4096,
                    status="active",
                    is_protected=False,
                    created_at=now,
                )
                session.add(seg1)

                seg2_file = rec_dir / "cam" / "cam-del-02" / "main" / "seg2.mp4"
                seg2_file.parent.mkdir(parents=True, exist_ok=True)
                seg2_file.write_bytes(b"\x00" * 4096)

                seg2 = Segment(
                    camera_serial="CAM-DEL-02",
                    stream_type="main",
                    file_path=str(seg2_file),
                    start_time=now,
                    end_time=now + timedelta(seconds=60),
                    duration_seconds=60.0,
                    file_size_bytes=4096,
                    status="active",
                    is_protected=False,
                    created_at=now,
                )
                session.add(seg2)
                await session.commit()

    import asyncio

    asyncio.run(_seed())
    return data_dir, rec_dir


def test_remove_missing_flag_fails(cli: CliRunner, seeded_env: tuple[Path, Path]) -> None:
    """nvr cameras remove fails if neither --keep-recordings nor --delete-recordings is specified."""
    data_dir, _ = seeded_env
    res = cli.invoke(
        app,
        ["cameras", "remove", "--serial", "CAM-KEEP-01", "--data-dir", str(data_dir)],
    )
    assert res.exit_code == int(ExitCode.INVALID_INPUT), res.output
    assert "Must specify either --keep-recordings or --delete-recordings" in res.output


def test_remove_conflicting_flags_fails(cli: CliRunner, seeded_env: tuple[Path, Path]) -> None:
    """nvr cameras remove fails if both --keep-recordings and --delete-recordings are specified."""
    data_dir, _ = seeded_env
    res = cli.invoke(
        app,
        [
            "cameras",
            "remove",
            "--serial",
            "CAM-KEEP-01",
            "--keep-recordings",
            "--delete-recordings",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res.exit_code == int(ExitCode.INVALID_INPUT), res.output
    assert "Must specify either --keep-recordings or --delete-recordings" in res.output


def test_remove_nonexistent_camera_fails(cli: CliRunner, seeded_env: tuple[Path, Path]) -> None:
    """nvr cameras remove fails when camera serial is not found in database."""
    data_dir, _ = seeded_env
    res = cli.invoke(
        app,
        [
            "cameras",
            "remove",
            "--serial",
            "NONEXISTENT",
            "--keep-recordings",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res.exit_code == int(ExitCode.NOT_FOUND), res.output
    assert "not found in registry" in res.output


def test_remove_keep_recordings(cli: CliRunner, seeded_env: tuple[Path, Path]) -> None:
    """nvr cameras remove --keep-recordings removes camera from DB but preserves segment files on disk."""
    data_dir, rec_dir = seeded_env
    seg_file = rec_dir / "cam" / "cam-keep-01" / "main" / "seg1.mp4"
    assert seg_file.exists()

    res = cli.invoke(
        app,
        [
            "cameras",
            "remove",
            "--serial",
            "CAM-KEEP-01",
            "--keep-recordings",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "successfully removed" in res.output
    assert "preserved on disk" in res.output

    # File on disk MUST still exist
    assert seg_file.exists()

    # Verify camera row is gone from DB
    settings = load_settings(data_dir=data_dir)

    async def _verify() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                cam = await session.get(Camera, "CAM-KEEP-01")
                assert cam is None

    import asyncio

    asyncio.run(_verify())


def test_remove_delete_recordings(cli: CliRunner, seeded_env: tuple[Path, Path]) -> None:
    """nvr cameras remove --delete-recordings removes camera and purges recording files on disk."""
    data_dir, rec_dir = seeded_env
    seg_file = rec_dir / "cam" / "cam-del-02" / "main" / "seg2.mp4"
    assert seg_file.exists()

    res = cli.invoke(
        app,
        [
            "cameras",
            "remove",
            "--serial",
            "CAM-DEL-02",
            "--delete-recordings",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "successfully removed" in res.output
    assert "purged" in res.output

    # File on disk MUST be deleted
    assert not seg_file.exists()

    # Camera directory should be deleted
    assert not (rec_dir / "cam" / "cam-del-02").exists()

    # Verify camera row is gone from DB
    settings = load_settings(data_dir=data_dir)

    async def _verify() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                cam = await session.get(Camera, "CAM-DEL-02")
                assert cam is None

    import asyncio

    asyncio.run(_verify())


def test_remove_json_output(cli: CliRunner, tmp_path: Path) -> None:
    """nvr cameras remove --json emits structured JSON payload."""
    data_dir = tmp_path / "nvr_json_data"
    cli.invoke(app, ["status", "--data-dir", str(data_dir)])
    settings = load_settings(data_dir=data_dir)

    async def _seed() -> None:
        async with open_runtime(settings) as rt:
            async with rt.sessions() as session:
                now = utc_now()
                cam = Camera(
                    serial="CAM-JSON-01",
                    host="192.168.1.15",
                    https_port=443,
                    mac="AA:BB:CC:99:88:77",
                    name="JSON Cam",
                    location="Lab",
                    group_tag="lab",
                    manufacturer="NuraEye",
                    model="NE-4K",
                    firmware_version="v2.1.0",
                    hardware_id="HW-JSON-01",
                    tls_fingerprint_sha256="sha256_json",
                    camera_id_check=True,
                    added_at=now,
                    host_updated_at=now,
                )
                session.add(cam)
                await session.commit()

    import asyncio

    asyncio.run(_seed())

    res = cli.invoke(
        app,
        [
            "cameras",
            "remove",
            "--serial",
            "CAM-JSON-01",
            "--keep-recordings",
            "--json",
            "--data-dir",
            str(data_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["serial"] == "CAM-JSON-01"
    assert data["removed"] is True
    assert data["recordings_deleted"] is False
    assert data["deleted_files_count"] == 0
