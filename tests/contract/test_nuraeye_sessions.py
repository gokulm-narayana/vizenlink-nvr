"""Contract tests for NuraEye session caching and lifecycle semantics (SES-01..07)."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.models import LoginInfo
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache, Session
from vizenlink_nvr.camera.result import Failure, FailureKind, Success
from vizenlink_nvr.timeutil import Clock, FakeClock


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure clean teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("SES-01")
async def test_ses_01_ten_calls_one_login(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Ten get_capabilities calls result in exactly one login request (SES-01)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    for _ in range(10):
        res = await client.get_capabilities()
        assert isinstance(res, Success)

    assert cam.state.login_attempts["admin"] == 1
    assert len(cam.requests) == 11  # 1 login + 10 capabilities calls


@pytest.mark.behavior("SES-02")
async def test_ses_02_expires_in_sec_zero_forces_refresh_no_401(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """rest_settings(sim).expires_in_sec = 0 triggers login before every call, no 401 seen by sim (SES-02)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    from fake_camera.routes.rest_session import rest_settings

    rest_settings(cam).expires_in_sec = 0

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    for i in range(3):
        res = await client.get_capabilities()
        assert isinstance(res, Success)
        assert cam.state.login_attempts["admin"] == i + 1

    # Verify that the sim never sent or recorded a 401 on capabilities
    assert len(cam.requests) == 6  # 3 login + 3 capabilities


@pytest.mark.behavior("SES-03")
async def test_ses_03_calls_extend_idle_window(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: FakeClock,
) -> None:
    """With expires_in_sec 60, advancing FakeClock 50s between ten calls produces 1 login (SES-03)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    from fake_camera.routes.rest_session import rest_settings

    rest_settings(cam).expires_in_sec = 60

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    for _ in range(10):
        res = await client.get_capabilities()
        assert isinstance(res, Success)
        fake_clock.advance(timedelta(seconds=50))

    assert cam.state.login_attempts["admin"] == 1


@pytest.mark.behavior("SES-04")
async def test_ses_04_token_invalidation_retry_and_changed_password(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Invalidated token triggers 401, re-login, retry; changed password stops at UNAUTHORIZED (SES-04)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    # Initial successful call
    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)
    assert cam.state.login_attempts["admin"] == 1

    # Part A: Sim drops session -> client gets 401, re-logs in once, retries and succeeds
    cam.state.sessions.clear()
    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)
    assert cam.state.login_attempts["admin"] == 2

    # Part B: Password changed on sim -> re-login gets 401, returns UNAUTHORIZED, exactly 1 new login
    cam.state.sessions.clear()
    cam.state.accounts["admin"] = Account("New-Secret-99", CameraRole.ADMINISTRATOR)

    res3 = await client.get_capabilities()
    assert isinstance(res3, Failure)
    assert res3.kind == FailureKind.UNAUTHORIZED
    assert "HTTP 401" in res3.reason
    assert cam.state.login_attempts["admin"] == 3  # exactly 1 login request after the 401

    # Following call makes one new login attempt only because caller asked again
    res4 = await client.get_capabilities()
    assert isinstance(res4, Failure)
    assert res4.kind == FailureKind.UNAUTHORIZED
    assert cam.state.login_attempts["admin"] == 4


@pytest.mark.behavior("SES-05")
async def test_ses_05_concurrent_callers_single_login(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Five concurrent get_capabilities calls on an empty cache produce exactly 1 login (SES-05)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    results = await asyncio.gather(*[client.get_capabilities() for _ in range(5)])
    for r in results:
        assert isinstance(r, Success)

    assert cam.state.login_attempts["admin"] == 1


@pytest.mark.behavior("SES-06")
def test_ses_06_clear_session_for_host(fake_clock: Clock) -> None:
    """clear_session_for('h') removes ('h', 'admin') and ('h', 'op1') but keeps ('h2', 'admin') (SES-06)."""
    cache = NuraeyeSessionCache(fake_clock)
    now = fake_clock.now()

    sess_h_admin = Session(
        token="tok1",
        expires_in_sec=1800,
        valid_until=now + timedelta(seconds=1800),
        username="admin",
        role="Administrator",
        password_change_required=False,
    )
    sess_h_op = Session(
        token="tok2",
        expires_in_sec=1800,
        valid_until=now + timedelta(seconds=1800),
        username="operator1",
        role="Operator",
        password_change_required=False,
    )
    sess_h2_admin = Session(
        token="tok3",
        expires_in_sec=1800,
        valid_until=now + timedelta(seconds=1800),
        username="admin",
        role="Administrator",
        password_change_required=False,
    )

    cache.put("192.168.1.10|admin", sess_h_admin)
    cache.put("192.168.1.10|operator1", sess_h_op)
    cache.put("192.168.1.20|admin", sess_h2_admin)

    cache.clear_session_for("192.168.1.10")

    assert cache.get("192.168.1.10|admin") is None
    assert cache.get("192.168.1.10|operator1") is None
    assert cache.get("192.168.1.20|admin") is not None


@pytest.mark.behavior("SES-07")
async def test_ses_07_login_without_token_and_parsed_fields(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Login without token yields exact reason; role and password_change_required parsed (SES-07)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    # Successful login parses role and password_change_required
    login_res = await client.login()
    assert isinstance(login_res, Success)
    assert isinstance(login_res.value, LoginInfo)
    assert login_res.value.username == "admin"
    assert login_res.value.role == "Administrator"
    assert login_res.value.password_change_required is False

    # Simulate empty token in login response
    from fake_camera.faults import Status

    cam.faults.add(
        "POST /nuraeye/session/login",
        Status(
            code=200,
            json_body={"error_code": 0, "error_msg": "Success", "output": {"expires_in_sec": 1800}},
        ),
    )
    client.sessions.clear_session_for(conn.host)

    res_no_token = await client.login()
    assert isinstance(res_no_token, Failure)
    assert res_no_token.reason == "session/login succeeded but returned no token"
