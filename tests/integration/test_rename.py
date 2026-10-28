"""Integration tests for camera renaming, location, and group tags (CAM-08, D-13)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fake_camera.faults import Status
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import select, update
from typer.testing import CliRunner

from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.result import Failure, FailureKind
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow, CameraCredential, CameraStream


@pytest.mark.behavior("CAM-08")
async def test_rename_writes_name_location_to_camera_and_group_is_nvr_only(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """rename --name, --location, --group writes name/location to camera,
    updates registry, and never sends group tag over the wire (CAM-08, D-13).
    """
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-01",
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
    assert res_add.exit_code == 0, f"Add failed: {res_add.output}"

    # 2. Clear request log to track requests during rename
    cam.requests.clear()

    # 3. Rename camera
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-RENAME-01",
            "--name",
            "Back Yard",
            "--location",
            "Garden",
            "--group",
            "Outdoor",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 0, f"Rename failed: {res_rename.output}"

    # 4. Camera state updated on the simulator
    assert cam.state.name == "Back Yard"
    assert cam.state.location == "Garden"

    # 5. Registry row updated
    updated_data = json.loads(res_rename.stdout)
    assert updated_data["name"] == "Back Yard"
    assert updated_data["location"] == "Garden"
    assert updated_data["group_tag"] == "Outdoor"
    assert updated_data["identity_synced_at"] is not None

    # 6. Invariant D-13: No simulator request body contains "Outdoor"
    assert len(cam.requests) > 0
    for req in cam.requests:
        body_text = req.body.decode("utf-8", errors="replace")
        assert "Outdoor" not in body_text, f"Group tag leaked to camera wire: {body_text}"


@pytest.mark.behavior("CAM-08")
async def test_rename_group_only_makes_zero_simulator_requests(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Renaming group only performs zero camera requests (CAM-08, D-13)."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-02",
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

    cam.requests.clear()

    # Rename only group
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-RENAME-02",
            "--group",
            "Warehouse",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 0
    updated_data = json.loads(res_rename.stdout)
    assert updated_data["group_tag"] == "Warehouse"

    # Zero requests reached the camera
    assert len(cam.requests) == 0


@pytest.mark.behavior("CAM-08")
async def test_rename_33_chars_refused_as_invalid_input_exit_20(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """33-character name is refused with exit 20 before any camera request."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-03",
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

    cam.requests.clear()

    long_name = "A" * 33
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-RENAME-03",
            "--name",
            long_name,
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 20
    assert len(cam.requests) == 0


@pytest.mark.behavior("CAM-08")
async def test_rename_unicode_special_chars_cafe(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Non-ASCII characters (e.g. 'Café 1') round-trip cleanly to camera and registry."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-04",
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

    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-RENAME-04",
            "--name",
            "Café 1",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 0
    assert cam.state.name == "Café 1"

    updated_data = json.loads(res_rename.stdout)
    assert updated_data["name"] == "Café 1"


@pytest.mark.behavior("CAM-08")
async def test_add_with_name_location_group_and_failure_leaves_zero_rows(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """nvr cameras add with --name, --location, --group sets on camera and registry;
    if SetScopes fails, nothing is stored in any table (CAM-06, CAM-08).
    """
    # 1. Successful add with name/location/group
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-05",
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
            "--name",
            "Front",
            "--location",
            "Porch",
            "--group",
            "Home",
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input="Pass-Owner-1\n",
    )
    assert res_add.exit_code == 0
    assert cam.state.name == "Front"
    assert cam.state.location == "Porch"

    add_data = json.loads(res_add.stdout)
    assert add_data["name"] == "Front"
    assert add_data["location"] == "Porch"
    assert add_data["group_tag"] == "Home"

    # 2. Failure during SetScopes leaves zero rows
    tmp_fail = tmp_path / "fail_db"
    cam_fail: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-06",
        accounts={"admin": Account("Pass-Owner-1", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )
    cam_fail.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )
    # Monkeypatch set_device_name to fail
    monkeypatch.setattr(
        OnvifDeviceClient,
        "set_device_name",
        AsyncMock(return_value=Failure(kind=FailureKind.GENERIC, reason="Scope error")),
    )

    res_fail = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "add",
            "--host",
            cam_fail.host,
            "--port",
            str(cam_fail.port),
            "--name",
            "Front",
            "--location",
            "Porch",
            "--group",
            "Home",
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_fail),
        ],
        input="Pass-Owner-1\n",
    )
    assert res_fail.exit_code != 0
    assert "Could not set the camera name or location. Nothing was stored." in res_fail.output

    # Check zero rows
    engine = create_engine_for(tmp_fail / "nvr.db")
    async with engine.connect() as conn:
        for model in (Camera, CameraCredential, CameraCapabilitiesRow, CameraStream):
            res = await conn.execute(select(model))
            assert len(res.fetchall()) == 0
    await engine.dispose()


@pytest.mark.behavior("CAM-08")
async def test_rename_on_auth_failed_camera_returns_exit_23_with_zero_requests(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """rename on an auth_failed camera returns exit 23 without sending any requests."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-RENAME-07",
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

    # Mark camera auth_failed in database
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.connect() as conn:
        await conn.execute(
            update(Camera)
            .where(Camera.serial == "VZL-CAM-RENAME-07")
            .values(state="auth_failed", last_error="Unauthorized")
        )
        await conn.commit()
    await engine.dispose()

    cam.requests.clear()

    # Attempt rename with --name
    res_rename = await asyncio.to_thread(
        cli.invoke,
        app,
        [
            "cameras",
            "rename",
            "--serial",
            "VZL-CAM-RENAME-07",
            "--name",
            "ShouldFail",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert res_rename.exit_code == 23

    # Zero requests reached the camera
    assert len(cam.requests) == 0
