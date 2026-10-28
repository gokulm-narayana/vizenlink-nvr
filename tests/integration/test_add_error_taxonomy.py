"""Integration tests for onboarding failure taxonomy, exit codes, and attempt bounds (CAM-03, ONB-02)."""

import asyncio
import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from fake_camera.faults import Malformed, Status
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.result import Timeout
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera


def get_free_port() -> int:
    """Find an unused ephemeral port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.behavior("CAM-03")
async def test_nothing_listening_yields_unreachable_exit_10(
    cli: CliRunner,
    tmp_path: Path,
) -> None:
    """Connecting to a port with nothing listening returns UNREACHABLE (10) and exact message."""
    free_port = get_free_port()

    result = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            "127.0.0.1",
            "--port",
            str(free_port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="some-password\n",
    )
    assert result.exit_code == ExitCode.UNREACHABLE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNREACHABLE"
    assert data["code"] == int(ExitCode.UNREACHABLE)
    assert "Could not reach the camera — check the connection and try again." in data["message"]


@pytest.mark.behavior("CAM-03")
async def test_identity_timeout_on_all_attempts_yields_unreachable_exit_10(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Identity probe timeout across all attempts returns UNREACHABLE (10)."""
    cam: FakeCamera = await fake_camera()

    with patch.object(NuraeyeClient, "are_you_nuraeye_device_with_retry", return_value=Timeout()):
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
            input="some-pass\n",
        )
    assert result.exit_code == ExitCode.UNREACHABLE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNREACHABLE"


@pytest.mark.behavior("CAM-03")
async def test_not_genuine_yields_unsupported_device_exit_12(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Non-genuine NuraEye device returns UNSUPPORTED_DEVICE (12)."""
    cam: FakeCamera = await fake_camera(genuine=False)

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
        input="some-pass\n",
    )
    assert result.exit_code == ExitCode.UNSUPPORTED_DEVICE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNSUPPORTED_DEVICE"
    assert "This device is not a VizenLink camera, or its firmware is not supported." in data["message"]


@pytest.mark.behavior("CAM-03")
async def test_identity_404_yields_unsupported_device_exit_12(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """HTTP 404 on identity probe returns UNSUPPORTED_DEVICE (12)."""
    cam: FakeCamera = await fake_camera()
    err_404 = Status(404, json_body={"error_code": 404, "error_msg": "Not found"})
    cam.faults.add("POST /nuraeye/identity", err_404, err_404, err_404)

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
        input="some-pass\n",
    )
    assert result.exit_code == ExitCode.UNSUPPORTED_DEVICE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNSUPPORTED_DEVICE"


@pytest.mark.behavior("CAM-03")
async def test_identity_malformed_yields_unsupported_device_exit_12(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Malformed body on identity probe returns UNSUPPORTED_DEVICE (12)."""
    cam: FakeCamera = await fake_camera()
    cam.faults.add("POST /nuraeye/identity", Malformed(), Malformed(), Malformed())

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
        input="some-pass\n",
    )
    assert result.exit_code == ExitCode.UNSUPPORTED_DEVICE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNSUPPORTED_DEVICE"


