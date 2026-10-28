"""Contract tests for NuraEye authenticated sessions and capabilities (SES-01..07, CAP-01..05)."""

import asyncio
import dataclasses
from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
from fake_camera.server import FakeCamera
from fake_camera.state import Account, CameraRole

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.capabilities import (
    Capabilities,
    RecordingMode,
    parse_capabilities,
)
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.models import LoginInfo
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache
from vizenlink_nvr.camera.result import Failure, FailureKind, Success
from vizenlink_nvr.timeutil import Clock, FakeClock


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("SES-07")
@pytest.mark.behavior("CAP-05")
async def test_tracer_authenticated_capabilities(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Tracer test: authenticate via session login, send bearer token, and parse capabilities."""
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

    res = await client.get_capabilities()
    assert isinstance(res, Success)
    assert isinstance(res.value, Capabilities)
    assert res.value.camera_id_check is True

    # Tracer acceptance criteria
    assert cam.state.login_attempts["admin"] == 1
    assert len(cam.requests) == 2

    login_req, caps_req = cam.requests[0], cam.requests[1]
    assert login_req.path == "/nuraeye/session/login"
    assert caps_req.path == "/nuraeye/capabilities"

    assert b"Authorization" in caps_req.raw_header_names
    assert b"X-VizenLink-Camera-Id" in caps_req.raw_header_names
    assert b"X-VizenLink-Camera-Id" in login_req.raw_header_names


@pytest.mark.behavior("SES-01")
async def test_session_reuse_across_calls(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """One login serves multiple authenticated calls (SES-01)."""
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)

    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)

    # Exactly 1 login attempt serves both calls
    assert cam.state.login_attempts["admin"] == 1
    assert len(cam.requests) == 3  # 1 login + 2 capabilities


@pytest.mark.behavior("SES-02")
async def test_session_refresh_when_expiring_soon(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: FakeClock,
) -> None:
    """Session expiring within leeway (15s) is refreshed without waiting for a 401 (SES-02)."""
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)
    assert cam.state.login_attempts["admin"] == 1

    # Advance clock to 10 seconds before 1800s expiry (within 15s leeway)
    fake_clock.advance(timedelta(seconds=1790))

    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)
    # Second login was triggered proactively
    assert cam.state.login_attempts["admin"] == 2


@pytest.mark.behavior("SES-03")
async def test_session_extended_on_activity(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: FakeClock,
) -> None:
    """Each successful authenticated call extends the idle window (SES-03)."""
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)
    key = NuraeyeSessionCache.session_key(conn.host, conn.username)
    sess1 = client.sessions.get(key)
    assert sess1 is not None
    initial_valid_until = sess1.valid_until

    # Advance 600s and make another call
    fake_clock.advance(timedelta(seconds=600))
    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)

    sess2 = client.sessions.get(key)
    assert sess2 is not None
    assert sess2.valid_until > initial_valid_until
    assert cam.state.login_attempts["admin"] == 1  # No re-login needed


@pytest.mark.behavior("SES-04")
async def test_session_401_retry_once(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """401 on authenticated call drops session, re-logs in and retries once (SES-04, D-09)."""
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)
    assert cam.state.login_attempts["admin"] == 1

    # Invalidate server-side sessions
    cam.state.sessions.clear()

    # Next call should receive 401, re-login once, and succeed
    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)
    assert cam.state.login_attempts["admin"] == 2


@pytest.mark.behavior("SES-04")
async def test_session_401_relogin_failure_stops(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """If re-login returns 401, returns UNAUTHORIZED without infinite loop (SES-04)."""
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)

    # Invalidate session and change password on camera so re-login fails
    cam.state.sessions.clear()
    cam.state.accounts["admin"] = Account("New-Admin-Pass-99", CameraRole.ADMINISTRATOR)

    res2 = await client.get_capabilities()
    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.UNAUTHORIZED
    assert "HTTP 401" in res2.reason
    assert cam.state.login_attempts["admin"] == 2  # exactly 1 retry


@pytest.mark.behavior("SES-05")
async def test_concurrent_calls_share_single_flight_login(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Concurrent calls share a single in-flight login (SES-05)."""
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

    # Dispatch 5 concurrent get_capabilities calls
    results = await asyncio.gather(*[client.get_capabilities() for _ in range(5)])
    for r in results:
        assert isinstance(r, Success)

    # All shared the single login
    assert cam.state.login_attempts["admin"] == 1


@pytest.mark.behavior("SES-06")
async def test_clear_session_for_host(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """clear_session_for drops cached sessions for that host (SES-06)."""
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)
    assert cam.state.login_attempts["admin"] == 1

    client.sessions.clear_session_for(conn.host)

    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)
    assert cam.state.login_attempts["admin"] == 2


