"""Contract tests for NuraEye identity probe retry variant (IDN-03)."""

from collections.abc import AsyncGenerator

import pytest
from fake_camera.faults import Delay
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.result import Success, Timeout
from vizenlink_nvr.timeutil import Clock


@pytest.fixture
async def http_client() -> AsyncGenerator[CameraHttp, None]:
    """Yield CameraHttp instance and ensure clean teardown."""
    bus = CameraEventBus()
    http = CameraHttp(bus)
    try:
        yield http
    finally:
        await http.aclose()


@pytest.mark.behavior("IDN-03")
async def test_idn_03_retry_succeeds_on_third_attempt(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """First two attempts time out, third genuine -> Success(True) with exactly 2 sleeps (IDN-03)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001", genuine=True)

    # First two requests to /nuraeye/identity delayed by 10s (timeout is 0.05s for fast test execution)
    cam.faults.add("POST /nuraeye/identity", Delay(seconds=10.0), Delay(seconds=10.0))

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )

    slept_durations: list[float] = []

    async def mock_sleep(d: float) -> None:
        slept_durations.append(d)

    client = NuraeyeClient(conn, http_client, fake_clock, sleep=mock_sleep)

    res = await client.are_you_nuraeye_device_with_retry(
        attempts=3,
        attempt_timeout=0.05,
        retry_delay=1.0,
    )

    assert isinstance(res, Success)
    assert res.value is True

    # 3 total requests to sim
    assert len(cam.requests) == 3
    # Slept twice between the 3 attempts
    assert slept_durations == [1.0, 1.0]


@pytest.mark.behavior("IDN-03")
async def test_idn_03_all_attempts_fail_returns_last_result(
    fake_camera: pytest.FixtureRequest,
    http_client: CameraHttp,
    fake_clock: Clock,
) -> None:
    """When all three attempts time out, returns last Timeout result (IDN-03)."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-000001", genuine=True)

    # All requests delay beyond timeout
    cam.faults.add("POST /nuraeye/identity", Delay(seconds=10.0), Delay(seconds=10.0), Delay(seconds=10.0))

    conn = CameraConnection(
        host=cam.host,
        port=cam.port,
        serial="VZL-CAM-000001",
        tls_pin_sha256=cam.cert_sha256,
    )

    slept_durations: list[float] = []

    async def mock_sleep(d: float) -> None:
        slept_durations.append(d)

    client = NuraeyeClient(conn, http_client, fake_clock, sleep=mock_sleep)

    res = await client.are_you_nuraeye_device_with_retry(
        attempts=3,
        attempt_timeout=0.05,
        retry_delay=1.0,
    )

    assert isinstance(res, Timeout)
    assert len(cam.requests) == 3
    assert slept_durations == [1.0, 1.0]
