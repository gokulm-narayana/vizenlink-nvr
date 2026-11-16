"""Camera scan service coordinating discovery and unauthenticated identity probing."""

import asyncio
import logging

from pydantic import BaseModel

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.discovery.ws_discovery import DiscoveredDevice, WsDiscoveryClient
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.result import Failure, Success, Timeout
from vizenlink_nvr.config import NvrSettings

logger = logging.getLogger(__name__)


class ScannedCamera(BaseModel):
    """Camera discovered and verified on the local network."""

    host: str
    port: int
    model: str
    name: str
    mac: str = ""
    location: str = ""


class ScanReport(BaseModel):
    """Aggregate result of a scan operation."""

    cameras: list[ScannedCamera]
    tiers_used: list[str]


class ScanService:
    """Service scanning LAN for genuine VizenLink/NuraEye cameras."""

    def __init__(
        self,
        layer: CameraLayer,
        discovery: WsDiscoveryClient,
        *,
        probe_timeout: float = 3.0,
        concurrency: int = 16,
    ) -> None:
        self.layer = layer
        self.discovery = discovery
        self.probe_timeout = probe_timeout
        self.concurrency = concurrency

    async def identify(self, device: DiscoveredDevice) -> ScannedCamera | None:
        """Perform unauthenticated identity probing and metadata discovery on candidate."""
        conn = CameraConnection.blank(host=device.host, port=device.port)
        nuraeye = NuraeyeClient(
            conn,
            http=self.layer.http,
            clock=self.layer.clock,
            sessions=self.layer.sessions,
        )

        # 1. Identity probe with 1 retry on Failure/Timeout (not on Success(False))
        res = await nuraeye.are_you_nuraeye_device(timeout=self.probe_timeout)
        if isinstance(res, (Failure, Timeout)):
            # Retry exactly once
            res = await nuraeye.are_you_nuraeye_device(timeout=self.probe_timeout)

        if not isinstance(res, Success) or not res.value:
            return None

        # 2. Blank metadata query: identity scopes, device information, and network info
        onvif_dev = OnvifDeviceClient(
            conn,
            http=self.layer.http,
            clock=self.layer.clock,
        )

        name = device.name_hint or ""
        location = device.location_hint or ""
        model = ""
        mac = device.mac_hint or ""

        id_res = await onvif_dev.get_device_identity(timeout=self.probe_timeout)
        if isinstance(id_res, Success):
            if id_res.value.name:
                name = id_res.value.name
            if id_res.value.location:
                location = id_res.value.location

        info_res = await onvif_dev.get_device_information(timeout=self.probe_timeout)
        if isinstance(info_res, Success):
            if info_res.value.model:
                model = info_res.value.model

        if not mac:
            net_res = await onvif_dev.get_network_interface_info(timeout=self.probe_timeout)
            if isinstance(net_res, Success) and net_res.value.mac:
                mac = net_res.value.mac

        # 3. Name fallbacks (D-01, DSC-05)
        if not name:
            name = model if model else f"Camera at {device.host}"
        if not model:
            model = "VizenLink Camera"

        return ScannedCamera(
            host=device.host,
            port=device.port,
            model=model,
            name=name,
            mac=mac,
            location=location,
        )

    async def scan(self, thorough: bool = False) -> ScanReport:
        """Run WS-Discovery passes and identify cameras."""
        sem = asyncio.Semaphore(self.concurrency)

        async def _identify_with_sem(dev: DiscoveredDevice) -> ScannedCamera | None:
            async with sem:
                return await self.identify(dev)

        async def identify_candidates(candidates: list[DiscoveredDevice]) -> list[ScannedCamera | None]:
            return await asyncio.gather(*(_identify_with_sem(device) for device in candidates))

        tiers_used = ["multicast"]
        try:
            multicast = await self.discovery.scan_multicast()
        except PermissionError:
            # Some networks permit direct probes even when multicast is blocked.
            multicast = []
        results = await identify_candidates(multicast)

        if thorough or not any(results):
            tiers_used.append("unicast")
            try:
                unicast = await self.discovery.scan_unicast()
            except PermissionError:
                if not any(results):
                    raise
                unicast = []
            verified = {(camera.host, camera.port) for camera in results if camera is not None}
            results.extend(await identify_candidates([
                device for device in unicast if (device.host, device.port) not in verified
            ]))

        cameras = [c for c in results if c is not None]
        cameras.sort(key=lambda c: (c.host, c.port))

        return ScanReport(cameras=cameras, tiers_used=tiers_used)


async def run_scan(
    settings: NvrSettings,
    *,
    thorough: bool = False,
    timeout: float | None = None,
) -> ScanReport:
    """Entry point creating CameraLayer and ScanService to execute scan."""
    layer = CameraLayer.create()
    try:
        discovery = WsDiscoveryClient(
            port=settings.discovery_port,
            multicast_group=settings.discovery_multicast_group,
            unicast_hosts=settings.discovery_unicast_hosts,
            clock=layer.clock,
        )
        service = ScanService(
            layer,
            discovery,
            probe_timeout=timeout if timeout is not None else 3.0,
        )
        return await service.scan(thorough=thorough)
    finally:
        await layer.aclose()
