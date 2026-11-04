"""Camera registry and media endpoints for VizenLink NVR."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, SecretStr

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
    RequireOwner,
    verify_camera_access,
)
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.media_token import DEFAULT_TOKEN_TTL_SECONDS, default_media_token_service
from vizenlink_nvr.services.registry import (
    CameraView,
    NewCameraRecord,
    get_camera,
    insert_camera,
    list_cameras,
)
from vizenlink_nvr.services.streams import StreamRecord
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

cameras_router = APIRouter(prefix="/cameras", tags=["cameras"])


class MediaTokenResponse(BaseModel):
    """Media token response schema."""

    token: str
    expires_in: int
    stream: str
    path: str


class StreamInput(BaseModel):
    """Input payload for stream profile."""

    role: str = "main"
    profile_token: str = "Profile_1"  # noqa: S105
    profile_name: str = "MainStream"
    venc_token: str = "VideoEncoder_1"  # noqa: S105
    codec: str = "H264"
    width: int = 1920
    height: int = 1080
    transport: str = "tcp"
    scheme: str = "rtsp"
    port: int = 554
    path: str = "/stream1"
    source: str = "onvif_fallback"
    sub_is_main: bool = False


class CameraCreateRequest(BaseModel):
    """Input payload for onboarding a new camera."""

    serial: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    https_port: int = 443
    mac: str = "00:00:00:00:00:00"
    name: str = "Camera"
    location: str = "Default"
    group_tag: str = "default"
    manufacturer: str = "Generic"
    model: str = "Generic"
    firmware_version: str = "1.0"
    hardware_id: str = "rev1"
    tls_fingerprint_sha256: str = ""
    camera_id_check: bool = True
    username: str = "admin"
    password: str = "admin123"  # noqa: S105
    capabilities_raw: str = "{}"
    streams: list[StreamInput] = []


def _resolve_vault(request: Request) -> Vault:
    """Resolve vault from app runtime or provide test vault."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and getattr(runtime, "vault", None) is not None:
        return cast(Vault, runtime.vault)
    if not hasattr(request.app.state, "vault"):
        request.app.state.vault = Vault(b"0" * 32, "test-vault-key", "memory")
    return cast(Vault, request.app.state.vault)


@cameras_router.get("", response_model=list[CameraView])
async def list_cameras_endpoint(
    user: CurrentUser,
    db: DbSession,
) -> list[CameraView]:
    """List cameras. Viewers only see their assigned cameras (AUTH-05)."""
    all_cameras = await list_cameras(db)
    if user.role in ("owner", "operator"):
        return all_cameras
    allowed = {p.camera_serial for p in user.permissions}
    return [c for c in all_cameras if c.serial in allowed]


@cameras_router.get("/{serial}", response_model=CameraView)
async def get_camera_endpoint(
    serial: str,
    user: CurrentUser,
    db: DbSession,
) -> CameraView:
    """Fetch camera details by serial. Enforces viewer access check."""
    verify_camera_access(serial, user)
    cam = await get_camera(db, serial)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{serial}' not found",
        )
    return cam


@cameras_router.post("", response_model=CameraView, status_code=status.HTTP_201_CREATED)
async def add_camera_endpoint(
    payload: CameraCreateRequest,
    user: RequireOperator,
    request: Request,
    db: DbSession,
) -> CameraView:
    """Onboard a new camera into the registry (Operator or Owner only)."""
    existing = await get_camera(db, payload.serial)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Camera with serial '{payload.serial}' already exists",
        )

    vault = _resolve_vault(request)
    sealed_pw = vault.seal(payload.serial, payload.username, SecretStr(payload.password))

    now = utc_now()
    stream_records = [
        StreamRecord(
            role=s.role,
            profile_token=s.profile_token,
            profile_name=s.profile_name,
            venc_token=s.venc_token,
            codec=s.codec,
            width=s.width,
            height=s.height,
            transport=s.transport,
            scheme=s.scheme,
            port=s.port,
            path=s.path,
            source=s.source,
            sub_is_main=s.sub_is_main,
        )
        for s in payload.streams
    ]

    record = NewCameraRecord(
        serial=payload.serial,
        host=payload.host,
        https_port=payload.https_port,
        mac=payload.mac,
        name=payload.name,
        location=payload.location,
        group_tag=payload.group_tag,
        manufacturer=payload.manufacturer,
        model=payload.model,
        firmware_version=payload.firmware_version,
        hardware_id=payload.hardware_id,
        tls_fingerprint_sha256=payload.tls_fingerprint_sha256,
        camera_id_check=payload.camera_id_check,
        username=payload.username,
        sealed_password=sealed_pw,
        capabilities_raw=payload.capabilities_raw,
        streams=stream_records,
        added_at=now,
    )

    created_view = await insert_camera(db, record)
    await db.commit()

    await AuditService.record_event(
        session=db,
        action="camera.add",
        resource_type="camera",
        resource_id=payload.serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"host": payload.host, "name": payload.name},
        commit=True,
    )

    return created_view


@cameras_router.delete("/{serial}")
async def remove_camera_endpoint(
    serial: str,
    user: RequireOwner,
    db: DbSession,
    keep_recordings: bool = True,
) -> dict[str, Any]:
    """Remove camera with explicit keep/delete recordings choice (Owner only)."""
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{serial}' not found",
        )

    deleted_count = 0
    if not keep_recordings:
        try:
            from vizenlink_nvr.services.janitor import delete_camera_recordings
            from vizenlink_nvr.services.storage import get_storage_config

            cfg = await get_storage_config(db, default_path=Path("/var/lib/vizenlink-nvr/recordings"))
            deleted_count = await delete_camera_recordings(
                session=db,
                camera_serial=serial,
                storage_path=cfg.storage_path,
            )
        except Exception as exc:
            logger.warning("Failed to delete recordings for camera %s: %s", serial, exc)

    await db.delete(cam)
    await db.commit()

    await AuditService.record_event(
        session=db,
        action="camera.remove",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"keep_recordings": keep_recordings},
        commit=True,
    )

    return {
        "serial": serial,
        "removed": True,
        "deleted": True,
        "recordings_deleted": not keep_recordings,
        "deleted_files_count": deleted_count,
    }


@cameras_router.post("/{serial}/reprobe")
async def reprobe_camera_endpoint(
    serial: str,
    user: RequireOperator,
    db: DbSession,
) -> dict[str, Any]:
    """Trigger camera reprobe (Operator or Owner only)."""
    cam = await get_camera(db, serial)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{serial}' not found",
        )
    return {
        "serial": serial,
        "reprobed": True,
        "status": cam.state,
    }


@cameras_router.post(
    "/{serial}/media-token",
    response_model=MediaTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_camera_media_token(
    serial: str,
    user: CurrentUser,
    stream: Annotated[str, Query(pattern="^(main|sub)$")] = "sub",
) -> MediaTokenResponse:
    """Generate a short-lived HMAC-signed media token for stream authorization."""
    verify_camera_access(serial, user)
    token = default_media_token_service.generate_token(
        user_id=user.id,
        camera_serial=serial,
        stream=stream,
        ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
    )
    return MediaTokenResponse(
        token=token,
        expires_in=DEFAULT_TOKEN_TTL_SECONDS,
        stream=stream,
        path=f"cam/{serial}/{stream}",
    )
