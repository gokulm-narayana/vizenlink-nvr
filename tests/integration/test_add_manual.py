"""Integration tests for manual camera onboarding via CLI (CAM-02, CAM-10, ONB-03, D-11)."""

import asyncio
import json
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow, CameraCredential, CameraStream


@pytest.mark.behavior("ONB-03")
async def test_tracer_add_manual_configured_camera(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Configured camera onboarded with blank serial binding, verified capabilities, and stored rows."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-000001",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # First login attempt is factory probe with "password"; configured camera returns 401
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # 1. Onboard camera using CLI with hidden stdin password
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
    assert result.exit_code == 0, f"Onboarding failed: {result.output}"

    # Verify JSON output
    data = json.loads(result.stdout)
    assert data["serial"] == "VZL-CAM-000001"
    assert "streams" in data
    assert len(data["streams"]) == 2

    # 2. Verify database records: 1 camera, 1 credential, 1 capabilities, 2 streams
    db_file = tmp_path / "nvr.db"
    assert db_file.exists()
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        cam_rows = (await conn.execute(select(Camera))).fetchall()
        assert len(cam_rows) == 1
        assert cam_rows[0].serial == "VZL-CAM-000001"

        cred_rows = (await conn.execute(select(CameraCredential))).fetchall()
        assert len(cred_rows) == 1
        assert cred_rows[0].serial == "VZL-CAM-000001"
        assert cred_rows[0].username == "admin"
        assert cred_rows[0].ciphertext != b""

        cap_rows = (await conn.execute(select(CameraCapabilitiesRow))).fetchall()
        assert len(cap_rows) == 1
        assert cap_rows[0].serial == "VZL-CAM-000001"

        stream_rows = (await conn.execute(select(CameraStream))).fetchall()
        assert len(stream_rows) == 2
        roles = {s.role for s in stream_rows}
        assert roles == {"main", "sub"}
    await engine.dispose()

    # 3. cameras show returns the same camera
    show_result = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "show",
            "--serial",
            "VZL-CAM-000001",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert show_result.exit_code == 0, f"Show failed: {show_result.output}"
    show_data = json.loads(show_result.stdout)
    assert show_data["serial"] == "VZL-CAM-000001"

    # 4. Simulation assertions
    # Exactly two login attempts for admin (one factory probe, one verification)
    login_reqs = [r for r in cam.requests if r.method == "POST" and r.path == "/nuraeye/session/login"]
    assert len(login_reqs) == 2

    # Pre-verification GetDeviceInformation serial read used blank credentials only
    dev_info_reqs = [
        r for r in cam.requests if r.path == "/onvif/device_service" and b"GetDeviceInformation" in r.body
    ]
    assert len(dev_info_reqs) >= 1
    # First GetDeviceInformation request had blank credentials
    assert dev_info_reqs[0].credential_use in ("blank", "none")

    # Verification is GET /nuraeye/capabilities
    cap_reqs = [r for r in cam.requests if r.method == "GET" and r.path == "/nuraeye/capabilities"]
    assert len(cap_reqs) >= 1

    # Every credential-bearing request carried exact-case X-VizenLink-Camera-Id
    cred_reqs = cam.requests_with_credentials()
    assert len(cred_reqs) > 0
    for r in cred_reqs:
        assert b"X-VizenLink-Camera-Id" in r.raw_header_names
        header_val = next(v for k, v in r.headers if k == b"X-VizenLink-Camera-Id")
        assert header_val == b"VZL-CAM-000001"

    # 5. CLI rejects --password option
    bad_opt_result = await asyncio.to_thread(
        cli.invoke,
        app,
        ["cameras", "add", "--host", "127.0.0.1", "--password", "Secret"],
    )
    assert bad_opt_result.exit_code != 0
    assert "no such option" in bad_opt_result.output.lower() or "error" in bad_opt_result.output.lower()


@pytest.mark.behavior("ONB-03")
async def test_missing_blank_serial_yields_no_serial_and_zero_logins(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Camera with empty serial aborts with NO_SERIAL and attempts zero logins."""
    cam: FakeCamera = await fake_camera(
        serial="",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
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
    assert result.exit_code == int(ExitCode.NO_SERIAL)

    # Zero login attempts
    assert cam.state.login_attempts.get("admin", 0) == 0

    # Zero credential-bearing requests
    assert len(cam.requests_with_credentials()) == 0


@pytest.mark.behavior("ONB-03")
async def test_swapped_simulator_serial_yields_421(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Simulator serial mismatch on factory probe aborts before owner authentication with zero rows."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-000001",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # Factory probe with bound serial yields 421 due to serial mismatch
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(421, json_body={"error_code": 421, "error_msg": "Camera ID mismatch"}),
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
    # Aborts before requesting or sending owner credentials
    assert result.exit_code != 0

    # Only factory probe occurred; owner credentials were never requested or disclosed
    login_reqs = [r for r in cam.requests if r.method == "POST" and r.path == "/nuraeye/session/login"]
    assert len(login_reqs) == 1

    # Zero database rows inserted
    db_file = tmp_path / "nvr.db"
    if db_file.exists():
        engine = create_engine_for(db_file)
        async with engine.connect() as conn:
            cam_rows = (await conn.execute(select(Camera))).fetchall()
            assert len(cam_rows) == 0
        await engine.dispose()


@pytest.mark.behavior("ONB-03")
async def test_wrong_password_fails_via_capabilities(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Wrong password fails credential verification; GetDeviceInformation success does not onboard."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-000001",
        accounts={"admin": Account("Correct-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # First login attempt is factory probe with "password"; configured camera returns 401
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
        input="Wrong-Password\n",
    )
    assert result.exit_code == int(ExitCode.WRONG_CREDENTIALS)

    # Zero database rows inserted
    db_file = tmp_path / "nvr.db"
    if db_file.exists():
        engine = create_engine_for(db_file)
        async with engine.connect() as conn:
            cam_rows = (await conn.execute(select(Camera))).fetchall()
            assert len(cam_rows) == 0
        await engine.dispose()
