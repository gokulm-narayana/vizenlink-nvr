"""Camera settings REST API endpoints for configuration, ISP, OSD, reboot, and reset (SET-01..SET-08)."""

from __future__ import annotations

import logging
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from vizenlink_nvr.api.dependencies import (
    DbSession,
    RequireOperator,
    RequireViewer,
    verify_camera_access,
)
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
    """Retrieve or create default vault instance on app.state."""
    if not hasattr(request.app.state, "vault"):
        request.app.state.vault = Vault(b"0" * 32, "test-vault-key", "memory")
    return cast(Vault, request.app.state.vault)


def get_settings_service(request: Request) -> CameraSettingsService:
    """Retrieve or initialize CameraSettingsService."""
    if not hasattr(request.app.state, "camera_settings_service"):
        request.app.state.camera_settings_service = CameraSettingsService()
    return cast(CameraSettingsService, request.app.state.camera_settings_service)


VaultDep = Annotated[Vault, Depends(get_vault)]
SettingsServiceDep = Annotated[CameraSettingsService, Depends(get_settings_service)]


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
    """Request payload for updating video encoder configuration."""

    venc_token: str = Field(..., min_length=1)  # noqa: S105
    encoding: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate_limit: float | None = None
    bitrate_limit_kbps: int | None = None
    quality: float | None = None
    gov_length: int | None = None


class ImagingUpdateRequest(BaseModel):
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


class OsdUpdateRequest(BaseModel):
    """Request payload for updating on-screen display overlay."""

    token: str = Field(..., min_length=1)  # noqa: S105
    video_source_token: str = "VideoSource_1"  # noqa: S105
    osd_type: str = "DateAndTime"
    position: str = "UpperLeft"
    plain_text: str | None = None
    date_format: str = "YYYY/MM/DD"
    time_format: str = "HH:mm:ss"


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
    verify_camera_access(serial, user)
    try:
        return await svc.get_settings(db, vault, serial)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
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
    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
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
    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
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
    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
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
    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
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
    verify_camera_access(serial, user)
    client_ip = request.client.host if request.client else None
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
    verify_camera_access(serial, user)
    try:
        health_data = await svc.get_health(db, vault, serial)
        return CameraHealthResponse(**health_data)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
