"""Integration tests for atomic, retry-safe camera onboarding (CAM-06, D-07)."""

import asyncio
import json
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole
from sqlalchemy import func, select
from typer.testing import CliRunner

import vizenlink_nvr.services.onboarding as onboarding_module
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.cli.exitcodes import ExitCode
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow, CameraCredential, CameraStream


async def assert_all_table_counts(
    engine,
    *,
    cameras: int,
    credentials: int,
    capabilities: int,
    streams: int,
) -> None:
    """Verify exact row counts in all 4 camera registry tables using a fresh connection."""
    async with engine.connect() as conn:
        c_cam = (await conn.execute(select(func.count()).select_from(Camera))).scalar()
        c_cred = (await conn.execute(select(func.count()).select_from(CameraCredential))).scalar()
        c_caps = (await conn.execute(select(func.count()).select_from(CameraCapabilitiesRow))).scalar()
        c_str = (await conn.execute(select(func.count()).select_from(CameraStream))).scalar()
        assert c_cam == cameras, f"Expected {cameras} cameras, got {c_cam}"
        assert c_cred == credentials, f"Expected {credentials} credentials, got {c_cred}"
        assert c_caps == capabilities, f"Expected {capabilities} capabilities, got {c_caps}"
        assert c_str == streams, f"Expected {streams} streams, got {c_str}"


@pytest.mark.behavior("CAM-06")
@pytest.mark.parametrize(
    "fault_step",
    [
        "identity",
        "factory_probe_login",
        "verification_login",
        "get_capabilities",
        "reread_serial",
        "get_profiles",
        "live_stream_profile_1",
        "live_stream_profile_2",
        "db_exception",
    ],
)
async def test_atomic_add_nine_fault_points_leave_zero_rows_and_retry_succeeds(
    fault_step: str,
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fault injected at any of the nine onboarding steps leaves 0 rows; an immediate retry succeeds."""
    serial = f"VZL-CAM-ATM-{fault_step.upper()[:12]}"
    cam: FakeCamera = await fake_camera(
        serial=serial,
        accounts={"admin": Account("Owner-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)

    # 1. Configure the fault for step
    if fault_step == "identity":
        err_500 = Status(500, json_body={"error": "Identity failure"})
        cam.faults.add("POST /nuraeye/identity", err_500, err_500, err_500)
    elif fault_step == "factory_probe_login":
        cam.faults.add("POST /nuraeye/session/login", Status(500, json_body={"error": "Login server error"}))
    elif fault_step == "verification_login":
        # First login (factory probe) 401, second login (verification) 500
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
            Status(500, json_body={"error": "Verification login error"}),
        )
    elif fault_step == "get_capabilities":
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        )
        cam.faults.add("GET /nuraeye/capabilities", Status(500, json_body={"error": "Caps error"}))
    elif fault_step == "reread_serial":
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        )
        # Blank get_serial_number is unauthenticated (first SOAP call)
        # Reread serial is authenticated (second SOAP call to device_service)
        cam.faults.add(
            "POST /onvif/device_service",
            Status(200),  # first blank read succeeds via normal handler
            Status(500, json_body={"error": "Serial reread failure"}),
        )
    elif fault_step == "get_profiles":
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        )
        cam.faults.add("POST /onvif/media2_service", Status(500, json_body={"error": "GetProfiles error"}))
    elif fault_step == "live_stream_profile_1":
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        )
        cam.faults.add("POST /nuraeye/live-stream-uri", Status(500, json_body={"error": "Profile 1 error"}))
    elif fault_step == "live_stream_profile_2":
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        )
        cam.faults.add(
            "POST /nuraeye/live-stream-uri",
            Status(
                200,
                json_body={
                    "error_code": 0,
                    "error_msg": "Success",
                    "output": {
                        "transport": "rtsp",
                        "port": 554,
                        "path": "/high",
                        "url": "rtsp://127.0.0.1:554/high",
                    },
                },
            ),
            Status(500, json_body={"error": "Profile 2 error"}),
        )
    elif fault_step == "db_exception":
        cam.faults.add(
            "POST /nuraeye/session/login",
            Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
        )

        async def failing_insert_camera(session, record):
            # Flush a partial camera row, then raise an exception inside the transaction
            cam_row = Camera(
                serial=record.serial,
                host=record.host,
                https_port=record.https_port,
                mac=record.mac,
                name=record.name,
                location=record.location,
                group_tag=record.group_tag,
                manufacturer=record.manufacturer,
                model=record.model,
                firmware_version=record.firmware_version,
                hardware_id=record.hardware_id,
                tls_fingerprint_sha256=record.tls_fingerprint_sha256,
                camera_id_check=record.camera_id_check,
                state="active",
                added_at=record.added_at,
                host_updated_at=record.added_at,
                identity_synced_at=record.added_at,
                last_error=None,
            )
            session.add(cam_row)
            await session.flush()
            raise RuntimeError("Simulated DB failure after camera row flush")

        monkeypatch.setattr(onboarding_module, "insert_camera", failing_insert_camera)

    # 2. Run add command -> must fail
    res_fail = await asyncio.to_thread(
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
        input="Owner-Pass-01\n",
    )
    assert res_fail.exit_code != 0, f"Expected failure for {fault_step}, got exit code 0"

    # 3. Assert zero rows in all four tables
    await assert_all_table_counts(engine, cameras=0, credentials=0, capabilities=0, streams=0)

    # 4. Clear faults and monkeypatches
    cam.faults._faults.clear()
    monkeypatch.undo()

    # Configured camera needs 401 on factory probe
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # 5. Immediate retry succeeds
    res_success = await asyncio.to_thread(
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
        input="Owner-Pass-01\n",
    )
    assert res_success.exit_code == 0, f"Retry failed for {fault_step}: {res_success.output}"

    # 6. Assert exactly one camera, one credential, one capabilities, two streams
    await assert_all_table_counts(engine, cameras=1, credentials=1, capabilities=1, streams=2)
    await engine.dispose()


@pytest.mark.behavior("CAM-06")
async def test_atomic_add_factory_password_changed_then_later_step_fails_retry_configured(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Factory camera changes password via SetUser; later step fails -> 0 rows.
    Retry asks for configured password.
    """
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-ATOMIC-FAC",
        accounts={"admin": Account("password", CameraRole.ADMINISTRATOR)},
        default_password_in_use=True,
        first_password_gate=True,
    )

    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)

    # Inject fault on GetProfiles (after SetUser has succeeded)
    cam.faults.add(
        "POST /onvif/media2_service",
        Status(500, json_body={"error": "Media2 profiles failure"}),
    )

    # 1. Attempt add with factory password change
    res_fail = await asyncio.to_thread(
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
        input="N3w-Atomic-Pass\nN3w-Atomic-Pass\n",
    )
    assert res_fail.exit_code == ExitCode.STREAMS_UNAVAILABLE

    # Zero rows in all tables
    await assert_all_table_counts(engine, cameras=0, credentials=0, capabilities=0, streams=0)

    # Camera simulator kept its newly set password
    assert cam.state.accounts["admin"].password == "N3w-Atomic-Pass"

    # Clear fault on GetProfiles
    cam.faults._faults.clear()

    # 2. Retry: factory probe gets 401 because password is no longer 'password'!
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )
    # So onboarding treats camera as CONFIGURED and asks for current password (1 line).
    res_retry = await asyncio.to_thread(
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
        input="N3w-Atomic-Pass\n",
    )
    assert res_retry.exit_code == 0, f"Retry onboarding failed: {res_retry.output}"

    # Now all rows are populated
    await assert_all_table_counts(engine, cameras=1, credentials=1, capabilities=1, streams=2)
    await engine.dispose()


