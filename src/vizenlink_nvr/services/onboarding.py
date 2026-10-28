"""Camera onboarding orchestration service and outcome models."""

import asyncio
import ipaddress
import json
import logging
import socket
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, SecretStr

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import fetch_certificate_sha256
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.nuraeye.capabilities import Capabilities, parse_capabilities
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client
from vizenlink_nvr.camera.result import Failure, FailureKind, Success, Timeout
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.secrets.vault import Vault, open_vault
from vizenlink_nvr.services.registry import (
    CameraView,
    NewCameraRecord,
    get_camera,
    insert_camera,
    update_host,
)
from vizenlink_nvr.services.runtime import Runtime, open_runtime
from vizenlink_nvr.services.streams import resolve_streams

logger = logging.getLogger(__name__)

FACTORY_USERNAME = "admin"
FACTORY_PASSWORD = "password"  # noqa: S105


class AddOutcomeKind(StrEnum):
    """Categorized outcome for camera addition attempts."""

    OK = "OK"
    ADDRESS_UPDATED = "ADDRESS_UPDATED"
    ALREADY_REGISTERED = "ALREADY_REGISTERED"
    UNREACHABLE = "UNREACHABLE"
    WRONG_CREDENTIALS = "WRONG_CREDENTIALS"
    UNSUPPORTED_DEVICE = "UNSUPPORTED_DEVICE"
    NEEDS_NEW_PASSWORD = "NEEDS_NEW_PASSWORD"  # noqa: S105
    BLOCKED = "BLOCKED"
    NO_SERIAL = "NO_SERIAL"
    STREAMS_UNAVAILABLE = "STREAMS_UNAVAILABLE"
    FORBIDDEN = "FORBIDDEN"
    TLS_CHANGED = "TLS_CHANGED"
    INVALID_INPUT = "INVALID_INPUT"
    GENERIC_FAILURE = "GENERIC_FAILURE"


class AddRequest(BaseModel):
    """Parameters for onboarding a single camera."""

    host: str
    port: int = 443
    allow_public: bool = False


class AddOutcome(BaseModel):
    """Result of an onboarding attempt."""

    kind: AddOutcomeKind
    serial: str | None = None
    camera: CameraView | None = None
    retry_after_seconds: int | None = None
    detail: str | None = None


class PasswordProvider(Protocol):
    """Protocol for supplying camera credentials during onboarding."""

    async def current_password(self) -> SecretStr:
        """Return the current camera password."""
        ...

    async def new_password(self) -> SecretStr:
        """Return a newly chosen camera password."""
        ...


class FactoryProbe(StrEnum):
    """Result of factory credential probe."""

    FACTORY_PASSWORD = "FACTORY_PASSWORD"  # noqa: S105
    CONFIGURED = "CONFIGURED"
    BLOCKED = "BLOCKED"
    UNREACHABLE = "UNREACHABLE"


class VerifyKind(StrEnum):
    """Outcome of credential verification."""

    OK = "OK"
    WRONG_CREDENTIALS = "WRONG_CREDENTIALS"
    NEEDS_NEW_PASSWORD = "NEEDS_NEW_PASSWORD"  # noqa: S105
    BLOCKED = "BLOCKED"
    UNREACHABLE = "UNREACHABLE"
    FORBIDDEN = "FORBIDDEN"
    TLS_CHANGED = "TLS_CHANGED"
    UNSUPPORTED = "UNSUPPORTED"


class VerifyOutcome(BaseModel):
    """Verification result with optional capabilities or retry duration."""

    kind: VerifyKind
    capabilities: Any | None = None
    retry_after: int | None = None


