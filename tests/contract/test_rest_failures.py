"""Contract tests for NuraEye REST failure mapping and lockout delay parsing (RES-03..05)."""

import json
from collections.abc import AsyncGenerator
from datetime import timedelta
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.result import Failure, FailureKind, parse_retry_after
from vizenlink_nvr.timeutil import Clock

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "nuraeye"


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure clean teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("RES-03")
def test_res_03_parse_retry_after_precedence() -> None:
    """parse_retry_after precedence: retry_after_seconds first, regex second, None fallback (RES-03)."""
    # 1. retry_after_seconds present
    assert parse_retry_after({"retry_after_seconds": 30}, "no number") == timedelta(seconds=30)

    # 2. regex in message present
    assert parse_retry_after({}, "Too many failed attempts (retry in 12 s)") == timedelta(seconds=12)

    # 3. both present -> retry_after_seconds takes precedence (30s, not 12s)
    assert parse_retry_after({"retry_after_seconds": 30}, "Too many attempts (retry in 12 s)") == timedelta(
        seconds=30
    )

    # 4. neither present -> None
    assert parse_retry_after({}, "Too many failed attempts") is None
    assert parse_retry_after(None, "Generic error message") is None


@pytest.mark.behavior("RES-04")
async def test_res_04_status_403_forbidden_no_relogin(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """403 yields FORBIDDEN and client does NOT trigger re-login (RES-04, D-10)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    fixture_data = json.loads((FIXTURES_DIR / "error_403.json").read_text(encoding="utf-8"))["data"]
    cam.faults.add("GET /nuraeye/capabilities", Status(code=403, json_body=fixture_data))

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.get_capabilities()
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.FORBIDDEN
    assert res.http_status == 403
    assert res.reason == "Not permitted for this user role"

    # Acceptance criteria: zero additional login requests
    assert cam.state.login_attempts["admin"] == 1


@pytest.mark.behavior("RES-04")
async def test_res_04_status_428_password_change_required(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """428 yields PASSWORD_CHANGE_REQUIRED (RES-04)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    fixture_data = json.loads((FIXTURES_DIR / "error_428.json").read_text(encoding="utf-8"))["data"]
    cam.faults.add("GET /nuraeye/capabilities", Status(code=428, json_body=fixture_data))

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.get_capabilities()
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.PASSWORD_CHANGE_REQUIRED
    assert res.http_status == 428
    assert res.reason == "Set a new Administrator password first"


@pytest.mark.behavior("RES-04")
async def test_res_04_status_429_blocked_with_fixtures(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """429 yields BLOCKED with retry_after parsed from field or message (RES-04)."""
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

    # 1. 429 with retry_after_seconds field (error_429_retry_field.json)
    fixture_field = json.loads((FIXTURES_DIR / "error_429_retry_field.json").read_text(encoding="utf-8"))[
        "data"
    ]
    cam.faults.add("GET /nuraeye/capabilities", Status(code=429, json_body=fixture_field))

    res1 = await client.get_capabilities()
    assert isinstance(res1, Failure)
    assert res1.kind == FailureKind.BLOCKED
    assert res1.http_status == 429
    assert res1.retry_after == timedelta(seconds=60)

    # 2. 429 with message only (error_429_message_only.json)
    fixture_msg = json.loads((FIXTURES_DIR / "error_429_message_only.json").read_text(encoding="utf-8"))[
        "data"
    ]
    cam.faults.add("GET /nuraeye/capabilities", Status(code=429, json_body=fixture_msg))

    res2 = await client.get_capabilities()
    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.BLOCKED
    assert res2.http_status == 429
    assert res2.retry_after == timedelta(seconds=60)


@pytest.mark.behavior("RES-04")
async def test_res_04_status_500_generic(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """500 yields GENERIC failure with HTTP 500: <msg> reason (RES-04)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    cam.faults.add(
        "GET /nuraeye/capabilities",
        Status(
            code=500,
            json_body={"error_code": 500, "error_msg": "Internal sensor fault", "output": {}},
        ),
    )

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.get_capabilities()
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.GENERIC
    assert res.http_status == 500
    assert res.reason == "HTTP 500: Internal sensor fault"


@pytest.mark.behavior("RES-05")
async def test_res_05_status_401_reason_format(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """401 failure reason contains '401' and the camera's error_msg (RES-05)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Wrong-Password",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.login()
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.UNAUTHORIZED
    assert res.http_status == 401
    assert "401" in res.reason
    assert "Invalid credentials" in res.reason
