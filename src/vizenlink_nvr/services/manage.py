"""Camera management operations: renaming, location, group, and credential recovery."""

import logging
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import select

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.camera.onvif.device import MAX_DEVICE_NAME_LENGTH, OnvifDeviceClient
from vizenlink_nvr.camera.result import Failure, FailureKind, Success, Timeout
from vizenlink_nvr.config import NvrSettings
from vizenlink_nvr.db.models import CameraCredential
from vizenlink_nvr.secrets.vault import Vault, open_vault
from vizenlink_nvr.services.onboarding import OnboardingService, PasswordProvider, VerifyKind
from vizenlink_nvr.services.registry import (
    MAX_GROUP_LENGTH,
    CameraView,
    get_camera,
    load_connection,
    replace_credential,
    set_state,
    update_identity,
)
from vizenlink_nvr.services.runtime import Runtime, open_runtime

logger = logging.getLogger(__name__)


class ManageKind(StrEnum):
    """Categorized outcome of a camera management operation."""

    OK = "OK"
    AUTH_FAILED = "AUTH_FAILED"
    WRONG_CREDENTIALS = "WRONG_CREDENTIALS"
    BLOCKED = "BLOCKED"
    UNREACHABLE = "UNREACHABLE"
    FORBIDDEN = "FORBIDDEN"
    TLS_CHANGED = "TLS_CHANGED"
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    GENERIC_FAILURE = "GENERIC_FAILURE"


class RenameRequest(BaseModel):
    """Parameters for updating camera name, location, and group."""

    serial: str
    name: str | None = None
    location: str | None = None
    group: str | None = None


class ManageOutcome(BaseModel):
    """Result of a camera management operation."""

    kind: ManageKind
    camera: CameraView | None = None
    detail: str | None = None
    retry_after_seconds: int | None = None


async def _handle_camera_failure(
    rt: Runtime,
    serial: str,
    res: Failure | Timeout,
    current_cam: CameraView,
) -> ManageOutcome:
    """Map camera call failure/timeout to ManageOutcome and update DB state if needed."""
    if isinstance(res, Timeout):
        return ManageOutcome(
            kind=ManageKind.UNREACHABLE,
            camera=current_cam,
            detail="Connection timed out.",
        )

    if res.kind == FailureKind.TLS_CHANGED:
        async with rt.sessions() as session:
            async with session.begin():
                await set_state(session, serial, "tls_changed", res.reason)
        updated = current_cam.model_copy(update={"state": "tls_changed", "last_error": res.reason})
        return ManageOutcome(
            kind=ManageKind.TLS_CHANGED,
            camera=updated,
            detail=(
                "The camera's certificate has changed since it was added. "
                "If you replaced or updated this camera, run: "
                f"nvr cameras reprobe {serial} --accept-new-certificate"
            ),
        )

    if res.kind == FailureKind.UNAUTHORIZED:
        async with rt.sessions() as session:
            async with session.begin():
                await set_state(session, serial, "auth_failed", res.reason)
        updated = current_cam.model_copy(update={"state": "auth_failed", "last_error": res.reason})
        return ManageOutcome(
            kind=ManageKind.AUTH_FAILED,
            camera=updated,
            detail="Camera authentication failed; password must be updated.",
        )

    if res.kind == FailureKind.FORBIDDEN:
        # Note: D-10: FORBIDDEN leaves state unchanged!
        return ManageOutcome(
            kind=ManageKind.FORBIDDEN,
            camera=current_cam,
            detail=res.reason,
        )

    if res.kind == FailureKind.BLOCKED:
        retry_secs = int(res.retry_after.total_seconds()) if res.retry_after is not None else None
        return ManageOutcome(
            kind=ManageKind.BLOCKED,
            camera=current_cam,
            detail=res.reason,
            retry_after_seconds=retry_secs,
        )

    if res.kind == FailureKind.UNREACHABLE:
        return ManageOutcome(
            kind=ManageKind.UNREACHABLE,
            camera=current_cam,
            detail=res.reason,
        )

    return ManageOutcome(
        kind=ManageKind.GENERIC_FAILURE,
        camera=current_cam,
        detail=res.reason,
    )


