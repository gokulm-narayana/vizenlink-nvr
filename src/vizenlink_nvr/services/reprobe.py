"""Reprobe service coordinating camera serial re-verification, recovery, and refresh."""

import json
import logging
from dataclasses import replace
from enum import StrEnum

from pydantic import BaseModel, Field

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import fetch_certificate_sha256
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client
from vizenlink_nvr.camera.result import Failure, FailureKind, Success, Timeout
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.secrets.vault import open_vault
from vizenlink_nvr.services.recovery import (
    AddressHealer,
    HealKind,
    HealOutcome,
    HealTrigger,
    make_healer,
)
from vizenlink_nvr.services.registry import (
    CameraView,
    get_camera,
    load_connection,
    replace_capabilities_and_streams,
    set_state,
    set_tls_fingerprint,
    update_identity,
)
from vizenlink_nvr.services.runtime import Runtime, open_runtime
from vizenlink_nvr.services.streams import resolve_streams

logger = logging.getLogger(__name__)


class ReprobeKind(StrEnum):
    """Categorized outcome of a camera reprobe."""

    OK = "OK"
    HEALED = "HEALED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNREACHABLE = "UNREACHABLE"
    NOT_FOUND_SERIAL = "NOT_FOUND_SERIAL"
    AUTH_FAILED = "AUTH_FAILED"
    TLS_CHANGED = "TLS_CHANGED"
    FORBIDDEN = "FORBIDDEN"


class ReprobeReport(BaseModel):
    """Result of reprobing a camera."""

    serial: str
    kind: ReprobeKind
    address: str | None = None
    heal: HealOutcome | None = None
    refreshed: bool = False
    camera: CameraView | None = None
    warnings: list[str] = Field(default_factory=list)


def _report_from_heal(serial: str, heal: HealOutcome, warnings: list[str]) -> ReprobeReport:
    """Map HealOutcome to ReprobeReport."""
    if heal.kind == HealKind.HEALED:
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.HEALED,
            address=heal.new_address,
            heal=heal,
            warnings=warnings,
        )
    if heal.kind == HealKind.AMBIGUOUS:
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.AMBIGUOUS,
            address=heal.old_address,
            heal=heal,
            warnings=warnings,
        )
    if heal.kind == HealKind.VERIFIED_IN_PLACE:
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.OK,
            address=heal.old_address,
            heal=heal,
            warnings=warnings,
        )
    if heal.kind == HealKind.NOT_FOUND:
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.NOT_FOUND,
            address=heal.old_address,
            heal=heal,
            warnings=warnings,
        )
    return ReprobeReport(
        serial=serial,
        kind=ReprobeKind.UNREACHABLE,
        address=heal.old_address,
        heal=heal,
        warnings=warnings,
    )