async def test_d14_token_persistence_guard(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """D-14 token persistence guard: tokens exist only in SessionCache memory."""
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

    login_res = await client.login()
    assert isinstance(login_res, Success)
    login_info = login_res.value
    assert isinstance(login_info, LoginInfo)

    # Assert token attribute never exists on user-facing LoginInfo
    assert not hasattr(login_info, "token")
    info_dict = dataclasses.asdict(login_info)
    assert "token" not in info_dict

    # Verify sentinel token exists in cache
    key = NuraeyeSessionCache.session_key(conn.host, conn.username)
    cached_session = client.sessions.get(key)
    assert cached_session is not None
    sentinel_token = cached_session.token
    assert len(sentinel_token) > 0
    assert sentinel_token not in str(info_dict)


@pytest.mark.behavior("CAP-01")
def test_parse_capabilities_strict_mode() -> None:
    """strict=True requires boolean wan_command_capable and wan_live_view_capable (CAP-01)."""
    # Missing flags
    res = parse_capabilities({}, strict=True)
    assert isinstance(res, Failure)
    assert res.kind == FailureKind.BAD_RESPONSE
    assert res.reason.startswith("GetCapabilities response missing")

    # Non-boolean flags
    res2 = parse_capabilities(
        {"wan_command_capable": "yes", "wan_live_view_capable": True},
        strict=True,
    )
    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.BAD_RESPONSE
    assert res2.reason.startswith("GetCapabilities response missing")

    # Non-strict defaults to False and records in missing_required
    res3 = parse_capabilities({"wan_live_view_capable": True}, strict=False)
    assert isinstance(res3, Capabilities)
    assert res3.wan_command_capable is False
    assert res3.wan_live_view_capable is True
    assert res3.missing_required == ["wan_command_capable"]


@pytest.mark.behavior("CAP-02")
def test_parse_capabilities_defaults() -> None:
    """Missing fields default per camera_api specifications (CAP-02)."""
    caps = parse_capabilities({})
    assert isinstance(caps, Capabilities)
    assert caps.siren_capable is False
    assert caps.spotlight_capable is False
    assert caps.warning_capable is False
    assert caps.local_storage_capable is False
    assert caps.recording_clip_duration_min_seconds == 0
    assert caps.recording_clip_duration_max_seconds == 0
    assert caps.loitering_duration_min_seconds == 0
    assert caps.loitering_duration_max_seconds == 0
    assert caps.max_users == 1
    assert caps.max_recording_schedule_windows == 14
    assert caps.user_roles == []
    assert caps.supported_recording_modes == []
    assert caps.supported_event_types == []
    assert caps.supported_event_deterrence_options == {}

    import json
    from pathlib import Path

    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "fixtures"
        / "nuraeye"
        / "capabilities_minimal.json"
    )
    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))["data"]["output"]
    caps_min = parse_capabilities(fixture_data)
    assert isinstance(caps_min, Capabilities)
    assert caps_min.wan_command_capable is False
    assert caps_min.wan_live_view_capable is False
    assert caps_min.missing_required == []


@pytest.mark.behavior("CAP-03")
def test_parse_capabilities_filters_recording_modes() -> None:
    """Unknown recording modes are dropped, valid wire values preserved (CAP-03)."""
    raw = {
        "supported_recording_modes": [
            "continuous",
            "unknown_mode",
            "scheduled",
            123,
            "event_triggered",
            "motion_only",
        ]
    }
    caps = parse_capabilities(raw)
    assert isinstance(caps, Capabilities)
    assert caps.supported_recording_modes == [
        RecordingMode.CONTINUOUS,
        RecordingMode.SCHEDULED,
        RecordingMode.EVENT_TRIGGERED,
    ]