async def rename_camera(
    rt: Runtime,
    layer: CameraLayer,
    vault: Vault,
    req: RenameRequest,
) -> ManageOutcome:
    """Rename camera display name and location on the camera, and group in the NVR (CAM-08, D-13)."""
    # 1. Input validation
    if req.name is None and req.location is None and req.group is None:
        return ManageOutcome(
            kind=ManageKind.INVALID_INPUT,
            detail="At least one of name, location, or group must be specified.",
        )

    if req.name is not None and len(req.name) > MAX_DEVICE_NAME_LENGTH:
        return ManageOutcome(
            kind=ManageKind.INVALID_INPUT,
            detail=f"Name exceeds {MAX_DEVICE_NAME_LENGTH} characters.",
        )

    if req.location is not None and len(req.location) > MAX_DEVICE_NAME_LENGTH:
        return ManageOutcome(
            kind=ManageKind.INVALID_INPUT,
            detail=f"Location exceeds {MAX_DEVICE_NAME_LENGTH} characters.",
        )

    if req.group is not None and len(req.group) > MAX_GROUP_LENGTH:
        return ManageOutcome(
            kind=ManageKind.INVALID_INPUT,
            detail=f"Group exceeds {MAX_GROUP_LENGTH} characters.",
        )

    # 2. Load stored camera
    async with rt.sessions() as session:
        cam = await get_camera(session, req.serial)

    if cam is None:
        return ManageOutcome(
            kind=ManageKind.NOT_FOUND,
            detail=f"Camera {req.serial} not found in registry.",
        )

    # 3. Check if camera hardware interaction is required
    new_name: str | None = None
    new_location: str | None = None

    if req.name is not None or req.location is not None:
        if cam.state == "auth_failed":
            return ManageOutcome(
                kind=ManageKind.AUTH_FAILED,
                camera=cam,
                detail="Camera authentication failed; password must be updated.",
            )

        if cam.state == "tls_changed":
            return ManageOutcome(
                kind=ManageKind.TLS_CHANGED,
                camera=cam,
                detail=(
                    "The camera's certificate has changed since it was added. "
                    "If you replaced or updated this camera, run: "
                    f"nvr cameras reprobe {req.serial} --accept-new-certificate"
                ),
            )

        async with rt.sessions() as session:
            conn = await load_connection(session, vault, req.serial)

        client = OnvifDeviceClient(conn, layer.http, layer.clock)

        if req.name is not None:
            name_res = await client.set_device_name(req.name)
            if isinstance(name_res, (Failure, Timeout)):
                return await _handle_camera_failure(rt, req.serial, name_res, cam)

        if req.location is not None:
            loc_res = await client.set_device_location(req.location)
            if isinstance(loc_res, (Failure, Timeout)):
                return await _handle_camera_failure(rt, req.serial, loc_res, cam)

        # Read back identity to ensure NVR cached state reflects what camera actually accepted
        ident_res = await client.get_device_identity()
        if isinstance(ident_res, Success):
            new_name = ident_res.value.name
            new_location = ident_res.value.location
        else:
            new_name = req.name if req.name is not None else cam.name
            new_location = req.location if req.location is not None else cam.location

    # 4. Update NVR database
    now = rt.clock.now()
    async with rt.sessions() as session:
        async with session.begin():
            updated_view = await update_identity(
                session,
                req.serial,
                name=new_name,
                location=new_location,
                group=req.group,
                at=now,
            )

    return ManageOutcome(kind=ManageKind.OK, camera=updated_view)


async def set_camera_password(
    rt: Runtime,
    layer: CameraLayer,
    vault: Vault,
    serial: str,
    passwords: PasswordProvider,
) -> ManageOutcome:
    """Update camera password after authentication failure or credential rotation (D-05, D-09, D-14)."""
    async with rt.sessions() as session:
        cam = await get_camera(session, serial)

    if cam is None:
        return ManageOutcome(
            kind=ManageKind.NOT_FOUND,
            detail=f"Camera {serial} not found in registry.",
        )

    # Prompt user for new password
    new_pw = await passwords.current_password()

    # Query stored username for camera
    async with rt.sessions() as session:
        cred_stmt = select(CameraCredential.username).where(CameraCredential.serial == serial)
        username = (await session.execute(cred_stmt)).scalar_one()

    conn = CameraConnection(
        host=cam.host,
        port=cam.https_port,
        username=username,
        password=new_pw,
        serial=cam.serial,
        tls_pin_sha256=cam.tls_fingerprint_sha256,
    )

    onboarding = OnboardingService(rt, layer, vault)
    verify_res = await onboarding.verify_credentials(conn)

    if verify_res.kind == VerifyKind.WRONG_CREDENTIALS:
        return ManageOutcome(
            kind=ManageKind.WRONG_CREDENTIALS,
            camera=cam,
            detail="Incorrect username or password.",
        )

    if verify_res.kind == VerifyKind.BLOCKED:
        return ManageOutcome(
            kind=ManageKind.BLOCKED,
            camera=cam,
            detail=verify_res.detail,
            retry_after_seconds=verify_res.retry_after,
        )

    if verify_res.kind == VerifyKind.FORBIDDEN:
        return ManageOutcome(
            kind=ManageKind.FORBIDDEN,
            camera=cam,
            detail="Access forbidden by camera.",
        )

    if verify_res.kind == VerifyKind.TLS_CHANGED:
        return ManageOutcome(
            kind=ManageKind.TLS_CHANGED,
            camera=cam,
            detail=(
                "The camera's certificate has changed since it was added. "
                "If you replaced or updated this camera, run: "
                f"nvr cameras reprobe {serial} --accept-new-certificate"
            ),
        )

    if verify_res.kind != VerifyKind.OK:
        return ManageOutcome(
            kind=ManageKind.UNREACHABLE,
            camera=cam,
            detail=verify_res.detail or "Could not reach the camera — check the connection and try again.",
        )

    # OK: seal password and update credential + active state in one transaction
    now = rt.clock.now()
    sealed = vault.seal(serial, username, new_pw)

    async with rt.sessions() as session:
        async with session.begin():
            await replace_credential(session, serial, username, sealed, now)
            await set_state(session, serial, "active", None)

    async with rt.sessions() as session:
        updated_cam = await get_camera(session, serial)

    return ManageOutcome(kind=ManageKind.OK, camera=updated_cam)


async def run_rename(settings: NvrSettings, req: RenameRequest) -> ManageOutcome:
    """Execute camera rename within initialized runtime and layer context."""
    async with open_runtime(settings) as rt:
        layer = CameraLayer.create(rt.clock)
        vault = await open_vault(rt)
        try:
            return await rename_camera(rt, layer, vault, req)
        finally:
            await layer.aclose()


async def run_set_password(
    settings: NvrSettings,
    serial: str,
    passwords: PasswordProvider,
) -> ManageOutcome:
    """Execute camera password update within initialized runtime and layer context."""
    async with open_runtime(settings) as rt:
        layer = CameraLayer.create(rt.clock)
        vault = await open_vault(rt)
        try:
            return await set_camera_password(rt, layer, vault, serial, passwords)
        finally:
            await layer.aclose()