async def reprobe_camera(
    rt: Runtime,
    layer: CameraLayer,
    healer: AddressHealer,
    serial: str,
    *,
    accept_new_certificate: bool = False,
) -> ReprobeReport:
    """Verify camera at stored address, heal if moved, and refresh capabilities and streams."""
    async with rt.sessions() as session:
        camera = await get_camera(session, serial)

    if camera is None:
        return ReprobeReport(serial=serial, kind=ReprobeKind.NOT_FOUND_SERIAL)

    warnings: list[str] = []
    dhcp_warning = (
        "This camera's firmware does not check camera IDs; set a DHCP reservation for it on your router."
    )
    if not camera.camera_id_check:
        warnings.append(dhcp_warning)

    new_pin: str | None = None
    heal_outcome: HealOutcome | None = None

    if accept_new_certificate:
        # Check unauthenticated serial-header first without pinning
        conn_blank = CameraConnection.blank(camera.host, camera.https_port, serial=camera.serial)
        client_blank = OnvifDeviceClient(conn_blank, layer.http, layer.clock)
        serial_res = await client_blank.get_serial_number(timeout=4.0)

        if isinstance(serial_res, Failure) and serial_res.kind == FailureKind.ID_MISMATCH:
            return ReprobeReport(
                serial=serial,
                kind=ReprobeKind.AMBIGUOUS,
                address=f"{camera.host}:{camera.https_port}",
                warnings=warnings,
            )

        if not isinstance(serial_res, Success) or serial_res.value.strip() != serial:
            return ReprobeReport(
                serial=serial,
                kind=ReprobeKind.UNREACHABLE,
                address=f"{camera.host}:{camera.https_port}",
                warnings=warnings,
            )

        # Fetch new certificate pin
        pin_res = await fetch_certificate_sha256(camera.host, camera.https_port, timeout=8.0)
        if not isinstance(pin_res, str):
            return ReprobeReport(
                serial=serial,
                kind=ReprobeKind.UNREACHABLE,
                address=f"{camera.host}:{camera.https_port}",
                warnings=warnings,
            )
        new_pin = pin_res

    else:
        # Standard unauthenticated serial check and healing
        conn = CameraConnection.blank(camera.host, camera.https_port, serial=camera.serial)
        client = OnvifDeviceClient(conn, layer.http, layer.clock)
        serial_res = await client.get_serial_number(timeout=4.0)

        if isinstance(serial_res, Failure):
            if serial_res.kind == FailureKind.ID_MISMATCH:
                heal_outcome = await healer.heal(
                    serial,
                    HealTrigger.ID_MISMATCH,
                    reported_host=camera.host,
                    reported_port=camera.https_port,
                    force=True,
                )
            else:
                heal_outcome = await healer.heal(
                    serial,
                    HealTrigger.UNREACHABLE,
                    reported_host=camera.host,
                    reported_port=camera.https_port,
                    force=True,
                )
        elif isinstance(serial_res, Timeout):
            heal_outcome = await healer.heal(
                serial,
                HealTrigger.UNREACHABLE,
                reported_host=camera.host,
                reported_port=camera.https_port,
                force=True,
            )
        else:
            returned_serial = serial_res.value.strip()
            if returned_serial != serial:
                heal_outcome = await healer.heal(
                    serial,
                    HealTrigger.ID_MISMATCH,
                    reported_host=camera.host,
                    reported_port=camera.https_port,
                    force=True,
                )

        if heal_outcome is not None:
            if heal_outcome.kind not in (HealKind.HEALED, HealKind.VERIFIED_IN_PLACE):
                return _report_from_heal(serial, heal_outcome, warnings)
            # Address updated: reload camera record from registry
            async with rt.sessions() as session:
                refreshed_cam = await get_camera(session, serial)
                if refreshed_cam is not None:
                    camera = refreshed_cam

    # Refuse authenticated work when in auth_failed state
    if camera.state == "auth_failed":
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.AUTH_FAILED,
            address=f"{camera.host}:{camera.https_port}",
            heal=heal_outcome,
            warnings=warnings,
        )

    # Refuse authenticated work when certificate changed and not explicitly accepted
    if camera.state == "tls_changed" and not accept_new_certificate:
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.TLS_CHANGED,
            address=f"{camera.host}:{camera.https_port}",
            heal=heal_outcome,
            warnings=warnings,
        )

    # Load stored credentials and construct authenticated clients
    vault = await open_vault(rt)
    async with rt.sessions() as session:
        conn_authed = await load_connection(session, vault, serial)

    if accept_new_certificate and new_pin is not None:
        conn_authed = replace(conn_authed, tls_pin_sha256=new_pin)

    onvif_authed = OnvifDeviceClient(conn_authed, layer.http, layer.clock)
    nura_authed = NuraeyeClient(conn_authed, layer.http, layer.clock, layer.sessions)
    media2_authed = OnvifMedia2Client(conn_authed, layer.http, layer.clock)

    # Re-read capabilities
    caps_res = await nura_authed.get_capabilities()
    if isinstance(caps_res, Failure):
        if caps_res.kind == FailureKind.TLS_CHANGED:
            async with rt.sessions() as session:
                async with session.begin():
                    await set_state(session, serial, "tls_changed", caps_res.reason)
            return ReprobeReport(
                serial=serial,
                kind=ReprobeKind.TLS_CHANGED,
                address=f"{camera.host}:{camera.https_port}",
                heal=heal_outcome,
                warnings=warnings,
            )
        if caps_res.kind == FailureKind.UNAUTHORIZED:
            async with rt.sessions() as session:
                async with session.begin():
                    await set_state(session, serial, "auth_failed", caps_res.reason)
            return ReprobeReport(
                serial=serial,
                kind=ReprobeKind.AUTH_FAILED,
                address=f"{camera.host}:{camera.https_port}",
                heal=heal_outcome,
                warnings=warnings,
            )
        if caps_res.kind == FailureKind.FORBIDDEN:
            return ReprobeReport(
                serial=serial,
                kind=ReprobeKind.FORBIDDEN,
                address=f"{camera.host}:{camera.https_port}",
                heal=heal_outcome,
                warnings=warnings,
            )
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.UNREACHABLE,
            address=f"{camera.host}:{camera.https_port}",
            heal=heal_outcome,
            warnings=warnings,
        )
    if isinstance(caps_res, Timeout):
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.UNREACHABLE,
            address=f"{camera.host}:{camera.https_port}",
            heal=heal_outcome,
            warnings=warnings,
        )

    # Re-read video streams
    streams_res = await resolve_streams(nura_authed, media2_authed)
    if isinstance(streams_res, (Failure, Timeout)):
        if isinstance(streams_res, Failure):
            if streams_res.kind == FailureKind.TLS_CHANGED:
                async with rt.sessions() as session:
                    async with session.begin():
                        await set_state(session, serial, "tls_changed", streams_res.reason)
                return ReprobeReport(
                    serial=serial,
                    kind=ReprobeKind.TLS_CHANGED,
                    address=f"{camera.host}:{camera.https_port}",
                    heal=heal_outcome,
                    warnings=warnings,
                )
            if streams_res.kind == FailureKind.UNAUTHORIZED:
                async with rt.sessions() as session:
                    async with session.begin():
                        await set_state(session, serial, "auth_failed", streams_res.reason)
                return ReprobeReport(
                    serial=serial,
                    kind=ReprobeKind.AUTH_FAILED,
                    address=f"{camera.host}:{camera.https_port}",
                    heal=heal_outcome,
                    warnings=warnings,
                )
            if streams_res.kind == FailureKind.FORBIDDEN:
                return ReprobeReport(
                    serial=serial,
                    kind=ReprobeKind.FORBIDDEN,
                    address=f"{camera.host}:{camera.https_port}",
                    heal=heal_outcome,
                    warnings=warnings,
                )
        # Stream failure: keep existing capabilities and stream records untouched
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.UNREACHABLE,
            address=f"{camera.host}:{camera.https_port}",
            heal=heal_outcome,
            refreshed=False,
            warnings=warnings,
        )

    # Re-read identity and device information
    ident_res = await onvif_authed.get_device_identity()
    dev_info_res = await onvif_authed.get_device_information()

    firmware = (
        dev_info_res.value.firmware_version if isinstance(dev_info_res, Success) else camera.firmware_version
    )
    name = ident_res.value.name if isinstance(ident_res, Success) else camera.name
    location = ident_res.value.location if isinstance(ident_res, Success) else camera.location

    # Single atomic transaction replacing capabilities, streams, and identity
    now = rt.clock.now()
    caps_data = caps_res.value.raw if hasattr(caps_res.value, "raw") else caps_res.value
    async with rt.sessions() as session:
        async with session.begin():
            if accept_new_certificate and new_pin is not None:
                await set_tls_fingerprint(session, serial, new_pin, now)
                await set_state(session, serial, "active", None)
            await replace_capabilities_and_streams(
                session,
                serial,
                capabilities_raw=json.dumps(caps_data),
                firmware_version=firmware,
                streams=streams_res,
                at=now,
            )
            updated_cam = await update_identity(
                session,
                serial,
                name=name,
                location=location,
                at=now,
            )

    report_kind = (
        ReprobeKind.HEALED if (heal_outcome and heal_outcome.kind == HealKind.HEALED) else ReprobeKind.OK
    )
    return ReprobeReport(
        serial=serial,
        kind=report_kind,
        address=f"{camera.host}:{camera.https_port}",
        heal=heal_outcome,
        refreshed=True,
        camera=updated_cam,
        warnings=warnings,
    )


async def run_reprobe(
    settings: NvrSettings,
    serial: str,
    *,
    accept_new_certificate: bool = False,
) -> ReprobeReport:
    """Execute camera reprobe within initialized runtime, layer, and healer context."""
    async with open_runtime(settings) as rt:
        layer = CameraLayer.create(rt.clock)
        healer = make_healer(rt, layer, settings)
        try:
            return await reprobe_camera(
                rt,
                layer,
                healer,
                serial,
                accept_new_certificate=accept_new_certificate,
            )
        finally:
            await healer.aclose()
            await layer.aclose()