@pytest.mark.behavior("CAM-06")
async def test_atomic_add_best_effort_reads_failing_still_succeeds(
    cli: CliRunner,
    fake_camera: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Best-effort reads (GetNetworkInterfaces, GetDeviceIdentity) failing do not abort the add."""
    from unittest.mock import AsyncMock

    from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
    from vizenlink_nvr.camera.result import Failure, FailureKind

    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-ATOMIC-BEST",
        accounts={"admin": Account("Owner-Pass-01", CameraRole.ADMINISTRATOR)},
        default_password_in_use=False,
        first_password_gate=False,
    )

    # Factory probe gets 401
    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(401, json_body={"error_code": 401, "error_msg": "Invalid credentials"}),
    )

    # Best effort reads fail
    monkeypatch.setattr(
        OnvifDeviceClient,
        "get_network_interface_info",
        AsyncMock(return_value=Failure(kind=FailureKind.GENERIC, reason="Failed network interface")),
    )
    monkeypatch.setattr(
        OnvifDeviceClient,
        "get_device_identity",
        AsyncMock(return_value=Failure(kind=FailureKind.GENERIC, reason="Failed identity")),
    )

    res = await asyncio.to_thread(
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
        input="Owner-Pass-01\n",
    )
    assert res.exit_code == 0, f"Add failed: {res.output}"
    data = json.loads(res.stdout)
    assert data["serial"] == "VZL-CAM-ATOMIC-BEST"
    assert data["mac"] == ""
    assert data["name"] == ""

    # Verify rows stored
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    await assert_all_table_counts(engine, cameras=1, credentials=1, capabilities=1, streams=2)
    await engine.dispose()
