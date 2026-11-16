# mirrors: mobile_app/packages/camera_api/lib/src/device_reset_types.dart@093227387abe
# mirrors: mobile_app/packages/camera_api/lib/src/lan/onvif/onvif_device_client.dart@bd2e63476c9c
"""ONVIF Device service client and models for camera identity, scopes, and network configuration."""

import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

from pydantic import SecretStr

from vizenlink_nvr.camera.connection import DEVICE_SERVICE_PATH, CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.soap import find_text, parse_xml, post_soap, xml_escape
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

    async def get_network_interface_info(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[NetworkInterfaceInfo]:
        """Fetch network interface details via GetNetworkInterfaces (DEV-03)."""
        body = '<tds:GetNetworkInterfaces xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>'
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
            name = find_text(root, "Name")
            raw_mac = find_text(root, "HwAddress")
            address = find_text(root, "Address")
            return Success(
                NetworkInterfaceInfo(
                    name=name,
                    mac=normalize_mac(raw_mac),
                    address=address,
                )
            )
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetNetworkInterfaces response: {exc}",
            )

    async def get_device_identity(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[DeviceIdentity]:
        """Read camera display name and location via GetScopes (DEV-04)."""
        body = '<tds:GetScopes xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>'
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
            name = ""
            location = ""
            for el in root.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == "ScopeItem" and el.text:
                    raw = el.text.strip()
                    if raw.startswith(NAME_SCOPE_PREFIX):
                        name = unquote(raw[len(NAME_SCOPE_PREFIX) :])
                    elif raw.startswith(LOCATION_SCOPE_PREFIX):
                        location = unquote(raw[len(LOCATION_SCOPE_PREFIX) :])
            return Success(DeviceIdentity(name=name, location=location))
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetScopes response: {exc}",
            )

    async def set_device_name(
        self,
        name: str,
        timeout: float = 8.0,
    ) -> CameraResult[None]:
        """Set camera display name via SetScopes (DEV-05, D-13, CAM-08)."""
        if len(name) > MAX_DEVICE_NAME_LENGTH:
            return Failure(
                kind=FailureKind.GENERIC,
                reason=f"Device name exceeds maximum length of {MAX_DEVICE_NAME_LENGTH} characters",
            )

        quoted = quote(name, safe="!~*'()")
        scope_uri = f"{NAME_SCOPE_PREFIX}{quoted}"
        body = (
            '<tds:SetScopes xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
            f"<tds:Scopes>{scope_uri}</tds:Scopes>"
            "</tds:SetScopes>"
        )
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
        return Success(None)

    async def set_device_location(
        self,
        location: str,
        timeout: float = 8.0,
    ) -> CameraResult[None]:
        """Set camera physical location via SetScopes (DEV-05, D-13, CAM-08)."""
        if len(location) > MAX_DEVICE_NAME_LENGTH:
            return Failure(
                kind=FailureKind.GENERIC,
                reason=f"Device location exceeds maximum length of {MAX_DEVICE_NAME_LENGTH} characters",
            )

        quoted = quote(location, safe="!~*'()")
        scope_uri = f"{LOCATION_SCOPE_PREFIX}{quoted}"
        body = (
            '<tds:SetScopes xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
            f"<tds:Scopes>{scope_uri}</tds:Scopes>"
            "</tds:SetScopes>"
        )
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
        return Success(None)

    async def set_user_password(
        self,
        username: str,
        new_password: str | SecretStr,
        timeout: float = 8.0,
    ) -> CameraResult[None]:
        """Set account password via SetUser (DEV-06, D-04, CAM-04)."""
        pw = new_password.get_secret_value() if isinstance(new_password, SecretStr) else str(new_password)
        if len(pw) > MAX_DEVICE_PASSWORD_LENGTH:
            return Failure(
                kind=FailureKind.GENERIC,
                reason=f"Password exceeds maximum length of {MAX_DEVICE_PASSWORD_LENGTH} characters",
            )

        body = (
            '<tds:SetUser xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">'
            "<tds:User>"
            f"<tt:Username>{xml_escape(username)}</tt:Username>"
            f"<tt:Password>{xml_escape(pw)}</tt:Password>"
            "</tds:User>"
            "</tds:SetUser>"
        )
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
        return Success(None)

    async def get_services(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[list[ServiceEntry]]:
        """Query available ONVIF services via GetServices (DEV-07)."""
        body = (
            '<tds:GetServices xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
            "<tds:IncludeCapability>false</tds:IncludeCapability>"
            "</tds:GetServices>"
        )
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
            entries: list[ServiceEntry] = []
            for el in root.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == "Service":
                    namespace = find_text(el, "Namespace")
                    xaddr = find_text(el, "XAddr")
                    if namespace and xaddr:
                        entries.append(ServiceEntry(namespace=namespace, xaddr=xaddr))
            return Success(entries)
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse GetServices response: {exc}",
            )

    async def system_reboot(
        self,
        timeout: float = 8.0,
    ) -> CameraResult[str]:
        """Request device reboot via ONVIF SystemReboot (SET-05)."""
        body = '<tds:SystemReboot xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>'
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
            msg = find_text(root, "Message") or "Rebooting"
            return Success(msg)
        except Exception as exc:
            return Failure(
                kind=FailureKind.BAD_RESPONSE,
                reason=f"Failed to parse SystemReboot response: {exc}",
            )

    async def set_system_factory_default(
        self,
        mode: str = "Soft",
        timeout: float = 8.0,
    ) -> CameraResult[bool]:
        """Request factory reset via ONVIF SetSystemFactoryDefault (SET-06).

        mode: "Soft" (erases user configuration, retains network)
              "Hard" (erases all configuration including network, re-entering AP mode)
        """
        valid_mode = "Hard" if mode.lower() == "hard" else "Soft"
        body = (
            '<tds:SetSystemFactoryDefault xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
            f"<tds:FactoryDefault>{valid_mode}</tds:FactoryDefault>"
            "</tds:SetSystemFactoryDefault>"
        )
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
        return Success(True)

    async def get_system_timezone(self, timeout: float = 8.0) -> CameraResult[str]:
        result = await post_soap(
            self.http,
            self.conn,
            DEVICE_SERVICE_PATH,
            '<tds:GetSystemDateAndTime xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
            clock=self.clock,
            timeout=timeout,
        )
        if not isinstance(result, Success):
            return result
        timezone = find_text(parse_xml(result.value), "TZ")
        return (
            Success(timezone)
            if timezone
            else Failure(FailureKind.BAD_RESPONSE, "Camera did not report a time zone")
        )

    async def set_system_date_and_time(
        self,
        tz: str,
        timeout: float = 8.0,
    ) -> CameraResult[bool]:
        """Update camera system timezone via ONVIF SetSystemDateAndTime (SET-01)."""
        body = (
            '<tds:SetSystemDateAndTime xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
            "<tds:DateTimeType>NTP</tds:DateTimeType>"
            "<tds:DaylightSavings>true</tds:DaylightSavings>"
            "<tds:TimeZone>"
            f'<tt:TZ xmlns:tt="http://www.onvif.org/ver10/schema">{xml_escape(tz)}</tt:TZ>'
            "</tds:TimeZone>"
            "</tds:SetSystemDateAndTime>"
        )
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
        return Success(True)
