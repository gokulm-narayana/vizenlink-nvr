"""Integration tests for one-shot factory password flow (ONB-01)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select
from typer.testing import CliRunner

from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.result import Timeout
from vizenlink_nvr.camera.wsse import compute_digest
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera


@pytest.mark.behavior("ONB-01")
async def test_factory_password_forced_change_and_onboard(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Factory-fresh camera requires new password, sets it via SetUser, verifies, and onboards."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-FACTORY-01",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
    )

    # Human CLI invoke with stdin providing new password twice
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
            "--data-dir",
            str(tmp_path),
        ],
        input="N3w-Camera-Pass\nN3w-Camera-Pass\n",
    )
    assert result.exit_code == 0, f"Onboarding failed: {result.output}"

    # Notice displayed to owner
    assert "Use this new password in the VizenLink mobile app too." in result.output

    # Simulator admin password updated and gates cleared
    assert cam.state.accounts["admin"].password == "N3w-Camera-Pass"
    assert cam.state.first_password_gate is False
    assert cam.state.default_password_in_use is False

    # Check recorded login requests
    login_reqs = [r for r in cam.requests if r.method == "POST" and r.path == "/nuraeye/session/login"]
    assert len(login_reqs) == 2, f"Expected 2 login attempts, got {len(login_reqs)}"

    factory_attempts = 0
    new_pw_attempts = 0

    for req in login_reqs:
        body = json.loads(req.body.decode("utf-8"))
        auth = body["auth_credentials"]
        nonce = auth["nonce"]
        created = auth["created"]
        digest = auth.get("password_digest") or auth.get("digest")

        expected_factory = compute_digest("password", nonce_b64=nonce, created=created)
        expected_new = compute_digest("N3w-Camera-Pass", nonce_b64=nonce, created=created)

        if digest == expected_factory:
            factory_attempts += 1
        elif digest == expected_new:
            new_pw_attempts += 1

    # Exactly one factory login attempt and one new password verification attempt
    assert factory_attempts == 1
    assert new_pw_attempts == 1

    # SetUser was called
    set_user_reqs = [r for r in cam.requests if b"SetUser" in r.body]
    assert len(set_user_reqs) == 1

    # Database has exactly 1 camera row
    db_file = tmp_path / "nvr.db"
    assert db_file.exists()
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        res = await conn.execute(select(Camera))
        cameras = res.fetchall()
        assert len(cameras) == 1
        assert cameras[0].serial == "VZL-CAM-FACTORY-01"
    await engine.dispose()


@pytest.mark.behavior("ONB-01")
async def test_mismatched_confirmation_aborts_without_set_user(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Mismatched confirmation exits with INVALID_INPUT (20) and sends no SetUser."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-FACTORY-02",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
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
            "--data-dir",
            str(tmp_path),
        ],
        input="N3w-Camera-Pass\nMismatched-Pass\n",
    )
    assert result.exit_code == ExitCode.INVALID_INPUT

    # Password on camera unchanged
    assert cam.state.accounts["admin"].password == "password"

    # No SetUser was sent
    set_user_reqs = [r for r in cam.requests if b"SetUser" in r.body]
    assert len(set_user_reqs) == 0


@pytest.mark.behavior("ONB-01")
async def test_rule_violation_aborts_without_set_user(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Password rule violation (e.g. factory word or short) exits with INVALID_INPUT and sends no SetUser."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-FACTORY-03",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
    )

    # Submitting "PassWord" (violates factory password rule)
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
            "--data-dir",
            str(tmp_path),
        ],
        input="PassWord\nPassWord\n",
    )
    assert result.exit_code == ExitCode.INVALID_INPUT

    # No SetUser sent and camera password unchanged
    assert cam.state.accounts["admin"].password == "password"
    set_user_reqs = [r for r in cam.requests if b"SetUser" in r.body]
    assert len(set_user_reqs) == 0


@pytest.mark.behavior("ONB-01")
async def test_dev_build_without_gate_still_treated_as_factory(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Dev build camera (admin/'password', password_change_required=False)
    still forces password change (F13).
    """
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-DEV-01",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=False,  # Dev build without first password gate
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
            "--data-dir",
            str(tmp_path),
        ],
        input="N3w-Dev-Pass\nN3w-Dev-Pass\n",
    )
    assert result.exit_code == 0, f"Onboarding failed: {result.output}"
    assert cam.state.accounts["admin"].password == "N3w-Dev-Pass"

    # SetUser was called to update password
    set_user_reqs = [r for r in cam.requests if b"SetUser" in r.body]
    assert len(set_user_reqs) == 1


@pytest.mark.behavior("ONB-01")
async def test_set_user_timeout_yields_unreachable_with_guidance(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """SetUser timeout returns UNREACHABLE (10) advising owner camera may already use new password."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-FACTORY-04",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
    )

    # Mock SetUser to time out
    with patch.object(OnvifDeviceClient, "set_user_password", return_value=Timeout()):
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
                "--data-dir",
                str(tmp_path),
            ],
            input="N3w-Camera-Pass\nN3w-Camera-Pass\n",
        )

    assert result.exit_code == ExitCode.UNREACHABLE
    assert "The camera did not confirm the change" in result.output
    assert "It may already use the new password" in result.output

    # No second login with new password was attempted
    login_reqs = [r for r in cam.requests if r.method == "POST" and r.path == "/nuraeye/session/login"]
    assert len(login_reqs) == 1  # Only the single factory probe
