"""Contract tests for NuraEye identity probe over simulated TLS camera."""

from collections.abc import AsyncGenerator

import pytest
from fake_camera.faults import Delay, Status
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.result import Failure, Success, Timeout
from vizenlink_nvr.timeutil import Clock


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("IDN-01")
async def test_identity_genuine_device(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Genuine camera responds with matching reply digest and returns Success(True)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001", genuine=True)
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.are_you_nuraeye_device()
    assert isinstance(res, Success)
    assert res.value is True

    assert len(cam.requests) == 1
    req = cam.requests[0]
    assert b"X-VizenLink-Camera-Id" in req.raw_header_names


@pytest.mark.behavior("IDN-01")
async def test_identity_non_genuine_device(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Camera with invalid reply digest returns Success(False)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001", genuine=False)
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.are_you_nuraeye_device()
    assert isinstance(res, Success)
    assert res.value is False


@pytest.mark.behavior("IDN-02")
async def test_identity_http_404_error(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """HTTP 404 response with error_msg returns Failure with exact error_msg."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.faults.add(
        "POST /nuraeye/identity",
        Status(
            404,
            {
                "error_code": 404,
                "error_msg": "Device does not support REST identity",
                "output": {},
            },
        ),
    )
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.are_you_nuraeye_device()
    assert isinstance(res, Failure)
    assert res.reason == "Device does not support REST identity"


@pytest.mark.behavior("IDN-02")
async def test_identity_missing_reply(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """REST response without reply field returns Failure('missing reply digest in response')."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.faults.add(
        "POST /nuraeye/identity",
        Status(
            200,
            {
                "error_code": 0,
                "error_msg": "Success",
                "output": {},
            },
        ),
    )
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.are_you_nuraeye_device()
    assert isinstance(res, Failure)
    assert res.reason == "missing reply digest in response"


@pytest.mark.behavior("IDN-02")
async def test_identity_timeout_on_delay(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Delay longer than probe timeout returns Timeout."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.faults.add("POST /nuraeye/identity", Delay(1.0))
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.are_you_nuraeye_device(timeout=0.1)
    assert isinstance(res, Timeout)
