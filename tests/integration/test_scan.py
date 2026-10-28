"""Integration tests for camera discovery scan service (DSC-05)."""

import pytest
from fake_camera.discovery import DiscoveryResponder
from fake_camera.faults import Status
from fake_camera.server import FakeCamera

from vizenlink_nvr.camera.discovery.ws_discovery import DiscoveredDevice, WsDiscoveryClient
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.services.scan import ScanService, run_scan


@pytest.mark.behavior("DSC-05")
async def test_tracer_scan_two_simulated_cameras(
    discovery_responder: DiscoveryResponder,
    fake_camera: pytest.FixtureRequest,
) -> None:
    """Tracer test: scan finds two simulated cameras and names them with blank credentials (DSC-05)."""
    cam1: FakeCamera = await fake_camera(
        serial="VZL-CAM-SCAN01",
        name="Front Porch",
        model="VZL-Dome-4K",
    )
    cam2: FakeCamera = await fake_camera(
        serial="VZL-CAM-SCAN02",
        name="Back Yard",
        model="VZL-Bullet-2K",
    )

    settings = NvrSettings(
        discovery_multicast_group="127.0.0.1",
        discovery_port=discovery_responder.port,
    )

    report = await run_scan(settings)
    assert len(report.cameras) == 2
    hosts = {c.host for c in report.cameras}
    assert cam1.host in hosts
    assert cam2.host in hosts

    cam1_scanned = next(c for c in report.cameras if c.port == cam1.port)
    assert cam1_scanned.name == "Front Porch"
    assert cam1_scanned.model == "VZL-Dome-4K"

    cam2_scanned = next(c for c in report.cameras if c.port == cam2.port)
    assert cam2_scanned.name == "Back Yard"
    assert cam2_scanned.model == "VZL-Bullet-2K"

    # Verify no requests carried stored or factory credentials
    assert cam1.requests_with_credentials() == []
    assert cam2.requests_with_credentials() == []


@pytest.mark.behavior("DSC-05")
async def test_dsc_05_name_fallbacks(
    fake_camera: pytest.FixtureRequest,
) -> None:
    """DSC-05: Name fallback hierarchy: GetScopes -> Model -> 'Camera at <host>'."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-NAME01",
        name="Garden Cam",
        model="VZL-PTZ",
    )
    layer = CameraLayer.create()
    try:
        discovery = WsDiscoveryClient(
            port=cam.port,
            clock=layer.clock,
        )
        service = ScanService(layer, discovery)
        dev = DiscoveredDevice(
            host=cam.host,
            port=cam.port,
            scheme="https",
            xaddr=f"https://{cam.host}:{cam.port}/onvif/device_service",
            scopes=[],
        )

        # 1. Identity name present -> uses name
        cam.state.name = "Garden Cam"
        c1 = await service.identify(dev)
        assert c1 is not None
        assert c1.name == "Garden Cam"

        # 2. Empty name -> falls back to model
        cam.state.name = ""
        c2 = await service.identify(dev)
        assert c2 is not None
        assert c2.name == "VZL-PTZ"

        # 3. GetScopes failing (500) -> falls back to model
        cam.state.name = "Will Fail"
        cam.faults.add("POST /onvif/device_service", Status(500, json_body={"error": "fail"}))
        c3 = await service.identify(dev)
        assert c3 is not None
        assert c3.name == "VZL-PTZ"

        # 4. Both failing -> falls back to "Camera at <host>"
        cam.state.name = "Will Fail"
        cam.state.model = ""
        cam.faults.add("POST /onvif/device_service", Status(500, json_body={"error": "fail"}))
        cam.faults.add("POST /onvif/device_service", Status(500, json_body={"error": "fail"}))
        c4 = await service.identify(dev)
        assert c4 is not None
        assert c4.name == f"Camera at {cam.host}"
    finally:
        await layer.aclose()


@pytest.mark.behavior("DSC-05")
async def test_dsc_05_non_genuine_dropped(
    fake_camera: pytest.FixtureRequest,
) -> None:
    """DSC-05: Non-genuine candidate (genuine=False) is dropped with 1 request and no retry."""
    cam: FakeCamera = await fake_camera(
        serial="VZL-CAM-FAKE01",
        genuine=False,
    )
    layer = CameraLayer.create()
    try:
        discovery = WsDiscoveryClient(port=cam.port, clock=layer.clock)
        service = ScanService(layer, discovery)
        dev = DiscoveredDevice(
            host=cam.host,
            port=cam.port,
            scheme="https",
            xaddr=f"https://{cam.host}:{cam.port}/onvif/device_service",
            scopes=[],
        )

        res = await service.identify(dev)
        assert res is None
        # Assert exactly 1 request to /nuraeye/identity (no retry on non-genuine)
        identity_reqs = [r for r in cam.requests if r.path == "/nuraeye/identity"]
        assert len(identity_reqs) == 1
    finally:
        await layer.aclose()


@pytest.mark.behavior("DSC-05")
async def test_dsc_05_retry_on_failure(
    fake_camera: pytest.FixtureRequest,
) -> None:
    """DSC-05: One failure then success succeeds after exactly 2 requests; 2 failures drops candidate."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-RETRY01")
    layer = CameraLayer.create()
    try:
        discovery = WsDiscoveryClient(port=cam.port, clock=layer.clock)
        service = ScanService(layer, discovery)
        dev = DiscoveredDevice(
            host=cam.host,
            port=cam.port,
            scheme="https",
            xaddr=f"https://{cam.host}:{cam.port}/onvif/device_service",
            scopes=[],
        )

        # 1. First request fails with 500, retry succeeds
        cam.faults.add("POST /nuraeye/identity", Status(500, json_body={"error": "fail"}))
        res_ok = await service.identify(dev)
        assert res_ok is not None
        identity_reqs = [r for r in cam.requests if r.path == "/nuraeye/identity"]
        assert len(identity_reqs) == 2

        # 2. Both requests fail -> candidate dropped after exactly 2 requests
        cam.requests.clear()
        cam.faults.add("POST /nuraeye/identity", Status(500, json_body={"error": "fail"}))
        cam.faults.add("POST /nuraeye/identity", Status(500, json_body={"error": "fail"}))
        res_fail = await service.identify(dev)
        assert res_fail is None
        identity_reqs_fail = [r for r in cam.requests if r.path == "/nuraeye/identity"]
        assert len(identity_reqs_fail) == 2
    finally:
        await layer.aclose()