def _is_safe_local_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP is loopback, private, or link-local (including ULA)."""
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _retry_sec(f: Failure) -> int | None:
    """Extract integer retry delay in seconds from failure outcome."""
    return int(f.retry_after.total_seconds()) if f.retry_after is not None else None


class OnboardingService:
    """Coordinate camera probing, credential verification, stream resolution, and registration."""

    def __init__(self, rt: Runtime, layer: CameraLayer, vault: Vault) -> None:
        self.rt = rt
        self.layer = layer
        self.vault = vault

    async def probe_factory(self, conn: CameraConnection) -> tuple[FactoryProbe, int | None]:
        """Perform exactly one login with factory credentials to determine configuration state."""
        if not conn.serial:
            raise ValueError("Connection must have a bound serial")

        self.layer.sessions.clear_session_for(conn.host)
        probe_conn = conn.with_credentials(FACTORY_USERNAME, FACTORY_PASSWORD)
        client = NuraeyeClient(probe_conn, self.layer.http, self.layer.clock, self.layer.sessions)
        res = await client.login(timeout=8.0)

        if isinstance(res, Success):
            return FactoryProbe.FACTORY_PASSWORD, None

        if isinstance(res, Failure):
            if res.kind == FailureKind.UNAUTHORIZED:
                return FactoryProbe.CONFIGURED, None
            if res.kind == FailureKind.BLOCKED:
                return FactoryProbe.BLOCKED, _retry_sec(res)

        return FactoryProbe.UNREACHABLE, None

    async def verify_credentials(self, conn: CameraConnection) -> VerifyOutcome:
        """Verify credentials by logging in and fetching authenticated capabilities."""
        if not conn.serial:
            raise ValueError("Connection must have a bound serial")

        self.layer.sessions.clear_session_for(conn.host)
        client = NuraeyeClient(conn, self.layer.http, self.layer.clock, self.layer.sessions)
        login_res = await client.login(timeout=8.0)

        if isinstance(login_res, Timeout):
            return VerifyOutcome(kind=VerifyKind.UNREACHABLE)

        if isinstance(login_res, Failure):
            if login_res.kind == FailureKind.UNAUTHORIZED:
                return VerifyOutcome(kind=VerifyKind.WRONG_CREDENTIALS)
            if login_res.kind == FailureKind.BLOCKED:
                return VerifyOutcome(kind=VerifyKind.BLOCKED, retry_after=_retry_sec(login_res))
            if login_res.kind == FailureKind.FORBIDDEN:
                return VerifyOutcome(kind=VerifyKind.FORBIDDEN)
            if login_res.kind == FailureKind.TLS_CHANGED:
                return VerifyOutcome(kind=VerifyKind.TLS_CHANGED)
            if login_res.kind == FailureKind.PASSWORD_CHANGE_REQUIRED:
                return VerifyOutcome(kind=VerifyKind.NEEDS_NEW_PASSWORD)
            return VerifyOutcome(kind=VerifyKind.UNREACHABLE)

        if login_res.value.password_change_required:
            return VerifyOutcome(kind=VerifyKind.NEEDS_NEW_PASSWORD)

        cap_res = await client.get_capabilities(timeout=8.0)
        if isinstance(cap_res, Timeout):
            return VerifyOutcome(kind=VerifyKind.UNREACHABLE)

        if isinstance(cap_res, Failure):
            if cap_res.kind == FailureKind.UNAUTHORIZED:
                return VerifyOutcome(kind=VerifyKind.WRONG_CREDENTIALS)
            if cap_res.kind == FailureKind.PASSWORD_CHANGE_REQUIRED:
                return VerifyOutcome(kind=VerifyKind.NEEDS_NEW_PASSWORD)
            if cap_res.kind == FailureKind.BLOCKED:
                return VerifyOutcome(kind=VerifyKind.BLOCKED, retry_after=_retry_sec(cap_res))
            if cap_res.kind == FailureKind.FORBIDDEN:
                return VerifyOutcome(kind=VerifyKind.FORBIDDEN)
            if cap_res.kind == FailureKind.TLS_CHANGED:
                return VerifyOutcome(kind=VerifyKind.TLS_CHANGED)
            return VerifyOutcome(kind=VerifyKind.UNREACHABLE)

        return VerifyOutcome(kind=VerifyKind.OK, capabilities=cap_res.value)

    async def add(self, req: AddRequest, passwords: PasswordProvider) -> AddOutcome:
        """Run complete camera onboarding sequence."""
        # 1. Host and port validation
        if req.port <= 0 or req.port > 65535:
            return AddOutcome(
                kind=AddOutcomeKind.INVALID_INPUT,
                detail=f"Invalid port: {req.port}",
            )

        try:
            ip = ipaddress.ip_address(req.host)
            if not req.allow_public and not _is_safe_local_ip(ip):
                return AddOutcome(
                    kind=AddOutcomeKind.INVALID_INPUT,
                    detail=f"Public IP address {req.host} not allowed without allow_public=True",
                )
        except ValueError:
            # Hostname: resolve and check IP safety
            try:
                addr_info = await asyncio.to_thread(
                    socket.getaddrinfo, req.host, req.port, type=socket.SOCK_STREAM
                )
                if not req.allow_public:
                    for ai in addr_info:
                        resolved_ip = ipaddress.ip_address(ai[4][0])
                        if not _is_safe_local_ip(resolved_ip):
                            return AddOutcome(
                                kind=AddOutcomeKind.INVALID_INPUT,
                                detail=f"Host {req.host} resolves to public IP {resolved_ip}",
                            )
            except Exception as exc:
                return AddOutcome(
                    kind=AddOutcomeKind.UNREACHABLE,
                    detail=f"Failed to resolve hostname {req.host}: {exc}",
                )

        # 2. Identity probe on blank connection
        blank_conn = CameraConnection.blank(req.host, req.port)
        nura_blank = NuraeyeClient(blank_conn, self.layer.http, self.layer.clock, self.layer.sessions)
        idn_res = await nura_blank.are_you_nuraeye_device_with_retry()

        if isinstance(idn_res, Timeout):
            return AddOutcome(kind=AddOutcomeKind.UNREACHABLE, detail="Identity probe timed out")
        if isinstance(idn_res, Failure):
            if idn_res.kind == FailureKind.UNREACHABLE:
                return AddOutcome(kind=AddOutcomeKind.UNREACHABLE, detail=idn_res.reason)
            return AddOutcome(kind=AddOutcomeKind.UNSUPPORTED_DEVICE, detail=idn_res.reason)
        if not idn_res.value:
            return AddOutcome(kind=AddOutcomeKind.UNSUPPORTED_DEVICE, detail="Device is not genuine NuraEye")

        # 3. Read serial using blank credentials immediately after identity
        onvif_blank = OnvifDeviceClient(blank_conn, self.layer.http, self.layer.clock)
        serial_res = await onvif_blank.get_serial_number()
        if not isinstance(serial_res, Success) or not serial_res.value or not serial_res.value.strip():
            return AddOutcome(kind=AddOutcomeKind.NO_SERIAL, detail="Camera did not report a serial number")
        serial = serial_res.value.strip()

        # 4. Fetch TLS certificate SHA-256 pin and bind conn.serial
        pin_res = await fetch_certificate_sha256(req.host, req.port, timeout=8.0)
        if isinstance(pin_res, (Failure, Timeout)):
            return AddOutcome(
                kind=AddOutcomeKind.UNREACHABLE,
                serial=serial,
                detail="Failed to retrieve camera TLS certificate",
            )
        pin = str(pin_res)
        bound_conn = CameraConnection(host=req.host, port=req.port, serial=serial, tls_pin_sha256=pin)

        # 5. Probe factory credentials
        factory_result, retry_after = await self.probe_factory(bound_conn)
        if factory_result == FactoryProbe.FACTORY_PASSWORD:
            return AddOutcome(kind=AddOutcomeKind.NEEDS_NEW_PASSWORD, serial=serial)
        if factory_result == FactoryProbe.BLOCKED:
            return AddOutcome(kind=AddOutcomeKind.BLOCKED, serial=serial, retry_after_seconds=retry_after)
        if factory_result == FactoryProbe.UNREACHABLE:
            return AddOutcome(kind=AddOutcomeKind.UNREACHABLE, serial=serial)

        # 6. Request current configured password
        current_pw = await passwords.current_password()
        authed_conn = bound_conn.with_credentials(FACTORY_USERNAME, current_pw)

        # 7. Authenticated verification via GetCapabilities
        verify_res = await self.verify_credentials(authed_conn)
        if verify_res.kind != VerifyKind.OK:
            mapping = {
                VerifyKind.WRONG_CREDENTIALS: AddOutcomeKind.WRONG_CREDENTIALS,
                VerifyKind.NEEDS_NEW_PASSWORD: AddOutcomeKind.NEEDS_NEW_PASSWORD,
                VerifyKind.BLOCKED: AddOutcomeKind.BLOCKED,
                VerifyKind.FORBIDDEN: AddOutcomeKind.FORBIDDEN,
                VerifyKind.TLS_CHANGED: AddOutcomeKind.TLS_CHANGED,
                VerifyKind.UNREACHABLE: AddOutcomeKind.UNREACHABLE,
                VerifyKind.UNSUPPORTED: AddOutcomeKind.UNSUPPORTED_DEVICE,
            }
            return AddOutcome(
                kind=mapping.get(verify_res.kind, AddOutcomeKind.GENERIC_FAILURE),
                serial=serial,
                retry_after_seconds=verify_res.retry_after,
            )

        # 8. Authenticated reads (serial re-verification, dev info, MAC, identity)
        onvif_authed = OnvifDeviceClient(authed_conn, self.layer.http, self.layer.clock)
        nura_authed = NuraeyeClient(authed_conn, self.layer.http, self.layer.clock, self.layer.sessions)
        media2_authed = OnvifMedia2Client(authed_conn, self.layer.http, self.layer.clock)

        reread_serial_res = await onvif_authed.get_serial_number()
        if not isinstance(reread_serial_res, Success) or reread_serial_res.value.strip() != serial:
            return AddOutcome(
                kind=AddOutcomeKind.UNSUPPORTED_DEVICE,
                serial=serial,
                detail="Serial mismatch on authenticated read",
            )

        dev_info_res = await onvif_authed.get_device_information()
        manufacturer = dev_info_res.value.manufacturer if isinstance(dev_info_res, Success) else ""
        model = dev_info_res.value.model if isinstance(dev_info_res, Success) else ""
        firmware_version = dev_info_res.value.firmware_version if isinstance(dev_info_res, Success) else ""
        hardware_id = dev_info_res.value.hardware_id if isinstance(dev_info_res, Success) else ""

        net_info_res = await onvif_authed.get_network_interface_info()
        mac = net_info_res.value.mac if isinstance(net_info_res, Success) else ""

        ident_res = await onvif_authed.get_device_identity()
        name = ident_res.value.name if isinstance(ident_res, Success) else ""
        location = ident_res.value.location if isinstance(ident_res, Success) else ""

        # 9. Duplicate check by serial
        now = self.layer.clock.now()
        async with self.rt.sessions() as session:
            existing = await get_camera(session, serial)
            if existing is not None:
                if existing.host == req.host and existing.https_port == req.port:
                    return AddOutcome(
                        kind=AddOutcomeKind.ALREADY_REGISTERED,
                        serial=serial,
                        camera=existing,
                    )
                await update_host(session, serial, req.host, req.port, at=now)
                await session.commit()
                updated_cam = await get_camera(session, serial)
                self.layer.sessions.clear_session_for(existing.host)
                return AddOutcome(
                    kind=AddOutcomeKind.ADDRESS_UPDATED,
                    serial=serial,
                    camera=updated_cam,
                )

        # 10. Stream resolution
        streams_res = await resolve_streams(nura_authed, media2_authed)
        if isinstance(streams_res, (Failure, Timeout)):
            return AddOutcome(
                kind=AddOutcomeKind.STREAMS_UNAVAILABLE,
                serial=serial,
                detail=getattr(streams_res, "reason", "Streams unavailable"),
            )
        streams = streams_res

        # 11. Seal password and atomic commit
        sealed = self.vault.seal(serial, FACTORY_USERNAME, current_pw)
        if isinstance(verify_res.capabilities, Capabilities):
            caps_dict = verify_res.capabilities.raw
            camera_id_check_val = verify_res.capabilities.camera_id_check
            if verify_res.capabilities.missing_required:
                logger.warning(
                    "Camera %s capabilities missing required fields: %s",
                    serial,
                    verify_res.capabilities.missing_required,
                )
        elif isinstance(verify_res.capabilities, dict):
            caps_dict = verify_res.capabilities
            parsed_caps = parse_capabilities(caps_dict, strict=False)
            camera_id_check_val = (
                parsed_caps.camera_id_check if isinstance(parsed_caps, Capabilities) else False
            )
            if isinstance(parsed_caps, Capabilities) and parsed_caps.missing_required:
                logger.warning(
                    "Camera %s capabilities missing required fields: %s",
                    serial,
                    parsed_caps.missing_required,
                )
        else:
            caps_dict = {}
            camera_id_check_val = False

        caps_raw = json.dumps(caps_dict)

        rec = NewCameraRecord(
            serial=serial,
            host=req.host,
            https_port=req.port,
            mac=mac,
            name=name,
            location=location,
            group_tag="",
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware_version,
            hardware_id=hardware_id,
            tls_fingerprint_sha256=pin,
            camera_id_check=camera_id_check_val,
            username=FACTORY_USERNAME,
            sealed_password=sealed,
            capabilities_raw=caps_raw,
            streams=streams,
            added_at=now,
        )

        async with self.rt.sessions() as session:
            async with session.begin():
                cam_view = await insert_camera(session, rec)

        return AddOutcome(
            kind=AddOutcomeKind.OK,
            serial=serial,
            camera=cam_view,
        )


async def run_add(
    settings: NvrSettings,
    req: AddRequest,
    passwords: PasswordProvider,
) -> AddOutcome:
    """Run camera onboarding within an initialized runtime and vault context."""
    async with open_runtime(settings) as rt:
        vault = await open_vault(rt)
        layer = CameraLayer.create(rt.clock)
        try:
            svc = OnboardingService(rt, layer, vault)
            return await svc.add(req, passwords)
        finally:
            await layer.aclose()
