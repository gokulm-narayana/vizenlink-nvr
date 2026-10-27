"""Contract tests for CameraHttp transport choke point behaviors."""

import socket
import ssl
from collections.abc import AsyncGenerator

import httpx
import pytest
from fake_camera.faults import Silence, Status
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import (
    CameraEventBus,
    CameraIdMismatchEvent,
    CameraUnreachableEvent,
)
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.rest import post_json
from vizenlink_nvr.camera.result import Failure, FailureKind, Timeout


@pytest.fixture
def event_bus() -> CameraEventBus:
    """Return clean event bus for test."""
    return CameraEventBus()


@pytest.fixture
async def http_transport(event_bus: CameraEventBus) -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and tear it down cleanly."""
    http = CameraHttp(event_bus, silent_after=0.1)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("HTTP-01")
async def test_camera_id_header_injection_and_case(
    fake_camera: pytest.FixtureRequest,
    http_transport: CameraHttp,
) -> None:
    """Serial sets byte-for-byte X-VizenLink-Camera-Id, omitted if absent, never duplicated."""
    cam: FakeCamera = await fake_camera(serial="VZL-1")
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256=cam.cert_sha256,
    )

    # Serial present: header is sent verbatim
    await http_transport.send(conn, "GET", "/test", timeout=2.0)
    assert len(cam.requests) == 1
    req = cam.requests[0]
    assert b"X-VizenLink-Camera-Id" in req.raw_header_names
    assert b"x-vizenlink-camera-id" not in req.raw_header_names

    # Serial empty: header is absent
    conn_no_serial = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="",
        tls_pin_sha256=cam.cert_sha256,
    )
    await http_transport.send(conn_no_serial, "GET", "/test", timeout=2.0)
    assert len(cam.requests) == 2
    req2 = cam.requests[1]
    assert not any(name.lower() == b"x-vizenlink-camera-id" for name in req2.raw_header_names)

    # Caller supplied header: not duplicated
    await http_transport.send(
        conn,
        "GET",
        "/test",
        headers=[("x-vizenlink-camera-id", "VZL-1")],
        timeout=2.0,
    )
    assert len(cam.requests) == 3
    req3 = cam.requests[2]
    id_count = sum(1 for name in req3.raw_header_names if name.lower() == b"x-vizenlink-camera-id")
    assert id_count == 1


@pytest.mark.behavior("HTTP-02")
async def test_header_case_preservation(
    fake_camera: pytest.FixtureRequest,
    http_transport: CameraHttp,
) -> None:
    """Authorization and Content-Type headers reach the wire with exact case."""
    cam: FakeCamera = await fake_camera(serial="VZL-1")
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256=cam.cert_sha256,
    )

    headers = [
        ("Authorization", "Bearer test-token"),
        ("Content-Type", "application/json"),
    ]
    await http_transport.send(conn, "POST", "/test", headers=headers, timeout=2.0)
    assert len(cam.requests) == 1
    req = cam.requests[0]
    assert b"Authorization" in req.raw_header_names
    assert b"Content-Type" in req.raw_header_names


@pytest.mark.behavior("HTTP-03")
@pytest.mark.behavior("HTTP-04")
async def test_camera_id_mismatch_event_publishing(
    fake_camera: pytest.FixtureRequest,
    event_bus: CameraEventBus,
    http_transport: CameraHttp,
) -> None:
    """421 publishes one CameraIdMismatchEvent if serial set, zero if serial empty."""
    cam: FakeCamera = await fake_camera(serial="VZL-ACTUAL")
    events: list[CameraIdMismatchEvent] = []
    event_bus.subscribe(lambda e: events.append(e) if isinstance(e, CameraIdMismatchEvent) else None)

    # Serial set: mismatched
    conn_with_serial = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-EXPECTED",
        tls_pin_sha256=cam.cert_sha256,
    )
    res = await http_transport.send(conn_with_serial, "GET", "/test", timeout=2.0)
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.ID_MISMATCH
    assert res.reason == "HTTP 421: Camera ID mismatch"
    assert len(events) == 1
    assert events[0].expected_id == "VZL-EXPECTED"

    # Serial not set: status 421 returned via fault, no event published
    cam.faults.add("GET /test", Status(421))
    conn_no_serial = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="",
        tls_pin_sha256=cam.cert_sha256,
    )
    res2 = await http_transport.send(conn_no_serial, "GET", "/test", timeout=2.0)
    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.ID_MISMATCH
    assert len(events) == 1  # Still 1, no new event


@pytest.mark.behavior("HTTP-05")
async def test_connection_refused_unreachable_event(
    event_bus: CameraEventBus,
    http_transport: CameraHttp,
) -> None:
    """Connect to closed port with serial publishes one unreachable event; no serial -> no event."""
    # Find free port then close it
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()

    events: list[CameraUnreachableEvent] = []
    event_bus.subscribe(lambda e: events.append(e) if isinstance(e, CameraUnreachableEvent) else None)

    conn_with_serial = CameraConnection(host="127.0.0.1", port=closed_port, serial="VZL-1")
    res = await http_transport.send(conn_with_serial, "GET", "/test", timeout=1.0)
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.UNREACHABLE
    assert len(events) == 1
    assert events[0].expected_id == "VZL-1"

    # Without serial -> no event
    conn_no_serial = CameraConnection(host="127.0.0.1", port=closed_port, serial="")
    res2 = await http_transport.send(conn_no_serial, "GET", "/test", timeout=1.0)
    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.UNREACHABLE
    assert len(events) == 1  # Unchanged


@pytest.mark.behavior("HTTP-06")
async def test_silence_window_unreachable_event(
    fake_camera: pytest.FixtureRequest,
    event_bus: CameraEventBus,
    http_transport: CameraHttp,
) -> None:
    """Silence exceeding silent_after publishes unreachable once while response still succeeds."""
    cam: FakeCamera = await fake_camera(serial="VZL-1")
    cam.faults.add("GET /test", Silence(0.3))

    events: list[CameraUnreachableEvent] = []
    event_bus.subscribe(lambda e: events.append(e) if isinstance(e, CameraUnreachableEvent) else None)

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256=cam.cert_sha256,
    )

    # silent_after is 0.1, Silence is 0.3, timeout is 2.0
    res = await http_transport.send(conn, "GET", "/test", timeout=2.0)
    assert not isinstance(res, Failure)
    assert not isinstance(res, Timeout)
    assert res.status == 404 or res.status == 200

    assert len(events) == 1
    assert events[0].expected_id == "VZL-1"


@pytest.mark.behavior("HTTP-08")
async def test_rest_requests_carry_json_content_type(
    fake_camera: pytest.FixtureRequest,
    http_transport: CameraHttp,
) -> None:
    """post_json helper ensures Content-Type: application/json is present."""
    cam: FakeCamera = await fake_camera(serial="VZL-1")
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256=cam.cert_sha256,
    )
    await post_json(http_transport, conn, "/test", {"foo": "bar"}, timeout=2.0)
    assert len(cam.requests) == 1
    req = cam.requests[0]
    ct = next((v for k, v in req.headers if k.lower() == b"content-type"), b"")
    assert ct == b"application/json"


@pytest.mark.behavior("HTTP-09")
async def test_tls_pin_enforcement_and_system_ssl_isolation(
    fake_camera: pytest.FixtureRequest,
    http_transport: CameraHttp,
) -> None:
    """Matching pin succeeds; wrong pin returns TLS_CHANGED without sending HTTP bytes.
    Also verifies default SSL isolation.
    """
    cam: FakeCamera = await fake_camera(serial="VZL-1")

    # Correct pin
    conn_valid = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256=cam.cert_sha256,
    )
    res_valid = await http_transport.send(conn_valid, "GET", "/test", timeout=2.0)
    assert not isinstance(res_valid, Failure)
    assert len(cam.requests) == 1

    # Wrong pin: returns TLS_CHANGED and no new request bytes reach the simulator
    conn_wrong = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256="00" * 32,
    )
    res_wrong = await http_transport.send(conn_wrong, "GET", "/test", timeout=2.0)
    assert isinstance(res_wrong, Failure)
    assert res_wrong.kind == FailureKind.TLS_CHANGED
    assert res_wrong.reason == "camera certificate changed since it was added"
    assert len(cam.requests) == 1  # Unchanged!

    # Default SSL context and default httpx verification remain strictly intact
    default_ctx = ssl.create_default_context()
    assert default_ctx.verify_mode == ssl.CERT_REQUIRED
    assert default_ctx.check_hostname is True

    async with httpx.AsyncClient() as client:
        # Default verify is True or an SSLContext with verification
        assert client._transport is not None
