"""Camera settings REST API endpoints for configuration, ISP, OSD, reboot, and reset (SET-01..SET-08)."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from vizenlink_nvr.api.dependencies import (
    DbSession,
    RequireOperator,
    RequireViewer,
    verify_camera_access,
)
from vizenlink_nvr.camera.result import Failure, Timeout
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.camera_settings import (
    CameraNotFoundError,
    CameraOperationError,
    CameraSettingsService,
    SettingsValidationError,
)

logger = logging.getLogger(__name__)

camera_settings_router = APIRouter(prefix="/cameras/{serial}", tags=["camera-settings"])


def get_vault(request: Request) -> Vault:
    """Use the running recorder's vault; injected app vaults support isolated tests."""
    runtime = getattr(request.app.state, "runtime", None)
    vault = (
        getattr(runtime, "vault", None) if runtime is not None else getattr(request.app.state, "vault", None)
    )
    if vault is None:
        raise HTTPException(503, "The recorder credential vault is unavailable. Start the NVR service.")
    return cast(Vault, vault)


def get_settings_service(request: Request) -> CameraSettingsService:
    """Retrieve or initialize CameraSettingsService."""
    if not hasattr(request.app.state, "camera_settings_service"):
        request.app.state.camera_settings_service = CameraSettingsService()
    return cast(CameraSettingsService, request.app.state.camera_settings_service)


VaultDep = Annotated[Vault, Depends(get_vault)]
SettingsServiceDep = Annotated[CameraSettingsService, Depends(get_settings_service)]


