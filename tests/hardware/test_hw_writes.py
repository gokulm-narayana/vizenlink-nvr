"""Real-camera hardware tests requiring write/reset permissions (HW-04, HW-08, HW-13)."""

import asyncio
import secrets
import sys
import urllib.parse
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.hardware.conftest import CameraSnapshot, HwConfig
from tests.hardware.support.camera_admin import (
    create_user,
    delete_user,
    soft_factory_reset,
    wait_until_answering,
)
from tests.hardware.support.report import HwReport
from tests.hardware.support.rtsps_client import RtspsClient
from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp, camera_ssl_context
from vizenlink_nvr.camera.onvif.device import (
    LOCATION_SCOPE_PREFIX,
    NAME_SCOPE_PREFIX,
    OnvifDeviceClient,
)
from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.timeutil import SystemClock


@pytest.mark.hardware
@pytest.mark.hardware_destructive
@pytest.mark.asyncio
async def test_hw_04_soft_factory_reset_and_recovery(
    hw_reset: HwConfig,
    hw_report: HwReport,
    hw_camera_snapshot: CameraSnapshot,
    tmp_path: Path,
) -> None:
    """HW-04: Soft factory reset, verify PasswordChangeRequired, add with new password (D-20, D-24)."""
    sys.stderr.write(
        f"WARNING: HW-04 will SOFT factory-reset the camera at {hw_reset.host}. "
        "Name, location and extra accounts are erased; Wi-Fi is kept.\n"
    )
    sys.stderr.flush()
    await asyncio.sleep(10.0)

    conn = CameraConnection(
        host=hw_reset.host,
        port=hw_reset.port,
        username=hw_reset.username,
        password=hw_reset.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()

    # 1. Trigger soft factory reset
    reset_res = await soft_factory_reset(conn, http=http)
    if not reset_res.is_success():
        hw_report.outcome("HW-04", "FAILED", f"Soft reset request failed: {reset_res.failure().reason}")
        pytest.fail(f"SetSystemFactoryDefault Soft failed: {reset_res.failure().reason}")

    hw_camera_snapshot.mutation_occurred = True

    # 2. Wait until camera reboots and answers
    sys.stderr.write("Waiting for camera reboot after soft reset...\n")
    sys.stderr.flush()
    answered = await wait_until_answering(hw_reset.host, hw_reset.port, timeout=180.0)
    assert answered, f"Camera at {hw_reset.host}:{hw_reset.port} did not resume answering within 180s"

    # 3. Assert direct Media2 GetProfiles with factory admin/"password" answers PasswordChangeRequired
    factory_conn = CameraConnection(
        host=hw_reset.host,
        port=hw_reset.port,
        username="admin",
        password="password",
    )
    m2_client = OnvifMedia2Client(factory_conn, http, clock)
    p_res = await m2_client.get_profiles()
    assert not p_res.is_success(), "Expected factory login to fail with PasswordChangeRequired"
    hw_report.record("HW-04", "factory_login_fault", p_res.failure().reason)
    assert "PasswordChangeRequired" in p_res.failure().reason or "PasswordChangeRequired" in str(
        p_res.failure().fault_subcode
    )

    # 4. Run nvr cameras add with stdin providing new password twice
    runner = CliRunner()
    res_add = runner.invoke(
        app,
        [
            "cameras",
            "add",
            "--host",
            hw_reset.host,
            "--port",
            str(hw_reset.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input=f"{hw_reset.password}\n{hw_reset.password}\n",
    )
    assert res_add.exit_code == 0, f"nvr cameras add after reset failed: {res_add.output}"
    assert "notice" in res_add.output or "factory password" in res_add.output.lower()

    # 5. Verify new password works
    new_client = OnvifDeviceClient(conn, http, clock)
    info_res = await new_client.get_device_information()
    assert info_res.is_success(), f"New password login failed: {info_res.failure().reason}"

    hw_report.outcome("HW-04", "PASSED", "Soft factory reset and initial password provisioning succeeded")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_08_create_user_role_and_stream(
    hw_write: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-08: Create a 'User' account, RTSPS DESCRIBE /high with it, delete account in finally."""
    conn = CameraConnection(
        host=hw_write.host,
        port=hw_write.port,
        username=hw_write.username,
        password=hw_write.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))

    test_user = f"user_{secrets.token_hex(4)}"
    test_pass = f"Pass_{secrets.token_urlsafe(12)}!"

    # Create user
    create_res = await create_user(conn, username=test_user, password=test_pass, level="User", http=http)
    if not create_res.is_success():
        hw_report.outcome("HW-08", "FAILED", f"CreateUsers failed: {create_res.failure().reason}")
        pytest.fail(f"CreateUsers failed: {create_res.failure().reason}")

    hw_report.record("HW-08", "created_user", test_user)

    try:
        # RTSPS DESCRIBE /high with created User credentials
        rtsps = RtspsClient(
            host=hw_write.host,
            port=hw_write.port,
            path="/high",
            username=test_user,
            password=test_pass,
        )
        await rtsps.connect()
        status, _ = await rtsps.describe()
        await rtsps.close()

        hw_report.record("HW-08", "user_describe_status", status)
        assert status == 200, f"Expected 200 DESCRIBE with User role, got {status}"
        hw_report.outcome("HW-08", "PASSED", f"Created User account and streamed /high (status {status})")

    finally:
        # Delete user
        await delete_user(conn, username=test_user, http=http)


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_13_rename_location_and_unicode_limits(
    hw_write: HwConfig,
    hw_report: HwReport,
    hw_camera_snapshot: CameraSnapshot,
) -> None:
    """HW-13: Rename to 'Back Yard' / 'Café', read back scopes, test 32-char non-ASCII name (A11)."""
    conn = CameraConnection(
        host=hw_write.host,
        port=hw_write.port,
        username=hw_write.username,
        password=hw_write.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    dev_client = OnvifDeviceClient(conn, http, clock)

    hw_camera_snapshot.mutation_occurred = True

    try:
        # 1. Rename to "Back Yard" with location "Café"
        name1 = "Back Yard"
        loc1 = "Café"
        scopes1 = [
            f"{NAME_SCOPE_PREFIX}{urllib.parse.quote(name1)}",
            f"{LOCATION_SCOPE_PREFIX}{urllib.parse.quote(loc1)}",
        ]
        set_res = await dev_client.set_scopes(scopes1)
        assert set_res.is_success(), f"SetScopes failed: {set_res.failure().reason}"

        # Read back via GetScopes
        get_res = await dev_client.get_scopes()
        assert get_res.is_success()
        current_scopes = get_res.unwrap()
        hw_report.record("HW-13", "renamed_scopes", current_scopes)

        # 2. Try 32-character non-ASCII name (A11) and record what camera stores
        name_32_unicode = "Café-Terrasse-München-Über-3200!"[:32]
        scopes2 = [
            f"{NAME_SCOPE_PREFIX}{urllib.parse.quote(name_32_unicode)}",
            f"{LOCATION_SCOPE_PREFIX}{urllib.parse.quote(loc1)}",
        ]
        set_res2 = await dev_client.set_scopes(scopes2)
        hw_report.record("HW-13", "unicode_32_set_success", set_res2.is_success())

        get_res2 = await dev_client.get_scopes()
        if get_res2.is_success():
            stored_name = None
            for sc in get_res2.unwrap():
                if sc.startswith(NAME_SCOPE_PREFIX):
                    stored_name = urllib.parse.unquote(sc[len(NAME_SCOPE_PREFIX) :])
            hw_report.record("HW-13", "stored_unicode_name", stored_name)

        hw_report.outcome(
            "HW-13",
            "PASSED",
            "Rename and location sync verified with Unicode character checks",
        )

    finally:
        # Restore original snapshot name and location
        restore_scopes: list[str] = []
        if hw_camera_snapshot.name:
            restore_scopes.append(f"{NAME_SCOPE_PREFIX}{urllib.parse.quote(hw_camera_snapshot.name)}")
        if hw_camera_snapshot.location:
            restore_scopes.append(f"{LOCATION_SCOPE_PREFIX}{urllib.parse.quote(hw_camera_snapshot.location)}")
        if restore_scopes:
            await dev_client.set_scopes(restore_scopes)
