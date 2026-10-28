"""Contract tests for NuraEye live stream URI resolution (LST-01..03, CAM-07)."""

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fake_camera.faults import Status
from fake_camera.routes.rest_session import rest_settings
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.live_stream_uri import (
    MAIN_PROFILE_TOKEN,
    MOBILE_ONLY_PROFILE_TOKEN,
    SUB_PROFILE_TOKEN,
    LiveStreamUri,
    parse_live_stream_uri,
)
from vizenlink_nvr.camera.result import Failure, FailureKind, Success
from vizenlink_nvr.timeutil import Clock

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "nuraeye"


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("LST-01")
async def test_lst_01_profile_mapping_and_payload(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """Profile_1 -> 554 /high; Profile_2 -> 555 /medium; Profile_3 -> 556 /mobile (LST-01)."""
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

    # 1. Profile_1 (Main)
    res1 = await client.get_live_stream_uri(MAIN_PROFILE_TOKEN)
    assert isinstance(res1, Success)
    assert isinstance(res1.value, LiveStreamUri)
    assert res1.value.transport == "rtsp"
    assert res1.value.port == 554
    assert res1.value.path == "/high"
    assert res1.value.scheme == "rtsps"
    assert res1.value.url == f"rtsps://{cam.host}:554/high"

    # Verify request body for Profile_1
    req1 = [r for r in cam.requests if r.path == "/nuraeye/live-stream-uri"][-1]
    assert json.loads(req1.body.decode("utf-8")) == {"profile_token": "Profile_1"}

    # 2. Profile_2 (Sub)
    res2 = await client.get_live_stream_uri(SUB_PROFILE_TOKEN)
    assert isinstance(res2, Success)
    assert res2.value.transport == "rtsp"
    assert res2.value.port == 555
    assert res2.value.path == "/medium"
    assert res2.value.scheme == "rtsps"
    assert res2.value.url == f"rtsps://{cam.host}:555/medium"

    req2 = [r for r in cam.requests if r.path == "/nuraeye/live-stream-uri"][-1]
    assert json.loads(req2.body.decode("utf-8")) == {"profile_token": "Profile_2"}

    # 3. Profile_3 (Mobile only)
    res3 = await client.get_live_stream_uri(MOBILE_ONLY_PROFILE_TOKEN)
    assert isinstance(res3, Success)
    assert res3.value.transport == "rtsp"
    assert res3.value.port == 556
    assert res3.value.path == "/mobile"
    assert res3.value.scheme == "rtsps"
    assert res3.value.url == f"rtsps://{cam.host}:556/mobile"

    req3 = [r for r in cam.requests if r.path == "/nuraeye/live-stream-uri"][-1]
    assert json.loads(req3.body.decode("utf-8")) == {"profile_token": "Profile_3"}


@pytest.mark.behavior("LST-01")
async def test_lst_01_webrtc_mode(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """rest_settings(sim).live_stream_mode = 'webrtc' returns webrtc transport with signaling URL (LST-01)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001")
    cam.state.set_password("admin", "Admin-Pass-01")
    rest_settings(cam).live_stream_mode = "webrtc"

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-01",
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = NuraeyeClient(conn, http_client, fake_clock)

    res = await client.get_live_stream_uri(MAIN_PROFILE_TOKEN)
    assert isinstance(res, Success)
    assert res.value.transport == "webrtc"
    assert res.value.port == 8444
    assert res.value.path == "/webrtc"
    assert res.value.scheme == "http"
    assert res.value.url == f"http://{cam.host}:8444/webrtc"


@pytest.mark.behavior("LST-01")
def test_lst_01_golden_fixtures() -> None:
    """Golden fixtures for RTSP and WebRTC parse into valid LiveStreamUri objects."""
    rtsp_text = (FIXTURES_DIR / "live_stream_uri_rtsp.json").read_text(encoding="utf-8")
    rtsp_fixture = json.loads(rtsp_text)["data"]["output"]
    parsed_rtsp = parse_live_stream_uri(rtsp_fixture)
    assert isinstance(parsed_rtsp, LiveStreamUri)
    assert parsed_rtsp.transport == "rtsp"
    assert parsed_rtsp.port == 556
    assert parsed_rtsp.path == "/mobile"
    assert parsed_rtsp.scheme == "rtsps"

    webrtc_text = (FIXTURES_DIR / "live_stream_uri_webrtc.json").read_text(encoding="utf-8")
    webrtc_fixture = json.loads(webrtc_text)["data"]["output"]
    parsed_webrtc = parse_live_stream_uri(webrtc_fixture)
    assert isinstance(parsed_webrtc, LiveStreamUri)
    assert parsed_webrtc.transport == "webrtc"
    assert parsed_webrtc.port == 8444
    assert parsed_webrtc.path == "/webrtc"
    assert parsed_webrtc.scheme == "http"


@pytest.mark.behavior("LST-02")
def test_lst_02_invalid_responses() -> None:
    """Unknown transport, invalid url, or missing port yield Failure (LST-02)."""
    # 1. Unknown transport "hls"
    res1 = parse_live_stream_uri(
        {
            "transport": "hls",
            "port": 554,
            "url": "http://192.168.1.10:554/live.m3u8",
        }
    )
    assert isinstance(res1, Failure)
    assert res1.kind == FailureKind.BAD_RESPONSE
    assert "unknown transport" in res1.reason

    # 2. Unparseable URL "::not a url"
    res2 = parse_live_stream_uri(
        {
            "transport": "rtsp",
            "port": 554,
            "url": "::not a url",
        }
    )
    assert isinstance(res2, Failure)
    assert res2.kind == FailureKind.BAD_RESPONSE
    assert "Unparseable media url" in res2.reason

    # 3. Missing port
    res3 = parse_live_stream_uri(
        {
            "transport": "rtsp",
            "url": "rtsps://192.168.1.10:554/high",
        }
    )
    assert isinstance(res3, Failure)
    assert res3.kind == FailureKind.BAD_RESPONSE
    assert "missing transport/port/url" in res3.reason


@pytest.mark.behavior("LST-03")
async def test_lst_03_error_responses_no_fallback(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """400 (unknown token), 404, and 501 yield Failure with camera error text, no fallback calls (LST-03)."""
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

    # 1. HTTP 400 (Unknown profile token)
    res_400 = await client.get_live_stream_uri("Profile_99")
    assert isinstance(res_400, Failure)
    assert res_400.http_status == 400
    assert "Unknown profile token" in res_400.reason

    # 2. HTTP 501 (WebRTC streaming not supported)
    cam.faults.add(
        "POST /nuraeye/live-stream-uri",
        Status(
            code=501,
            json_body={
                "error_code": 501,
                "error_msg": "WebRTC streaming not supported in this build",
                "output": {},
            },
        ),
    )
    res_501 = await client.get_live_stream_uri(MAIN_PROFILE_TOKEN)
    assert isinstance(res_501, Failure)
    assert res_501.http_status == 501
    assert "WebRTC streaming not supported" in res_501.reason

    # 3. HTTP 404 (Endpoint not found - no fallback to legacy GetWebRtcUri)
    initial_request_count = len(cam.requests)
    cam.faults.add(
        "POST /nuraeye/live-stream-uri",
        Status(
            code=404,
            json_body={"error_code": 404, "error_msg": "Not found", "output": {}},
        ),
    )
    res_404 = await client.get_live_stream_uri(SUB_PROFILE_TOKEN)
    assert isinstance(res_404, Failure)
    assert res_404.http_status == 404
    assert "Not found" in res_404.reason

    # Verify client did not attempt any secondary fallback endpoint (e.g. legacy /webrtc-uri)
    new_requests = [r for r in cam.requests[initial_request_count:] if r.path != "/nuraeye/session/login"]
    assert len(new_requests) == 1
    assert new_requests[0].path == "/nuraeye/live-stream-uri"
