"""Contract tests for ONVIF Device service (DEV-01..DEV-07)."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fake_camera.server import FakeCamera
from pydantic import SecretStr

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.device import (
    DeviceIdentity,
    DeviceInformation,
    NetworkInterfaceInfo,
    OnvifDeviceClient,
    ServiceEntry,
    normalize_mac,
)
from vizenlink_nvr.camera.result import Failure, Success
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


@pytest.mark.behavior("DEV-03")
async def test_dev_03_network_interfaces(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """DEV-03: MAC normalized to uppercase colon-separated; first interface returned."""
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"

    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000002")
    cam.state.set_password("admin", "Admin-Pass-02")
    cam.state.mac = "aa-bb-cc-dd-ee-ff"

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-02",
        serial="VZL-CAM-000002",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifDeviceClient(conn, http_client, fake_clock)
    res = await client.get_network_interface_info()
    assert isinstance(res, Success)
    assert isinstance(res.value, NetworkInterfaceInfo)
    assert res.value.name == "wlan"
    assert res.value.mac == "AA:BB:CC:DD:EE:FF"
    assert res.value.address == "127.0.0.1"


@pytest.mark.behavior("DEV-04")
async def test_dev_04_device_identity_scopes(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """DEV-04: Scopes with name/Back%20Yard and location/Front%20Gate -> DeviceIdentity."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000003")
    cam.state.set_password("admin", "Admin-Pass-03")
    cam.state.name = "Back Yard"
    cam.state.location = "Front Gate"

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-03",
        serial="VZL-CAM-000003",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifDeviceClient(conn, http_client, fake_clock)
    res = await client.get_device_identity()
    assert isinstance(res, Success)
    assert isinstance(res.value, DeviceIdentity)
    assert res.value.name == "Back Yard"
    assert res.value.location == "Front Gate"

    # Missing scopes test
    cam.state.name = ""
    cam.state.location = ""
    res_empty = await client.get_device_identity()
    assert isinstance(res_empty, Success)
    assert res_empty.value.name == ""
    assert res_empty.value.location == ""


@pytest.mark.behavior("DEV-05")
async def test_dev_05_set_device_name_and_location(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """DEV-05: 33 characters fails before sending; Back Yard sends one Scopes; Café 1 roundtrips."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000004")
    cam.state.set_password("admin", "Admin-Pass-04")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-04",
        serial="VZL-CAM-000004",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifDeviceClient(conn, http_client, fake_clock)

    # 1. 33 characters refused before sending (zero requests recorded)
    initial_request_count = len(cam.requests)
    long_name = "X" * 33
    res_long = await client.set_device_name(long_name)
    assert isinstance(res_long, Failure)
    assert "exceeds maximum length" in res_long.reason
    assert len(cam.requests) == initial_request_count

    # Same for location
    res_long_loc = await client.set_device_location(long_name)
    assert isinstance(res_long_loc, Failure)
    assert len(cam.requests) == initial_request_count

    # 2. Back Yard sends exactly one Scopes entry
    res_set = await client.set_device_name("Back Yard")
    assert isinstance(res_set, Success)
    last_req = cam.requests[-1]
    body_str = last_req.body.decode("utf-8")
    assert "<tds:Scopes>onvif://www.onvif.org/name/Back%20Yard</tds:Scopes>" in body_str
    assert cam.state.name == "Back Yard"

    # 3. Non-ASCII "Café 1" round-trips through the sim
    res_cafe = await client.set_device_name("Café 1")
    assert isinstance(res_cafe, Success)
    assert cam.state.name == "Café 1"

    res_identity = await client.get_device_identity()
    assert isinstance(res_identity, Success)
    assert res_identity.value.name == "Café 1"


@pytest.mark.behavior("DEV-06")
async def test_dev_06_set_user_password(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """DEV-06: SetUser XML shape, no UserLevel, sim rejects 'PASSWORD' fault."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000005")
    cam.state.set_password("admin", "Admin-Pass-05")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-05",
        serial="VZL-CAM-000005",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifDeviceClient(conn, http_client, fake_clock)

    # Valid set password
    res_valid = await client.set_user_password("admin", SecretStr("N3w&Pass"))
    assert isinstance(res_valid, Success)
    last_req = cam.requests[-1]
    body_str = last_req.body.decode("utf-8")
    assert "<tt:Username>admin</tt:Username>" in body_str
    assert "<tt:Password>N3w&amp;Pass</tt:Password>" in body_str
    assert "UserLevel" not in body_str

    # Sim rejects "PASSWORD" (case-insensitive) with fault ter:PasswordNotAllowed
    conn_updated = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="N3w&Pass",
        serial="VZL-CAM-000005",
        tls_pin_sha256=cam.cert_sha256,
    )
    client_updated = OnvifDeviceClient(conn_updated, http_client, fake_clock)
    res_pwd = await client_updated.set_user_password("admin", "PASSWORD")
    assert isinstance(res_pwd, Failure)
    assert res_pwd.fault_subcode == "PasswordNotAllowed"


@pytest.mark.behavior("DEV-07")
async def test_dev_07_get_services(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """DEV-07: GetServices sends IncludeCapability false; returns service pairs."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000006")
    cam.state.set_password("admin", "Admin-Pass-06")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-06",
        serial="VZL-CAM-000006",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifDeviceClient(conn, http_client, fake_clock)
    res = await client.get_services()
    assert isinstance(res, Success)
    assert isinstance(res.value, list)
    assert len(res.value) >= 1
    assert any(
        isinstance(s, ServiceEntry) and s.namespace == "http://www.onvif.org/ver10/device/wsdl"
        for s in res.value
    )

    last_req = cam.requests[-1]
    body_str = last_req.body.decode("utf-8")
    assert "<tds:IncludeCapability>false</tds:IncludeCapability>" in body_str
