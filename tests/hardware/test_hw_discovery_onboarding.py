"""Real-camera hardware tests: Discovery and Onboarding (HW-01, HW-02, HW-12, HW-14)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.hardware.conftest import HwConfig
from tests.hardware.support.report import HwReport
from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.discovery.ws_discovery import WsDiscoveryClient, local_ipv4_interfaces
from vizenlink_nvr.camera.http import CameraHttp, camera_ssl_context, fetch_certificate_sha256
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.cli.app import app
from vizenlink_nvr.timeutil import SystemClock


def test_gate_skips_when_not_authorized(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Pure unit-style test proving no hardware operations occur without NVR_HW_RUN_AUTHORIZED=1."""
    monkeypatch.delenv("NVR_HW_RUN_AUTHORIZED", raising=False)
    monkeypatch.setenv("NVR_HW_HOST", "192.168.1.100")
    monkeypatch.setenv("NVR_HW_PASSWORD", "secret")

    with pytest.raises(pytest.skip.Exception, match="NVR_HW_RUN_AUTHORIZED=1"):
        request.getfixturevalue("hw_env")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_01_multicast_unicast_discovery(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-01: WS-Discovery multicast and unicast scans across real interfaces."""
    clock = SystemClock()
    client = WsDiscoveryClient(clock=clock)

    multicast_devs = await client.scan_multicast(wait=3.0)
    unicast_devs = await client.scan_unicast(overall_cap=5.0, straggler_wait=2.0)

    m_found = any(d.host == hw_env.host for d in multicast_devs)
    u_found = any(d.host == hw_env.host for d in unicast_devs)

    nics = [iface.name for iface in local_ipv4_interfaces()]
    hw_report.record("HW-01", "nics", nics)
    hw_report.record("HW-01", "multicast_found", m_found)
    hw_report.record("HW-01", "unicast_found", u_found)

    if not m_found and not u_found:
        hw_report.outcome(
            "HW-01",
            "FAILED",
            "Camera not found in multicast or unicast discovery; check macOS Local Network permissions (A3)",
        )
        pytest.fail(
            f"Camera at {hw_env.host} was not discovered. If running on macOS, "
            "ensure Local Network permission is granted to python/terminal (A3)."
        )

    hw_report.outcome(
        "HW-01",
        "PASSED",
        f"Multicast: {m_found}, Unicast: {u_found} across {len(nics)} NICs",
    )


@pytest.mark.hardware
def test_hw_02_onboard_real_camera(
    hw_env: HwConfig,
    hw_report: HwReport,
    tmp_path: Path,
) -> None:
    """HW-02: Onboard real camera via nvr cameras add --password-stdin --json into tmp data dir."""
    runner = CliRunner()
    result = runner.invoke(
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

    if result.exit_code != 0:
        hw_report.outcome("HW-02", "FAILED", f"Exit {result.exit_code}: {result.output}")
        pytest.fail(f"nvr cameras add failed with exit code {result.exit_code}: {result.output}")

    payload = json.loads(result.output)
    streams = payload.get("streams", [])
    hw_report.record("HW-02", "serial", payload.get("serial"))
    hw_report.record("HW-02", "stream_count", len(streams))
    hw_report.record("HW-02", "streams", streams)
    hw_report.outcome(
        "HW-02",
        "PASSED",
        f"Camera {payload.get('serial')} onboarded with {len(streams)} streams",
    )


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_12_capabilities_structure(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-12: Read capabilities and assert typed fields parse, camera_id_check is True."""
    conn = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    client = NuraeyeClient(conn, http, clock)

    res = await client.get_capabilities(strict=False)
    if not res.is_success():
        hw_report.outcome("HW-12", "FAILED", f"Capabilities fetch failed: {res.failure().reason}")
        pytest.fail(f"get_capabilities failed: {res.failure().reason}")

    caps = res.unwrap()
    hw_report.record("HW-12", "camera_id_check", caps.camera_id_check)
    hw_report.record("HW-12", "default_password_in_use", caps.default_password_in_use)
    hw_report.record("HW-12", "max_users", caps.max_users)
    hw_report.record("HW-12", "user_roles", caps.user_roles)

    assert caps.camera_id_check is True, "Expected camera_id_check to be True"
    assert caps.default_password_in_use is False, "Expected default_password_in_use to be False"
    hw_report.outcome("HW-12", "PASSED", "Capabilities parsed correctly with camera_id_check=True")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hw_14_tls_fingerprints(
    hw_env: HwConfig,
    hw_report: HwReport,
) -> None:
    """HW-14: Fetch cert fingerprints for 443, 554, 555 and assert pinned connection on 443."""
    fp_443 = await fetch_certificate_sha256(hw_env.host, hw_env.port)
    fp_554 = await fetch_certificate_sha256(hw_env.host, 554)
    fp_555 = await fetch_certificate_sha256(hw_env.host, 555)

    hw_report.record("HW-14", "tls_fingerprint_443", fp_443)
    hw_report.record("HW-14", "tls_fingerprint_554", fp_554)
    hw_report.record("HW-14", "tls_fingerprint_555", fp_555)

    assert fp_443 is not None, "Failed to fetch TLS certificate fingerprint on HTTPS port"

    # Assert pinned connection with 443 fingerprint succeeds
    conn = CameraConnection(
        host=hw_env.host,
        port=hw_env.port,
        username=hw_env.username,
        password=hw_env.password,
        tls_fingerprint_sha256=fp_443,
    )
    http = CameraHttp(ssl_context=camera_ssl_context(fp_443))
    dev_client = OnvifDeviceClient(conn, http, SystemClock())
    info = await dev_client.get_device_information()
    assert info.is_success(), f"Pinned connection to device service failed: {info.failure().reason}"

    hw_report.outcome("HW-14", "PASSED", f"Fingerprint 443: {fp_443[:16]}... verified")
