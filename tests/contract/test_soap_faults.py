"""Contract tests for ONVIF SOAP fault mapping and WSSE header structure (SOAP-01..07, WSSE-03)."""

import unittest.mock as mock
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp, HttpResponse
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.soap import (
    build_envelope,
    post_soap,
    soap_fault_reason,
    soap_fault_subcode,
)
from vizenlink_nvr.camera.result import Failure, FailureKind
from vizenlink_nvr.camera.wsse import make_token
from vizenlink_nvr.timeutil import Clock, FakeClock

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "onvif"


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure clean teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("SOAP-01")
async def test_soap_01_http200_fault(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """HTTP 200 with a Fault body yields Failure with fault Reason text (SOAP-01)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    fault_xml = (FIXTURES_DIR / "fault_http200.xml").read_text(encoding="utf-8")
    cam.faults.add(
        "POST /onvif/device_service",
        Status(code=200, json_body=None),
    )

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )

    # Direct fault parser check
    assert soap_fault_reason(fault_xml) == "Invalid argument value"

    # End-to-end check via post_soap
    async def mock_fault_http(*args: object, **kwargs: object) -> HttpResponse:
        return HttpResponse(status=200, headers=[], body=fault_xml.encode("utf-8"))

    with mock.patch.object(http_client, "send", side_effect=mock_fault_http):
        res = await post_soap(
            http_client,
            conn,
            "/onvif/device_service",
            "<test/>",
            clock=fake_clock,
        )

    assert isinstance(res, Failure)
    assert res.reason == "Invalid argument value"
    assert res.http_status == 200


@pytest.mark.behavior("SOAP-02")
def test_soap_02_nested_subcode() -> None:
    """Subcode ter:InvalidArgVal nested under ter:InvalidArgs -> reason suffix and fault_subcode (SOAP-02)."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        "<s:Fault>"
        "<s:Code><s:Value>s:Sender</s:Value>"
        "<s:Subcode><s:Value>ter:InvalidArgs</s:Value>"
        "<s:Subcode><s:Value>ter:InvalidArgVal</s:Value></s:Subcode></s:Subcode></s:Code>"
        '<s:Reason><s:Text xml:lang="en">Validation failed</s:Text></s:Reason>'
        "</s:Fault>"
        "</s:Body>"
        "</s:Envelope>"
    )

    subcode = soap_fault_subcode(xml)
    assert subcode == "InvalidArgVal"
    reason = soap_fault_reason(xml)
    assert reason == "Validation failed"