@camera_settings_router.get("/snapshot")
async def camera_snapshot(
    serial: str,
    user: RequireViewer,
    db: DbSession,
    vault: VaultDep,
    svc: SettingsServiceDep,
    profile: Literal["high", "medium", "low"] = "medium",
    osd: bool = Query(default=True),
) -> Response:
    """Read one authenticated camera snapshot; no synthetic image fallback."""
    from vizenlink_nvr.camera.wsse import make_token
    from vizenlink_nvr.services.camera_features import camera_connection
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    if is_sim_camera(cam):
        return Response(
            SIM_CAMERAS.render_snapshot_svg(cam, include_osd=osd),
            media_type="image/svg+xml",
            headers={"Cache-Control": "private, no-store"},
        )
    conn = await camera_connection(db, vault, serial)
    digest = make_token(conn.password.get_secret_value(), svc.clock)
    username = conn.username.replace('"', '\\"')
    authorization = (
        f'Digest username="{username}", nonce="{digest.nonce_b64}", '
        f'created="{digest.created}", response="{digest.digest}"'
    )
    response = await svc.http.send(
        conn,
        "GET",
        f"/snapshot?profile={profile}",
        headers=[("Authorization", authorization)],
        timeout=8,
        max_bytes=8 * 1024 * 1024,
    )
    if isinstance(response, Timeout):
        raise HTTPException(504, "Camera snapshot timed out")
    if isinstance(response, Failure):
        raise HTTPException(502, response.reason)
    if response.status != 200:
        raise HTTPException(502, f"Camera rejected the snapshot request (HTTP {response.status})")
    if len(response.body) > 8 * 1024 * 1024 or not response.body.startswith(b"\xff\xd8\xff"):
        raise HTTPException(502, "Camera did not return a valid JPEG snapshot")
    return Response(response.body, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------


class IdentityUpdateRequest(BaseModel):
    """Request payload for updating device identity and credentials."""

    name: str | None = None
    location: str | None = None
    timezone: str | None = None
    password: str | None = None


class EncoderUpdateRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    """Request payload for updating video encoder configuration."""

    venc_token: str = Field(..., min_length=1)  # noqa: S105
    encoding: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate_limit: float | None = None
    bitrate_limit_kbps: int | None = None
    quality: float | None = None
    gov_length: int | None = None
    profile: str | None = None
    cbr: bool | None = None


class ImagingUpdateRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    """Request payload for updating camera imaging and sensor parameters."""

    video_source_token: str = "VideoSource_1"  # noqa: S105
    brightness: float | None = None
    contrast: float | None = None
    color_saturation: float | None = None
    sharpness: float | None = None
    ir_cut_filter: str | None = None
    wdr_mode: str | None = None
    wdr_level: float | None = None
    night_vision_type: str | None = None
    exposure_mode: str | None = None
    exposure_time: float | None = None
    exposure_gain: float | None = None
    white_balance_mode: str | None = None
    mirror_flip: str | None = None
    anti_flicker: str | None = None


class OsdFontColor(BaseModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    z: float = Field(ge=0, le=1, allow_inf_nan=False)
    colorspace: str = Field(max_length=200)


class OsdUpdateRequest(BaseModel):
    """Request payload for updating on-screen display overlay."""

    token: str = Field(..., min_length=1)  # noqa: S105
    video_source_token: str = "VideoSource_1"  # noqa: S105
    osd_type: str = "DateAndTime"
    position: str = "UpperLeft"
    plain_text: str | None = None
    date_format: str = "dd/MM/yyyy"
    time_format: str = "hh:mm:ss tt"
    position_x: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    position_y: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    font_size: int | None = Field(default=None, ge=1, le=256)
    font_color: OsdFontColor | None = None


class OsdCreateRequest(OsdUpdateRequest):
    token: str = ""
    video_source_token: str = "VideoSourceCfg_1"  # noqa: S105
    date_format: str = "dd/MM/yyyy"


@camera_settings_router.post("/settings/osd")
async def create_osd_endpoint(
    serial: str,
    payload: OsdCreateRequest,
    user: RequireOperator,
    db: DbSession,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> dict[str, str]:
    from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client, OsdConfig
    from vizenlink_nvr.services.audit import AuditService
    from vizenlink_nvr.services.camera_features import camera_connection, require_success

    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    if payload.osd_type not in ("Plain", "DateAndTime"):
        raise HTTPException(422, "Choose a text or timestamp overlay")
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        token = SIM_CAMERAS.create_osd(cam, payload.model_dump())
        await AuditService.record_event(
            session=db,
            action="camera.osd.create",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            details={"type": payload.osd_type},
            commit=True,
        )
        return {"status": "ok", "token": token}
    conn = await camera_connection(db, vault, serial)
    client = OnvifMedia2Client(conn, svc.http, svc.clock)
    token = require_success(await client.create_osd(OsdConfig(**payload.model_dump())))
    await AuditService.record_event(
        session=db,
        action="camera.osd.create",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"type": payload.osd_type},
        commit=True,
    )
    return {"status": "ok", "token": token}


@camera_settings_router.delete("/settings/osd/{token}")
async def delete_osd_endpoint(
    serial: str, token: str, user: RequireOperator, db: DbSession, vault: VaultDep, svc: SettingsServiceDep
) -> dict[str, str]:
    from vizenlink_nvr.camera.onvif.media2 import OnvifMedia2Client
    from vizenlink_nvr.services.audit import AuditService
    from vizenlink_nvr.services.camera_features import camera_connection, require_success

    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        SIM_CAMERAS.delete_osd(cam, token)
        await AuditService.record_event(
            session=db,
            action="camera.osd.delete",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            details={"token": token},
            commit=True,
        )
        return {"status": "ok"}
    conn = await camera_connection(db, vault, serial)
    require_success(await OnvifMedia2Client(conn, svc.http, svc.clock).delete_osd(token))
    await AuditService.record_event(
        session=db,
        action="camera.osd.delete",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"token": token},
        commit=True,
    )
    return {"status": "ok"}


class FactoryResetRequest(BaseModel):
    """Request payload for camera factory reset."""

    mode: str = "Soft"
    confirmation: str = Field(..., min_length=1)


class GenericStatusResponse(BaseModel):
    """Standard success response envelope."""

    status: str
    message: str | None = None


class CameraHealthResponse(BaseModel):
    """Camera health monitoring metrics schema."""

    serial: str
    online: bool
    uptime_seconds: int | None
    reboot_reason: str | None
    clock_sync_status: str
    firmware_version: str
    last_seen: str | None


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@camera_settings_router.get("/settings")
async def get_camera_settings_endpoint(
    serial: str,
    user: RequireViewer,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> dict[str, Any]:
    """Retrieve full capability-gated camera settings and options (SET-01..SET-08)."""
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return SIM_CAMERAS.get_settings(cam)
    try:
        return await svc.get_settings(db, vault, serial)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to fetch camera settings for %s: %s", serial, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with camera: {exc}",
        ) from exc


@camera_settings_router.put("/settings/identity")
async def update_identity_endpoint(
    serial: str,
    payload: IdentityUpdateRequest,
    user: RequireOperator,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> dict[str, Any]:
    """Update camera name, location, timezone, or password (SET-01)."""
    from vizenlink_nvr.services.audit import AuditService
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        result = SIM_CAMERAS.update_identity(cam, payload.name, payload.location, payload.timezone)
        await db.commit()
        await AuditService.record_event(
            session=db,
            action="camera.settings.update_identity",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
            details=result.get("updated", {}),
            commit=True,
        )
        return result
    try:
        return await svc.update_identity(
            session=db,
            vault=vault,
            serial=serial,
            name=payload.name,
            location=payload.location,
            timezone=payload.timezone,
            password=payload.password,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
        )
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SettingsValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@camera_settings_router.put("/settings/encoder")
async def update_encoder_endpoint(
    serial: str,
    payload: EncoderUpdateRequest,
    user: RequireOperator,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> dict[str, Any]:
    """Update video stream encoder settings within validated capability bounds (SET-02, SET-08)."""
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return SIM_CAMERAS.update_encoder(cam, payload.model_dump())
    try:
        return await svc.update_encoder(
            session=db,
            vault=vault,
            serial=serial,
            venc_token=payload.venc_token,
            encoding=payload.encoding,
            width=payload.width,
            height=payload.height,
            frame_rate_limit=payload.frame_rate_limit,
            bitrate_limit_kbps=payload.bitrate_limit_kbps,
            quality=payload.quality,
            gov_length=payload.gov_length,
            profile=payload.profile,
            cbr=payload.cbr,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
        )
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SettingsValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@camera_settings_router.put("/settings/imaging")
async def update_imaging_endpoint(
    serial: str,
    payload: ImagingUpdateRequest,
    user: RequireOperator,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> dict[str, Any]:
    """Update Day/Night mode, WDR, ISP parameters, mirror/flip, and anti-flicker (SET-03, SET-08)."""
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return SIM_CAMERAS.update_imaging(cam, payload.model_dump())
    try:
        return await svc.update_imaging(
            session=db,
            vault=vault,
            serial=serial,
            video_source_token=payload.video_source_token,
            brightness=payload.brightness,
            contrast=payload.contrast,
            color_saturation=payload.color_saturation,
            sharpness=payload.sharpness,
            ir_cut_filter=payload.ir_cut_filter,
            wdr_mode=payload.wdr_mode,
            wdr_level=payload.wdr_level,
            night_vision_type=payload.night_vision_type,
            mirror_flip=payload.mirror_flip,
            anti_flicker=payload.anti_flicker,
            exposure_mode=payload.exposure_mode,
            exposure_time=payload.exposure_time,
            exposure_gain=payload.exposure_gain,
            white_balance_mode=payload.white_balance_mode,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
        )
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SettingsValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@camera_settings_router.put("/settings/osd")
async def update_osd_endpoint(
    serial: str,
    payload: OsdUpdateRequest,
    user: RequireOperator,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> dict[str, Any]:
    """Update On-Screen Display (OSD) overlay text and timestamp positioning (SET-04)."""
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return SIM_CAMERAS.update_osd(cam, payload.model_dump())
    try:
        return await svc.update_osd(
            session=db,
            vault=vault,
            serial=serial,
            token=payload.token,
            video_source_token=payload.video_source_token,
            osd_type=payload.osd_type,
            position=payload.position,
            plain_text=payload.plain_text,
            date_format=payload.date_format,
            time_format=payload.time_format,
            position_x=payload.position_x,
            position_y=payload.position_y,
            font_size=payload.font_size,
            font_color=payload.font_color.model_dump() if payload.font_color else None,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
        )
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SettingsValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@camera_settings_router.post("/reboot", response_model=GenericStatusResponse)
async def reboot_camera_endpoint(
    serial: str,
    user: RequireOperator,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> GenericStatusResponse:
    """Trigger camera reboot via ONVIF SystemReboot (SET-05)."""
    from vizenlink_nvr.services.sim_camera import is_sim_camera

    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return GenericStatusResponse(status="ok", message="Simulated camera rebooting in 5 seconds")
    try:
        msg = await svc.reboot(
            session=db,
            vault=vault,
            serial=serial,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
        )
        return GenericStatusResponse(status="ok", message=msg)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@camera_settings_router.post("/factory-reset", response_model=GenericStatusResponse)
async def factory_reset_camera_endpoint(
    serial: str,
    payload: FactoryResetRequest,
    user: RequireOperator,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> GenericStatusResponse:
    """Trigger camera factory reset (Soft or Hard) with confirmation check (SET-06)."""
    verify_camera_access(serial, user)

    # Require explicit confirmation string
    if payload.confirmation.strip().upper() not in ("RESET", "CONFIRM"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation keyword required ('RESET' or 'CONFIRM')",
        )

    mode = payload.mode.strip().capitalize()
    if mode not in ("Soft", "Hard"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset mode must be 'Soft' or 'Hard'",
        )

    client_ip = request.client.host if request.client else None
    from vizenlink_nvr.services.sim_camera import is_sim_camera

    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return GenericStatusResponse(status="ok", message=f"{mode} factory reset simulated")
    try:
        await svc.factory_reset(
            session=db,
            vault=vault,
            serial=serial,
            mode=mode,
            actor_id=user.id,
            actor_username=user.username,
            ip_address=client_ip,
        )
        return GenericStatusResponse(
            status="ok",
            message=f"{mode} factory reset initiated successfully",
        )
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@camera_settings_router.get("/health", response_model=CameraHealthResponse)
async def get_camera_health_endpoint(
    serial: str,
    user: RequireViewer,
    db: DbSession,
    request: Request,
    vault: VaultDep,
    svc: SettingsServiceDep,
) -> CameraHealthResponse:
    """Retrieve camera health, uptime, and clock sync state (SET-07)."""
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return CameraHealthResponse(**SIM_CAMERAS.get_health(cam))
    try:
        health_data = await svc.get_health(db, vault, serial)
        return CameraHealthResponse(**health_data)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CameraOperationError as exc:
        raise HTTPException(502, str(exc)) from exc