@pytest.mark.behavior("CAP-04")
def test_parse_capabilities_malformed_event_shapes() -> None:
    """Malformed event types or deterrence options are handled gracefully (CAP-04)."""
    raw = {
        "supported_event_types": "NotAList",
        "supported_event_deterrence_options": ["NotADict"],
    }
    caps = parse_capabilities(raw)
    assert isinstance(caps, Capabilities)
    assert caps.supported_event_types == []
    assert caps.supported_event_deterrence_options == {}


@pytest.mark.behavior("CAP-05")
def test_parse_capabilities_raw_and_typed_superset() -> None:
    """raw preserves unknown fields verbatim; camera_id_check and night_vision fields are typed (CAP-05)."""
    raw_input = {
        "wan_command_capable": True,
        "wan_live_view_capable": True,
        "camera_id_check": True,
        "night_vision_color_capable": True,
        "night_vision_smart_capable": True,
        "custom_future_flag": "present",
        "nested_unknown": {"foo": "bar"},
    }
    caps = parse_capabilities(raw_input)
    assert isinstance(caps, Capabilities)
    assert caps.raw == raw_input
    assert caps.raw["custom_future_flag"] == "present"
    assert caps.raw["nested_unknown"] == {"foo": "bar"}
    assert caps.camera_id_check is True
    assert caps.night_vision_color_capable is True
    assert caps.night_vision_smart_capable is True


@pytest.mark.behavior("CAP-06")
def test_parse_capabilities_keys_in_openapi_schema() -> None:
    """Every key name read by parse_capabilities exists in vendored OpenAPI capabilities schema (CAP-06)."""
    from pathlib import Path
    from typing import Any

    import yaml

    openapi_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "camera_api"
        / "design"
        / "Camera-REST-API.openapi.yaml"
    )
    with openapi_path.open("r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    cap_path = spec["paths"]["/nuraeye/capabilities"]["get"]
    resp_schema = cap_path["responses"]["200"]["content"]["application/json"]["schema"]
    all_props: dict[str, Any] = {}
    for sub in resp_schema.get("allOf", []):
        if "properties" in sub and "output" in sub["properties"]:
            all_props = sub["properties"]["output"]["properties"]
            break

    assert len(all_props) > 0, "Failed to locate capabilities output properties in OpenAPI spec"

    accessed_keys: set[str] = set()

    class KeyAuditor(dict):  # type: ignore[type-arg]
        def __getitem__(self, item: Any) -> Any:
            accessed_keys.add(str(item))
            return super().__getitem__(item)

        def get(self, item: Any, default: Any = None) -> Any:
            accessed_keys.add(str(item))
            return super().get(item, default)

        def __contains__(self, item: Any) -> bool:
            accessed_keys.add(str(item))
            return super().__contains__(item)

    test_input = KeyAuditor(
        {
            "wan_command_capable": True,
            "wan_live_view_capable": True,
            "supported_recording_modes": ["continuous"],
            "user_roles": ["Operator"],
            "supported_event_types": ["PersonDetected"],
            "supported_event_deterrence_options": {"PersonDetected": ["siren"]},
        }
    )

    _ = parse_capabilities(test_input, strict=True)
    _ = parse_capabilities(test_input, strict=False)

    for key in accessed_keys:
        assert key in all_props, f"Key '{key}' read by parse_capabilities is not in OpenAPI schema"


async def test_edge_expires_in_sec_zero(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """expires_in_sec 0 forces a fresh login before every call."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")

    # Configure simulator to return expires_in_sec = 0
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

    res1 = await client.get_capabilities()
    assert isinstance(res1, Success)
    assert cam.state.login_attempts["admin"] == 1

    res2 = await client.get_capabilities()
    assert isinstance(res2, Success)
    assert cam.state.login_attempts["admin"] == 2
