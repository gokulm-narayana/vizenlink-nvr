"""Unit tests for simulated camera state, authority, lockout, and WS-Discovery."""

import asyncio
import socket
from datetime import datetime, timedelta

import pytest
from fake_camera.discovery import DiscoveryResponder
from fake_camera.server import FakeCamera
from fake_camera.state import CameraState

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.result import Failure, FailureKind
from vizenlink_nvr.camera.roles import CameraRole
from vizenlink_nvr.camera.wsse import compute_digest
from vizenlink_nvr.timeutil import UTC, FakeClock


def test_factory_state_defaults() -> None:
    """Verify camera factory state defaults: admin/password, flags set."""
    state = CameraState()
    assert "admin" in state.accounts
    assert state.accounts["admin"].password == "password"
    assert state.accounts["admin"].role == CameraRole.ADMINISTRATOR
    assert state.default_password_in_use is True
    assert state.first_password_gate is True
    assert state.session_table_size == 10


def test_lru_session_eviction() -> None:
    """The 11th login evicts the least recently active session token."""
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    state = CameraState(session_table_size=10, clock=clock)

    tokens: list[str] = []
    for _ in range(10):
        clock.advance(timedelta(seconds=1))
        tok = state.issue_token("admin", CameraRole.ADMINISTRATOR)
        tokens.append(tok)

    # First token should still be valid
    assert state.authenticate_bearer(tokens[0]) is not None

    # Advance clock and issue 11th token
    clock.advance(timedelta(seconds=1))
    tok_11 = state.issue_token("admin", CameraRole.ADMINISTRATOR)

    # Token 1 (second token created, which wasn't refreshed) should be evicted
    assert state.authenticate_bearer(tokens[1]) is None
    # Token 0 (refreshed above) and Token 11 should be present
    assert state.authenticate_bearer(tokens[0]) is not None
    assert state.authenticate_bearer(tok_11) is not None
    assert len(state.sessions) == 10


def test_lockout_after_five_failures() -> None:
    """5 consecutive failures lock out the user with retry_after_seconds 15 (doubling to 30 for admin)."""
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    state = CameraState(clock=clock)
    nonce = "AAAAAAAAAAAAAAAAAAAAAA=="
    created = "2026-01-01T12:00:00.000Z"
    bad_digest = compute_digest("wrong-password", nonce_b64=nonce, created=created)

    for _ in range(4):
        acc, _ = state.verify_rest_login("admin", bad_digest, nonce, created)
        assert acc is None
        assert state.blocked_for("admin") is None

    # 5th failure triggers lockout
    acc5, _ = state.verify_rest_login("admin", bad_digest, nonce, created)
    assert acc5 is None
    remaining = state.blocked_for("admin")
    assert remaining == 15

    # 6th failure doubles to 30
    acc6, _ = state.verify_rest_login("admin", bad_digest, nonce, created)
    assert acc6 is None
    remaining2 = state.blocked_for("admin")
    assert remaining2 == 30

    # Advance clock past 30 seconds -> unblocked
    clock.advance(timedelta(seconds=31))
    assert state.blocked_for("admin") is None


def test_password_change_rules() -> None:
    """Setting password rejects 'password' in any case and clears the first password gate."""
    state = CameraState()
    with pytest.raises(ValueError, match="password_not_allowed"):
        state.set_password("admin", "PASSWORD")

    with pytest.raises(ValueError, match="password_not_allowed"):
        state.set_password("admin", "password")

    state.set_password("admin", "NewSecurePass123!")
    assert state.accounts["admin"].password == "NewSecurePass123!"
    assert state.first_password_gate is False
    assert state.default_password_in_use is False


def test_wsse_credential_classification() -> None:
    """verify_wsse classifies blank, stored, and other correctly without storing plaintext."""
    state = CameraState()
    nonce = "AAAAAAAAAAAAAAAAAAAAAA=="
    created = "2026-01-01T12:00:00.000Z"

    # Blank
    acc_blank, cred_blank = state.verify_wsse("", nonce, created, "")
    assert acc_blank is None
    assert cred_blank == "blank"

    # Stored admin password
    admin_digest = compute_digest("password", nonce_b64=nonce, created=created)
    acc_stored, cred_stored = state.verify_wsse("admin", nonce, created, admin_digest)
    assert acc_stored is not None
    assert cred_stored == "stored"

    # Other / wrong password
    bad_digest = compute_digest("invalid", nonce_b64=nonce, created=created)
    acc_other, cred_other = state.verify_wsse("admin", nonce, created, bad_digest)
    assert acc_other is None
    assert cred_other == "other"


@pytest.mark.behavior("HTTP-07")
async def test_camera_id_precedence_over_auth(
    fake_camera: pytest.FixtureRequest,
) -> None:
    """Wrong camera ID with wrong password yields 421, not 401."""
    cam: FakeCamera = await fake_camera(serial="VZL-ACTUAL")
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-WRONG-ID",
        tls_pin_sha256=cam.cert_sha256,
    )
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        # Request with wrong camera id and wrong password
        resp = await http.send(
            conn,
            "POST",
            "/nuraeye/identity",
            headers=[("Authorization", "Basic d3Jvbmc6d3Jvbmc=")],
            timeout=2.0,
        )
        assert isinstance(resp, Failure)
        assert resp.kind == FailureKind.ID_MISMATCH
        assert resp.http_status == 421
    finally:
        await http.aclose()


async def test_identity_probe_leaves_no_credentials(
    fake_camera: pytest.FixtureRequest,
    fake_clock: FakeClock,
) -> None:
    """requests_with_credentials() returns empty list after only identity probe."""
    cam: FakeCamera = await fake_camera(serial="VZL-1")
    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-1",
        tls_pin_sha256=cam.cert_sha256,
    )
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        client = NuraeyeClient(conn, http, fake_clock)
        await client.are_you_nuraeye_device()

        assert len(cam.requests) == 1
        assert cam.requests[0].credential_use == "none"
        assert len(cam.requests_with_credentials()) == 0
    finally:
        await http.aclose()


async def test_discovery_responder_udp_probe(
    fake_camera: pytest.FixtureRequest,
    discovery_responder: DiscoveryResponder,
) -> None:
    """DiscoveryResponder answers UDP probe with expected XML scopes and XAddrs."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-DISC-001",
        mac="AA:BB:CC:11:22:33",
        name="Front Gate",
        location="Main Entrance",
    )

    probe_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"'
        '               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">'
        "  <soap:Header>"
        "    <wsa:MessageID>urn:uuid:12345678-1234-1234-1234-123456789abc</wsa:MessageID>"
        "  </soap:Header>"
        "  <soap:Body/>"
        "</soap:Envelope>"
    )

    # Send UDP probe to discovery responder
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    sock.sendto(probe_xml.encode("utf-8"), ("127.0.0.1", discovery_responder.port))

    data, _ = await asyncio.to_thread(sock.recvfrom, 65535)
    sock.close()

    resp_str = data.decode("utf-8")
    assert "ProbeMatches" in resp_str
    assert "tdn:NetworkVideoTransmitter" in resp_str or "NetworkVideoTransmitter" in resp_str
    assert f"https://{cam.host}:{cam.port}/onvif/device_service" in resp_str
    assert "onvif://www.onvif.org/MAC/AA:BB:CC:11:22:33" in resp_str
    assert "urn:uuid:12345678-1234-1234-1234-123456789abc" in resp_str
