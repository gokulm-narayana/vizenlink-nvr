"""Real-camera hardware tests: Protocol, Headers, Lockout, and Re-IP (HW-03, HW-05, HW-06, HW-07)."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from tests.hardware.conftest import HwConfig
from tests.hardware.support.report import HwReport
from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp, camera_ssl_context
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.timeutil import FakeClock, SystemClock, utc_now


@pytest.mark.hardware
def test_hw_03_wrong_password_then_success(
    hw_env: HwConfig,
    hw_report: HwReport,
    tmp_path: Path,
) -> None:
    """HW-03: One add with wrong password -> WRONG_CREDENTIALS, then right password succeeds immediately."""
    runner = CliRunner()

    # 1. Attempt with incorrect password
    res_wrong = runner.invoke(
        app,
        [
            "cameras",
            "add",
            "--host",
            hw_env.host,
            "--port",
            str(hw_env.port),
            "--password-stdin",
            "--data-dir",
            str(tmp_path),
        ],
        input="wrong-camera-password-9999\n",
    )
    assert res_wrong.exit_code != 0
    err_text = res_wrong.output or (res_wrong.stdout if hasattr(res_wrong, "stdout") else "")
    assert "Incorrect username or password" in err_text
    hw_report.record("HW-03", "wrong_password_exit", res_wrong.exit_code)

    # 2. Correct login immediately succeeds without lockout
    res_good = runner.invoke(
        app,
        [
            "cameras",
            "add",
            "--host",
            hw_env.host,
            "--port",
            str(hw_env.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input=f"{hw_env.password}\n",
    )
    assert res_good.exit_code == 0
    payload = json.loads(res_good.output)
    hw_report.record("HW-03", "good_login_serial", payload.get("serial"))
    hw_report.outcome("HW-03", "PASSED", "Wrong password failed gracefully; immediate retry succeeded")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_05_reprobe_heals_closed_port_and_wrong_id_421(
    hw_env: HwConfig,
    hw_report: HwReport,
    tmp_path: Path,
) -> None:
    """HW-05: Reprobe heals closed port back to real address; wrong id header yields 421."""
    runner = CliRunner()

    # 1. Onboard camera into tmp_path
    res_add = runner.invoke(
        app,
        [
            "cameras",
            "add",
            "--host",
            hw_env.host,
            "--port",
            str(hw_env.port),
            "--password-stdin",
            "--json",
            "--data-dir",
            str(tmp_path),
        ],
        input=f"{hw_env.password}\n",
    )
    assert res_add.exit_code == 0
    payload = json.loads(res_add.output)
    serial = payload["serial"]

    # 2. Rewrite stored port in sqlite db to an unreachable port (e.g. 19443)
    db_file = tmp_path / "nvr.db"
    engine = create_engine_for(db_file)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE cameras SET https_port = 19443 WHERE serial = :serial"),
            {"serial": serial},
        )
    await engine.dispose()

    # 3. Run reprobe and verify it heals
    res_reprobe = runner.invoke(
        app,
        [
            "cameras",
            "reprobe",
            "--serial",
            serial,
            "--data-dir",
            str(tmp_path),
        ],
    )
    hw_report.record("HW-05", "reprobe_output", res_reprobe.output)
    assert res_reprobe.exit_code == 0

    # Verify db port was healed back
    engine = create_engine_for(db_file)
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT https_port FROM cameras WHERE serial = :serial"),
                {"serial": serial},
            )
        ).scalar_one()
    await engine.dispose()

    assert row == hw_env.port, f"Expected port {hw_env.port}, got {row}"
    hw_report.record("HW-05", "healed_port", row)

    # 4. Request with wrong camera id header yields 421 Misdirected Request
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    conn_wrong_id = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
        camera_id="WRONG_SERIAL_12345",
    )
    clock = SystemClock()
    nura_client = NuraeyeClient(conn_wrong_id, http, clock)
    res_wrong_id = await nura_client.get_capabilities()
    assert not res_wrong_id.is_success()
    fail_obj = res_wrong_id.failure()
    assert fail_obj.http_status == 421, f"Expected 421 Misdirected Request, got {fail_obj.http_status}"
    hw_report.record("HW-05", "wrong_id_status", fail_obj.http_status)

    hw_report.outcome("HW-05", "PASSED", "Reprobe healed closed port and wrong camera id yielded 421")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_06_header_case_sensitivity(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-06: Exact-case wrong id -> 421; lower-case wrong id recorded."""
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    conn = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
    )

    # 1. Exact-case wrong id
    exact_resp = await http.send(
        conn,
        "GET",
        "/nuraeye/capabilities",
        headers=[("X-VizenLink-Camera-Id", "DEFINITELY_WRONG_ID_99999")],
    )
    assert hasattr(exact_resp, "status")
    exact_status = exact_resp.status
    hw_report.record("HW-06", "exact_case_status", exact_status)
    assert exact_status == 421, f"Expected 421 for exact-case wrong id header, got {exact_status}"

    # 2. Lower-case wrong id (record status, not asserted)
    lower_resp = await http.send(
        conn,
        "GET",
        "/nuraeye/capabilities",
        headers=[("x-vizenlink-camera-id", "DEFINITELY_WRONG_ID_99999")],
    )
    lower_status = lower_resp.status if hasattr(lower_resp, "status") else "ERROR"
    hw_report.record("HW-06", "lower_case_status", lower_status)

    hw_report.outcome(
        "HW-06",
        "PASSED",
        f"Exact-case: {exact_status} (asserted 421); Lower-case: {lower_status} (recorded)",
    )


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_07_wsse_time_skews(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-07: Logins with created at now-1h, now+1h, now-24h, interleaved with good login."""
    conn = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    now = utc_now()

    skews = [
        ("minus_1h", timedelta(hours=-1)),
        ("plus_1h", timedelta(hours=1)),
        ("minus_24h", timedelta(hours=-24)),
    ]

    for label, offset in skews:
        skew_clock = FakeClock(now + offset)
        skew_client = OnvifDeviceClient(conn, http, skew_clock)
        skew_res = await skew_client.get_device_information()

        outcome_str = "SUCCESS" if skew_res.is_success() else f"FAILED: {skew_res.failure().reason}"
        hw_report.record("HW-07", f"skew_{label}", outcome_str)

        # Good login recovery between each to ensure counter never reaches a block
        good_client = OnvifDeviceClient(conn, http, SystemClock())
        good_res = await good_client.get_device_information()
        assert good_res.is_success(), f"Good login recovery failed after {label}: {good_res.failure().reason}"

    hw_report.outcome("HW-07", "PASSED", "Interleaved time skew checks completed")