@pytest.mark.behavior("DSC-05")
async def test_scan_unicast_fallback_and_thorough(
    fake_camera: pytest.FixtureRequest,
) -> None:
    """Scan falls back to unicast when multicast finds nothing, and thorough runs both."""
    cam: FakeCamera = await fake_camera(serial="VZL-CAM-FALLBACK")
    layer = CameraLayer.create()
    try:
        dev = DiscoveredDevice(
            host=cam.host,
            port=cam.port,
            scheme="https",
            xaddr=f"https://{cam.host}:{cam.port}/onvif/device_service",
            scopes=[],
        )

        class FakeDiscovery:
            def __init__(self) -> None:
                self.multicast_called = 0
                self.unicast_called = 0
                self.multicast_results: list[DiscoveredDevice] = []

            async def scan_multicast(self) -> list[DiscoveredDevice]:
                self.multicast_called += 1
                return self.multicast_results

            async def scan_unicast(self) -> list[DiscoveredDevice]:
                self.unicast_called += 1
                return [dev]

        # Multicast empty -> triggers unicast
        disc = FakeDiscovery()
        service = ScanService(layer, disc)  # type: ignore[arg-type]
        rep1 = await service.scan(thorough=False)
        assert disc.multicast_called == 1
        assert disc.unicast_called == 1
        assert rep1.tiers_used == ["multicast", "unicast"]
        assert len(rep1.cameras) == 1

        # Multicast non-empty, thorough=False -> does NOT trigger unicast
        disc.multicast_called = 0
        disc.unicast_called = 0
        disc.multicast_results = [dev]
        rep2 = await service.scan(thorough=False)
        assert disc.multicast_called == 1
        assert disc.unicast_called == 0
        assert rep2.tiers_used == ["multicast"]

        # Multicast non-empty, thorough=True -> triggers unicast and merges
        disc.multicast_called = 0
        disc.unicast_called = 0
        rep3 = await service.scan(thorough=True)
        assert disc.multicast_called == 1
        assert disc.unicast_called == 1
        assert rep3.tiers_used == ["multicast", "unicast"]
        assert len(rep3.cameras) == 1  # merged by host
    finally:
        await layer.aclose()
