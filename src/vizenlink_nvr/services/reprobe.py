"""Reprobe service coordinating camera serial re-verification and recovery."""

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.result import Failure, FailureKind, Timeout
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.services.recovery import AddressHealer, HealKind, HealOutcome, HealTrigger, make_healer
from vizenlink_nvr.services.registry import get_camera
from vizenlink_nvr.services.runtime import Runtime, open_runtime

logger = logging.getLogger(__name__)


class ReprobeKind(StrEnum):
    """Categorized outcome of a camera reprobe."""

    OK = "OK"
    HEALED = "HEALED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNREACHABLE = "UNREACHABLE"
    NOT_FOUND_SERIAL = "NOT_FOUND_SERIAL"


class ReprobeReport(BaseModel):
    """Result of reprobing a camera."""

    serial: str
    kind: ReprobeKind
    address: str | None = None
    heal: HealOutcome | None = None
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
) -> ReprobeReport:
    """Verify camera at stored address; initiate healing on 421, timeout, or mismatch."""
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

    # Check unauthenticated endpoint carrying bound serial header
    conn = CameraConnection.blank(camera.host, camera.https_port, serial=camera.serial)
    client = OnvifDeviceClient(conn, layer.http, layer.clock)
    serial_res = await client.get_serial_number(timeout=4.0)

    if isinstance(serial_res, Failure):
        if serial_res.kind == FailureKind.ID_MISMATCH:
            heal = await healer.heal(
                serial,
                HealTrigger.ID_MISMATCH,
                reported_host=camera.host,
                reported_port=camera.https_port,
                force=True,
            )
            return _report_from_heal(serial, heal, warnings)

        # UNREACHABLE or other communication error -> treat as unreachable
        heal = await healer.heal(
            serial,
            HealTrigger.UNREACHABLE,
            reported_host=camera.host,
            reported_port=camera.https_port,
            force=True,
        )
        return _report_from_heal(serial, heal, warnings)

    if isinstance(serial_res, Timeout):
        heal = await healer.heal(
            serial,
            HealTrigger.UNREACHABLE,
            reported_host=camera.host,
            reported_port=camera.https_port,
            force=True,
        )
        return _report_from_heal(serial, heal, warnings)

    # Success: verify returned serial
    returned_serial = serial_res.value.strip()
    if returned_serial == serial:
        return ReprobeReport(
            serial=serial,
            kind=ReprobeKind.OK,
            address=f"{camera.host}:{camera.https_port}",
            warnings=warnings,
        )

    # Serial mismatch detected by comparison (e.g. firmware without camera_id_check)
    heal = await healer.heal(
        serial,
        HealTrigger.ID_MISMATCH,
        reported_host=camera.host,
        reported_port=camera.https_port,
        force=True,
    )
    return _report_from_heal(serial, heal, warnings)


async def run_reprobe(settings: NvrSettings, serial: str) -> ReprobeReport:
    """Execute camera reprobe within initialized runtime, layer, and healer context."""
    async with open_runtime(settings) as rt:
        layer = CameraLayer.create(rt.clock)
        healer = make_healer(rt, layer, settings)
        try:
            return await reprobe_camera(rt, layer, healer, serial)
        finally:
            await healer.aclose()
            await layer.aclose()