@pytest.mark.behavior("ONB-02")
async def test_wrong_password_yields_wrong_credentials_exit_11_lockout_safe(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Wrong password returns WRONG_CREDENTIALS (11) and burns exactly 2 login attempts."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-WRONG-01",
        accounts={"admin": Account("Correct-Owner-Pass", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # First login (factory probe) gets 401
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
        input="Wrong-Owner-Pass\n",
    )
    assert result.exit_code == ExitCode.WRONG_CREDENTIALS
    data = json.loads(result.stdout)
    assert data["kind"] == "WRONG_CREDENTIALS"
    assert data["message"] == "Incorrect username or password."

    # Exactly 2 login attempts for admin: 1 factory probe + 1 owner verification attempt
    assert cam.state.login_attempts.get("admin") == 2


@pytest.mark.behavior("ONB-02")
async def test_verification_429_yields_blocked_exit_14(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Verification 429 returns BLOCKED (14) with formatted retry duration."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-BLOCK-01",
        accounts={"admin": Account("Correct-Owner-Pass", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # 1. Factory probe gets 401
    # 2. Verification login gets 429 with 45 seconds retry_after
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        Status(
            429,
            json_body={"error_code": 429, "error_msg": "Too many requests", "retry_after_seconds": 45},
        ),
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
        input="Correct-Owner-Pass\n",
    )
    assert result.exit_code == ExitCode.BLOCKED
    data = json.loads(result.stdout)
    assert data["kind"] == "BLOCKED"
    assert "about a minute" in data["message"]


@pytest.mark.behavior("ONB-02")
async def test_factory_probe_429_yields_blocked_exit_14_without_prompt(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Factory probe 429 returns BLOCKED (14) immediately without consuming owner password."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-BLOCK-02")

    # Factory probe immediately gets 429
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(
            429,
            json_body={"error_code": 429, "error_msg": "Too many requests", "retry_after_seconds": 300},
        ),
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
        input="Unused-Pass\n",
    )
    assert result.exit_code == ExitCode.BLOCKED
    data = json.loads(result.stdout)
    assert data["kind"] == "BLOCKED"
    assert "about 5 minutes" in data["message"]


@pytest.mark.behavior("ONB-02")
async def test_verification_403_yields_forbidden_exit_18(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Verification 403 returns FORBIDDEN (18), not wrong credentials."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-FORBID-01",
        accounts={"admin": Account("Correct-Owner-Pass", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        Status(403, json_body={"error_code": 403, "error_msg": "Forbidden"}),
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
        input="Correct-Owner-Pass\n",
    )
    assert result.exit_code == ExitCode.FORBIDDEN
    data = json.loads(result.stdout)
    assert data["kind"] == "FORBIDDEN"
    assert data["code"] == int(ExitCode.FORBIDDEN)


@pytest.mark.behavior("ONB-02")
async def test_verification_timeout_yields_unreachable_exit_10(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Verification timeout returns UNREACHABLE (10)."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-TIMEOUT-01",
        accounts={"admin": Account("Correct-Owner-Pass", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # First login (factory probe) 401
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    with patch.object(NuraeyeClient, "login", side_effect=[Status(401), Timeout()]):
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
            input="Correct-Owner-Pass\n",
        )
    assert result.exit_code == ExitCode.UNREACHABLE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNREACHABLE"


@pytest.mark.behavior("CAM-03")
async def test_verification_503_firmware_upgrade_yields_unreachable_exit_10(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """HTTP 503 during verification returns UNREACHABLE (10) with firmware upgrade detail."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-503-01",
        accounts={"admin": Account("Correct-Owner-Pass", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # Factory probe returns 401, verification returns 503
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        Status(503, json_body={"error_code": 503, "error_msg": "Firmware upgrade in progress"}),
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
        input="Correct-Owner-Pass\n",
    )
    assert result.exit_code == ExitCode.UNREACHABLE
    data = json.loads(result.stdout)
    assert data["kind"] == "UNREACHABLE"
    assert "upgrading" in data["detail"].lower() or "firmware" in data["detail"].lower()


@pytest.mark.behavior("CAM-03")
async def test_empty_serial_yields_no_serial_exit_15(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Empty serial number reports NO_SERIAL (15)."""
    cam: FakeCamera = await fake_camera(serial="")

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
        input="some-pass\n",
    )
    assert result.exit_code == ExitCode.NO_SERIAL
    data = json.loads(result.stdout)
    assert data["kind"] == "NO_SERIAL"
    assert "did not report a serial number" in data["message"]


@pytest.mark.behavior("CAM-03")
async def test_missing_media2_yields_streams_unavailable_exit_16(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Missing or failing Media2 service returns STREAMS_UNAVAILABLE (16)."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-STREAMS-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # Factory probe 401
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # Inject fault on GetProfiles
    cam.faults.add(
        "POST /onvif/media2_service",
        Status(500, json_body={"error": "Media2 service unavailable"}),
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
    assert result.exit_code == ExitCode.STREAMS_UNAVAILABLE
    data = json.loads(result.stdout)
    assert data["kind"] == "STREAMS_UNAVAILABLE"


@pytest.mark.behavior("CAM-03")
async def test_already_registered_exit_17_and_address_updated_exit_0(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Duplicate add at same host:port returns ALREADY_REGISTERED (17); different port updates host (0)."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-DUP-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # 1. Onboard initial camera
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )
    res1 = await asyncio.to_thread(
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
    assert res1.exit_code == 0

    # 2. Add same camera at same host and port -> ALREADY_REGISTERED (17)
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )
    res2 = await asyncio.to_thread(
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
    assert res2.exit_code == ExitCode.ALREADY_REGISTERED
    data2 = json.loads(res2.stdout)
    assert data2["kind"] == "ALREADY_REGISTERED"

    # 3. Add same serial at new port (simulated by second instance with same serial) -> ADDRESS_UPDATED (0)
    cam2: FakeCamera = await fake_camera(
        serial="VZL-CAM-DUP-01",
        accounts={"admin": Account("Admin-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam2.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )
    res3 = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam2.host,
            "--port",
            str(cam2.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Admin-Pass-01\n",
    )
    assert res3.exit_code == 0
    data3 = json.loads(res3.stdout)
    assert data3["serial"] == "VZL-CAM-DUP-01"
    assert data3["https_port"] == cam2.port

    # Verify exactly 1 camera row remains in DB with updated port
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        res = await conn.execute(select(Camera))
        cameras = res.fetchall()
        assert len(cameras) == 1
        assert cameras[0].https_port == cam2.port
    await engine.dispose()
