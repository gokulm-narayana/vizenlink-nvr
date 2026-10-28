"""Integration tests for auth_failed lifecycle, set-password recovery, and lockout safety (D-09, D-10)."""

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
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraCredential


@pytest.mark.behavior("CAM-08")
async def test_auth_failed_lifecycle_and_set_password_recovery(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Full cycle: external password change -> reprobe auth_failed -> short-circuits ->
    wrong set-password -> right set-password recovery (D-05, D-09, D-14).
    Asserts login-attempt deltas of 1, 0, 0, 1, 1.
    """
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-AUTH-01",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # 1. Onboard camera
    res_add = await asyncio.to_thread(
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
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0

    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        orig_cred = (
            await conn.execute(
                select(CameraCredential.ciphertext).where(CameraCredential.serial == "VZL-CAM-AUTH-01")
            )
        ).scalar_one()
    await engine.dispose()

    # 2. Simulate external password change (e.g. from mobile app)
    cam.state.accounts["admin"] = Account("Pass-New-Mobile", CameraRole.ADMINISTRATOR)
    n0 = cam.state.login_attempts.get("admin", 0)

    # 3. Step 1: First reprobe fails with 401 -> marks auth_failed, exit 23
    res_reprobe_1 = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-AUTH-01",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe_1.exit_code == 23
    n1 = cam.state.login_attempts.get("admin", 0)
    assert n1 - n0 == 1, "First reprobe should have made exactly 1 login attempt"

    # Verify camera state is auth_failed in database
    async with engine.connect() as conn:
        state_1 = (
            await conn.execute(select(Camera.state).where(Camera.serial == "VZL-CAM-AUTH-01"))
        ).scalar_one()
        assert state_1 == "auth_failed"
    await engine.dispose()

    # Verify status CLI reports auth_failed count
    res_status = await asyncio.to_thread(
        cli.invoke,
        app,
        ["status", "--json", "--data-dir", str(tmp_path)],
    )
    assert res_status.exit_code == 0
    status_data = json.loads(res_status.stdout)
    assert status_data["cameras_by_state"]["auth_failed"] == 1

    # 4. Step 2: Second reprobe while auth_failed -> short-circuits with 0 new login attempts
    res_reprobe_2 = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-AUTH-01",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe_2.exit_code == 23
    n2 = cam.state.login_attempts.get("admin", 0)
    assert n2 - n1 == 0, "Second reprobe should have made 0 new login attempts"

    # 5. Step 3: Rename while auth_failed -> short-circuits with 0 new login attempts
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-AUTH-01",
            "--name",
            "WillNotTry",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 23
    n3 = cam.state.login_attempts.get("admin", 0)
    assert n3 - n2 == 0, "Rename on auth_failed camera should have made 0 new login attempts"

    # 6. Step 4: set-password with wrong password -> WRONG_CREDENTIALS exit 11
    res_pw_wrong = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "set-password",
            "--serial",
            "VZL-CAM-AUTH-01",
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Wrong-Password-Entry\n",
    )
    assert res_pw_wrong.exit_code == 11
    n4 = cam.state.login_attempts.get("admin", 0)
    assert n4 - n3 == 1, "Wrong set-password should have made exactly 1 new login attempt"

    # Verify state still auth_failed and ciphertext unchanged
    async with engine.connect() as conn:
        state_wrong = (
            await conn.execute(select(Camera.state).where(Camera.serial == "VZL-CAM-AUTH-01"))
        ).scalar_one()
        assert state_wrong == "auth_failed"

        cred_wrong = (
            await conn.execute(
                select(CameraCredential.ciphertext).where(CameraCredential.serial == "VZL-CAM-AUTH-01")
            )
        ).scalar_one()
        assert cred_wrong == orig_cred
    await engine.dispose()

    # 7. Step 5: set-password with correct password -> OK exit 0
    res_pw_right = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "set-password",
            "--serial",
            "VZL-CAM-AUTH-01",
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Pass-New-Mobile\n",
    )
    assert res_pw_right.exit_code == 0
    n5 = cam.state.login_attempts.get("admin", 0)
    assert n5 - n4 == 1, "Right set-password should have made exactly 1 new login attempt"

    # Assert exact deltas sequence across the 5 operations: 1, 0, 0, 1, 1
    deltas = [n1 - n0, n2 - n1, n3 - n2, n4 - n3, n5 - n4]
    assert deltas == [1, 0, 0, 1, 1]

    # Verify state active and ciphertext updated
    async with engine.connect() as conn:
        state_right = (
            await conn.execute(select(Camera.state).where(Camera.serial == "VZL-CAM-AUTH-01"))
        ).scalar_one()
        assert state_right == "active"

        cred_right = (
            await conn.execute(
                select(CameraCredential.ciphertext).where(CameraCredential.serial == "VZL-CAM-AUTH-01")
            )
        ).scalar_one()
        assert cred_right != orig_cred
    await engine.dispose()

    # 8. Subsequent reprobe now succeeds
    res_reprobe_3 = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-AUTH-01",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe_3.exit_code == 0


@pytest.mark.behavior("CAM-08")
async def test_set_password_429_returns_blocked_exit_14_and_stores_nothing(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """When camera responds 429 during set-password, returns BLOCKED exit 14 and stores nothing."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-AUTH-02",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    res_add = await asyncio.to_thread(
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
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0

    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        orig_cred = (
            await conn.execute(
                select(CameraCredential.ciphertext).where(CameraCredential.serial == "VZL-CAM-AUTH-02")
            )
        ).scalar_one()
    await engine.dispose()

    # Inject 429 fault on login with retry_after
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(
            429,
            json_body={
                "error_code": 429,
                "error_msg": "Too many attempts",
                "retry_after_seconds": 60,
            },
        ),
    )

    res_pw = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "set-password",
            "--serial",
            "VZL-CAM-AUTH-02",
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="New-Password-Attempt\n",
    )
    assert res_pw.exit_code == 14

    # Nothing was stored
    async with engine.connect() as conn:
        curr_cred = (
            await conn.execute(
                select(CameraCredential.ciphertext).where(CameraCredential.serial == "VZL-CAM-AUTH-02")
            )
        ).scalar_one()
        assert curr_cred == orig_cred
    await engine.dispose()


