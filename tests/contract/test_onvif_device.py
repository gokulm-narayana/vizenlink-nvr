"""Contract tests for ONVIF Device service (DEV-01, DEV-02)."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.device import DeviceInformation, OnvifDeviceClient
from vizenlink_nvr.camera.result import Success
from vizenlink_nvr.timeutil import Clock

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "onvif"


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("DEV-01")
@pytest.mark.behavior("DEV-02")
async def test_tracer_onvif_serial_and_device_info(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Tracer test: read serial and device info over WSSE SOAP against simulator (DEV-01, DEV-02)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    # 1. Authenticated connection with known serial
    conn_authed = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client_authed = OnvifDeviceClient(conn_authed, http_client, fake_clock)

    res_serial = await client_authed.get_serial_number()
    assert isinstance(res_serial, Success)
    assert res_serial.value == "VZL-CAM-000001"
    assert res_serial.value == cam.state.serial

    req_authed = [r for r in cam.requests if r.path == "/onvif/device_service"][-1]
    # Verify Content-Type and camera ID headers
    content_type_val = [val for name, val in req_authed.headers if name.lower() == b"content-type"][0]
    assert content_type_val == b"application/soap+xml; charset=utf-8"
    assert b"X-VizenLink-Camera-Id" in req_authed.raw_header_names
    camera_id_val = [val for name, val in req_authed.headers if name == b"X-VizenLink-Camera-Id"][0]
    assert camera_id_val == b"VZL-CAM-000001"

    # 2. Blank connection (used during initial discovery / probe)
    conn_blank = CameraConnection(
        host=cam.host,
        port=cam.port,
        tls_pin_sha256=cam.cert_sha256,
    )
    client_blank = OnvifDeviceClient(conn_blank, http_client, fake_clock)

    res_blank = await client_blank.get_device_information()
    assert isinstance(res_blank, Success)
    assert isinstance(res_blank.value, DeviceInformation)
    assert res_blank.value.manufacturer == cam.state.manufacturer
    assert res_blank.value.model == cam.state.model
    assert res_blank.value.serial_number == cam.state.serial

    req_blank = [r for r in cam.requests if r.path == "/onvif/device_service"][-1]
    assert req_blank.credential_use == "blank"