@pytest.mark.behavior("SOAP-03")
async def test_soap_03_insufficient_user_level_is_forbidden(
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """InsufficientUserLevel fault at HTTP 400 yields FORBIDDEN, not UNAUTHORIZED (SOAP-03)."""
    fault_xml = (FIXTURES_DIR / "fault_insufficient_user_level.xml").read_text(encoding="utf-8")

    conn = CameraConnection(
        host="127.0.0.1",
        port=80,
        username="operator1",
        password="Op-Pass-01",
    )

    async def mock_fault_http(*args: object, **kwargs: object) -> HttpResponse:
        return HttpResponse(status=400, headers=[], body=fault_xml.encode("utf-8"))

    with mock.patch.object(http_client, "send", side_effect=mock_fault_http):
        res = await post_soap(
            http_client,
            conn,
            "/onvif/device_service",
            "<test/>",
            clock=fake_clock,
        )

    assert isinstance(res, Failure)
    assert res.kind == FailureKind.FORBIDDEN
    assert res.kind != FailureKind.UNAUTHORIZED
    assert res.http_status == 400
    assert "not permitted to perform this operation" in res.reason


@pytest.mark.behavior("SOAP-04")
async def test_soap_04_too_many_attempts_blocked(
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """TooManyAttempts fault and bare 429 both yield BLOCKED and neither is FORBIDDEN (SOAP-04)."""
    fault_xml = (FIXTURES_DIR / "fault_too_many_attempts.xml").read_text(encoding="utf-8")
    conn = CameraConnection(host="127.0.0.1", port=80, username="admin", password="pw")

    # 1. SOAP fault TooManyAttempts at HTTP 429
    with mock.patch.object(
        http_client,
        "send",
        return_value=HttpResponse(status=429, headers=[], body=fault_xml.encode("utf-8")),
    ):
        res1 = await post_soap(http_client, conn, "/onvif/device_service", "<test/>", clock=fake_clock)

    assert isinstance(res1, Failure)
    assert res1.kind == FailureKind.BLOCKED
    assert res1.kind != FailureKind.FORBIDDEN

    # 2. Bare HTTP 429 without SOAP fault
    with mock.patch.object(
        http_client,
        "send",
        return_value=HttpResponse(status=429, headers=[], body=b"Rate limited"),
    ):
        res2 = await post_soap(http_client, conn, "/onvif/device_service", "<test/>", clock=fake_clock)

    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.BLOCKED
    assert res2.kind != FailureKind.FORBIDDEN


@pytest.mark.behavior("SOAP-05")
async def test_soap_05_password_change_required(
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """PasswordChangeRequired fault at 428 and bare 428 both yield PASSWORD_CHANGE_REQUIRED (SOAP-05)."""
    fault_xml = (FIXTURES_DIR / "fault_password_change_required.xml").read_text(encoding="utf-8")
    conn = CameraConnection(host="127.0.0.1", port=80, username="admin", password="password")

    # 1. SOAP fault at HTTP 428
    with mock.patch.object(
        http_client,
        "send",
        return_value=HttpResponse(status=428, headers=[], body=fault_xml.encode("utf-8")),
    ):
        res1 = await post_soap(http_client, conn, "/onvif/device_service", "<test/>", clock=fake_clock)

    assert isinstance(res1, Failure)
    assert res1.kind == FailureKind.PASSWORD_CHANGE_REQUIRED

    # 2. Bare HTTP 428 without SOAP
    with mock.patch.object(
        http_client,
        "send",
        return_value=HttpResponse(status=428, headers=[], body=b"Precondition Required"),
    ):
        res2 = await post_soap(http_client, conn, "/onvif/device_service", "<test/>", clock=fake_clock)

    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.PASSWORD_CHANGE_REQUIRED


@pytest.mark.behavior("SOAP-06")
async def test_soap_06_http502_html_generic(
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """HTTP 502 with HTML body yields GENERIC 'HTTP 502: <body>' (SOAP-06)."""
    conn = CameraConnection(host="127.0.0.1", port=80, username="admin", password="pw")

    html_body = b"<html><body>502 Bad Gateway</body></html>"
    with mock.patch.object(
        http_client,
        "send",
        return_value=HttpResponse(status=502, headers=[], body=html_body),
    ):
        res = await post_soap(http_client, conn, "/onvif/device_service", "<test/>", clock=fake_clock)

    assert isinstance(res, Failure)
    assert res.kind == FailureKind.GENERIC
    assert res.reason == "HTTP 502: <html><body>502 Bad Gateway</body></html>"
    assert res.http_status == 502


@pytest.mark.behavior("SOAP-07")
async def test_soap_07_http421_camera_id_mismatch(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """HTTP 421 yields ID_MISMATCH and reason contains 'Camera ID mismatch' (SOAP-07)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    # Mismatching camera serial in connection
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-999999",  # Wrong serial -> simulator answers 421
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifDeviceClient(conn, http_client, fake_clock)

    res = await client.get_serial_number()
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.ID_MISMATCH
    assert "Camera ID mismatch" in res.reason


@pytest.mark.behavior("WSSE-03")
def test_wsse_03_envelope_structure_and_escaping() -> None:
    """Envelope has UsernameToken, PasswordDigest, Base64Binary, .000Z Created, and XML escaping (WSSE-03)."""
    clock = FakeClock(datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))
    token = make_token("Secret-123", clock)

    envelope = build_envelope("<tds:GetScopes/>", "a&b<c>d'\"e", token)

    assert "<wsse:UsernameToken>" in envelope
    assert (
        'Password Type="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-username-token-profile-1.0#PasswordDigest"' in envelope
    )
    assert (
        'Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-soap-message-security-1.0#Base64Binary"' in envelope
    )
    assert "<wsu:Created" in envelope
    assert token.created.endswith(".000Z")
    assert f">{token.created}</wsu:Created>" in envelope

    # Escaping verification
    assert "<wsse:Username>a&amp;b&lt;c&gt;d&apos;&quot;e</wsse:Username>" in envelope


@pytest.mark.behavior("WSSE-03")
async def test_wsse_03_not_authorized_fault_is_unauthorized(
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """ter:NotAuthorized fault at 200/400/401 yields UNAUTHORIZED (WSSE-03)."""
    not_auth_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        "<s:Body>"
        "<s:Fault>"
        "<s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode></s:Code>"
        '<s:Reason><s:Text xml:lang="en">Sender not authorized</s:Text></s:Reason>'
        "</s:Fault>"
        "</s:Body>"
        "</s:Envelope>"
    )
    conn = CameraConnection(host="127.0.0.1", port=80, username="admin", password="bad")

    for status in (200, 400, 401):
        with mock.patch.object(
            http_client,
            "send",
            return_value=HttpResponse(status=status, headers=[], body=not_auth_xml.encode("utf-8")),
        ):
            res = await post_soap(http_client, conn, "/onvif/device_service", "<test/>", clock=fake_clock)
        assert isinstance(res, Failure)
        assert res.kind == FailureKind.UNAUTHORIZED
