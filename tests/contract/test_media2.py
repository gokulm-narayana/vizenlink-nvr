"""Contract tests for ONVIF Media2 service (PRF-01, PRF-02, D-23 stream URI)."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fake_camera.routes.onvif_device import onvif_settings
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.media2 import MediaProfile, OnvifMedia2Client
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


@pytest.mark.behavior("PRF-01")
async def test_prf_01_get_profiles(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """PRF-01: Parse media profiles; skip invalid/incomplete; fail if no usable profiles."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000010")
    cam.state.set_password("admin", "Admin-Pass-10")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-10",
        serial="VZL-CAM-000010",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifMedia2Client(conn, http_client, fake_clock)

    # 1. Default profiles: 2 usable H265 profiles
    res = await client.get_profiles()
    assert isinstance(res, Success)
    assert len(res.value) == 2
    assert res.value[0] == MediaProfile(
        token="Profile_1",
        name="MainStream",
        venc_token="VideoEncoder_1",
        width=2560,
        height=1440,
        encoding="H265",
    )
    assert res.value[1] == MediaProfile(
        token="Profile_2",
        name="SubStream",
        venc_token="VideoEncoder_2",
        width=1280,
        height=720,
        encoding="H265",
    )

    # 2. Incomplete profiles skipped
    settings = onvif_settings(cam)
    settings.profiles = [
        {"token": "Incomplete_1", "name": "NoVenc"},  # lacks venc_token/width/height
        {
            "token": "Profile_Valid",
            "name": "ValidStream",
            "venc_token": "VideoEncoder_Valid",
            "width": 1920,
            "height": 1080,
            "encoding": "H264",
        },
    ]
    # Reset cached endpoint so we re-fetch if needed or re-use
    client_2 = OnvifMedia2Client(conn, http_client, fake_clock)
    res_partial = await client_2.get_profiles()
    assert isinstance(res_partial, Success)
    assert len(res_partial.value) == 1
    assert res_partial.value[0].token == "Profile_Valid"

    # 3. All incomplete -> Failure
    settings.profiles = [
        {"token": "Incomplete_1", "name": "NoVenc"},
    ]
    client_3 = OnvifMedia2Client(conn, http_client, fake_clock)
    res_empty = await client_3.get_profiles()
    assert isinstance(res_empty, Failure)
    assert "no usable Profiles" in res_empty.reason


@pytest.mark.behavior("PRF-02")
async def test_prf_02_resolve_media2_endpoint(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """PRF-02: Endpoint resolved from namespace; XAddr host ignored; missing Media2 fails."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000011")
    cam.state.set_password("admin", "Admin-Pass-11")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-11",
        serial="VZL-CAM-000011",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifMedia2Client(conn, http_client, fake_clock)

    # 1. Endpoint resolution uses path only (/onvif/media2_service), host 10.9.9.9 is ignored
    res_ep = await client.resolve_endpoint()
    assert isinstance(res_ep, Success)
    assert res_ep.value == "/onvif/media2_service"

    # 2. Disabled Media2 yields Failure("Media2 service not offered by this camera")
    settings = onvif_settings(cam)
    settings.media2_enabled = False

    client_disabled = OnvifMedia2Client(conn, http_client, fake_clock)
    res_disabled = await client_disabled.resolve_endpoint()
    assert isinstance(res_disabled, Failure)
    assert res_disabled.reason == "Media2 service not offered by this camera"


async def test_get_stream_uri(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """D-23 fallback: get_stream_uri returns RTSP stream URI for given profile."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000012")
    cam.state.set_password("admin", "Admin-Pass-12")

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        username="admin",
        password="Admin-Pass-12",
        serial="VZL-CAM-000012",
        tls_pin_sha256=cam.cert_sha256,
    )
    client = OnvifMedia2Client(conn, http_client, fake_clock)
    res = await client.get_stream_uri("Profile_1")
    assert isinstance(res, Success)
    assert res.value == f"rtsps://{cam.host}:554/high"
