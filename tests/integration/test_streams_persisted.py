"""Integration tests for persisted stream metadata, stream_url, and D-23 fallback (CAM-07, LST-04)."""

import asyncio
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.routes.rest_session import rest_settings
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraStream
from vizenlink_nvr.services.registry import get_camera, stream_url


@pytest.mark.behavior("LST-04")
async def test_streams_persisted_clean_columns_and_stream_url(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Default camera stores H265 streams with clean paths, ports 554/555; builds clean rtsps URL."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-STREAMS-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    result = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam.host,
            "--port",
            str(cam.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Admin-Pass-01\n",
    )
    assert result.exit_code == 0, f"Add failed: {result.output}"

    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        stmt = select(CameraStream).where(CameraStream.serial == "VZL-STREAMS-01").order_by(CameraStream.role)
        stream_rows = (await conn.execute(stmt)).fetchall()
        assert len(stream_rows) == 2

        # Check no stream column contains "@" or "://"
        for row in stream_rows:
            assert "@" not in row.path
            assert "://" not in row.path
            assert "@" not in row.scheme
            assert "://" not in row.scheme
            assert row.codec.upper() in ("H265", "HEVC")

        main_row = next(r for r in stream_rows if r.role == "main")
        sub_row = next(r for r in stream_rows if r.role == "sub")

        assert main_row.port == 554
        assert main_row.path == "/high"
        assert sub_row.port == 555
        assert sub_row.path == "/medium"

    # Test stream_url helper
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        cam_view = await get_camera(session, "VZL-STREAMS-01")
        assert cam_view is not None
        main_stream = next(s for s in cam_view.streams if s.role == "main")
        url = stream_url(cam_view, main_stream)
        assert url == f"rtsps://{cam.host}:554/high"
        assert "@" not in url

    await engine.dispose()


@pytest.mark.behavior("LST-04")
async def test_webrtc_fallback_to_onvif_media2(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Camera in WebRTC mode triggers D-23 fallback: both streams stored with source 'onvif_fallback'."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-WEBRTC-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # Configure camera to report webrtc transport
    rest_settings(cam).live_stream_mode = "webrtc"

    result = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam.host,
            "--port",
            str(cam.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Admin-Pass-01\n",
    )
    assert result.exit_code == 0, f"Add failed: {result.output}"

    # Verify both stream rows in DB have source onvif_fallback and transport rtsp
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        stream_rows = (
            await conn.execute(select(CameraStream).where(CameraStream.serial == "VZL-WEBRTC-01"))
        ).fetchall()
        assert len(stream_rows) == 2
        for s in stream_rows:
            assert s.source == "onvif_fallback"
            assert s.transport == "rtsp"
            assert s.port == 554
            assert s.path == "/high"
    await engine.dispose()


@pytest.mark.behavior("LST-04")
async def test_webrtc_fallback_get_stream_uri_failure_returns_streams_unavailable(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """When WebRTC fallback occurs but GetStreamUri fails, add returns STREAMS_UNAVAILABLE and zero rows."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-FAIL-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    rest_settings(cam).live_stream_mode = "webrtc"

    # Fault on ONVIF media2 service GetStreamUri
    cam.faults.add(
        "POST /onvif/media2_service",
        Status(500, json_body={"error": "media2 failed"}),
    )

    result = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam.host,
            "--port",
            str(cam.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Admin-Pass-01\n",
    )
    assert result.exit_code == int(ExitCode.STREAMS_UNAVAILABLE)

    # Zero rows in DB
    db_file = tmp_path / "nvr.db"
    if db_file.exists():
        engine = create_engine_for(db_file)
        async with engine.connect() as conn:
            cam_rows = (await conn.execute(select(Camera))).fetchall()
            assert len(cam_rows) == 0
        await engine.dispose()
