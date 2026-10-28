# mirrors: mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_device_client.dart@2e06d2ad3a40
"""ONVIF Device service client and models for camera identity, scopes, and network configuration."""

import re
from dataclasses import dataclass

from vizenlink_nvr.camera.connection import DEVICE_SERVICE_PATH, CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.soap import find_text, parse_xml, post_soap
from vizenlink_nvr.camera.result import CameraResult, Failure, FailureKind, Success, Timeout
from vizenlink_nvr.timeutil import Clock

NAME_SCOPE_PREFIX = "onvif://www.onvif.org/name/"
LOCATION_SCOPE_PREFIX = "onvif://www.onvif.org/location/"
MAC_SCOPE_PREFIX = "onvif://www.onvif.org/MAC/"
MAX_DEVICE_NAME_LENGTH = 32
MAX_DEVICE_PASSWORD_LENGTH = 32


def normalize_mac(text: str) -> str:
    """Normalize MAC address to uppercase colon-separated format (e.g. AA:BB:CC:DD:EE:FF)."""
    clean = re.sub(r"[^A-Fa-f0-9]", "", text).upper()
    if len(clean) != 12:
        return text.strip().upper()
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


@dataclass(frozen=True)
class DeviceInformation:
    """ONVIF device identification attributes."""

    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str


@dataclass(frozen=True)
class NetworkInterfaceInfo:
    """ONVIF network interface configuration."""

    name: str
    mac: str
    address: str


@dataclass(frozen=True)
class DeviceIdentity:
    """User-assigned device identity attributes."""

    name: str
    location: str


@dataclass(frozen=True)
class ServiceEntry:
    """ONVIF service descriptor."""

    namespace: str
    xaddr: str


class OnvifDeviceClient:
    """Client for ONVIF Device service (GetDeviceInformation, GetScopes, etc.)."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
    ) -> None:
        self.conn = conn
        self.http = http
        self.clock = clock

    async def get_device_information(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[DeviceInformation]:
        """Fetch device identification via GetDeviceInformation (DEV-01)."""
        body = '<tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>'
        res = await post_soap(
            self.http,
            self.conn,
            DEVICE_SERVICE_PATH,
            body,
            clock=self.clock,
            timeout=timeout,
        )
        if isinstance(res, (Failure, Timeout)):
            return res

        try:
            root = parse_xml(res.value)
            return Success(
                DeviceInformation(
                    manufacturer=find_text(root, "Manufacturer"),
                    model=find_text(root, "Model"),
                    firmware_version=find_text(root, "FirmwareVersion"),
                    serial_number=find_text(root, "SerialNumber"),
                    hardware_id=find_text(root, "HardwareId"),
                )
            )
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetDeviceInformation response: {exc}",
            )

    async def get_serial_number(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[str]:
        """Fetch camera serial number via GetDeviceInformation (DEV-02, D-06)."""
        res = await self.get_device_information(timeout=timeout)
        if isinstance(res, (Failure, Timeout)):
            return res
        return Success(res.value.serial_number.strip())