@pytest.mark.behavior("CAM-08")
async def test_reprobe_403_returns_forbidden_exit_18_and_does_not_mark_auth_failed(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """403 on stored account during reprobe returns FORBIDDEN exit 18 and leaves state unchanged (D-10)."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-AUTH-03",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    res_add = await asyncio.to_thread(
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
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0

    # Inject 403 Forbidden on capabilities
    cam.faults.add(
        "GET /nuraeye/capabilities",
        Status(403, json_body={"error_code": 403, "error_msg": "Forbidden"}),
    )

    res_reprobe = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            "VZL-CAM-AUTH-03",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_reprobe.exit_code == 18

    # State must NOT be auth_failed
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        state = (
            await conn.execute(select(Camera.state).where(Camera.serial == "VZL-CAM-AUTH-03"))
        ).scalar_one()
        assert state == "active"
    await engine.dispose()


@pytest.mark.behavior("CAM-08")
async def test_rename_setscopes_401_marks_auth_failed(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """External password change causing SetScopes 401 on rename marks camera auth_failed."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-AUTH-04",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    res_add = await asyncio.to_thread(
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
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0

    # Change password on camera
    cam.state.accounts["admin"] = Account("Pass-New-1", CameraRole.ADMINISTRATOR)

    # Rename triggers SetScopes with old password -> 401
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-AUTH-04",
            "--name",
            "NewNameAttempt",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 23

    # Verify state in DB is auth_failed
    engine = create_engine_for(tmp_path / "nvr.db")
    async with engine.connect() as conn:
        state = (
            await conn.execute(select(Camera.state).where(Camera.serial == "VZL-CAM-AUTH-04"))
        ).scalar_one()
        assert state == "auth_failed"
    await engine.dispose()
