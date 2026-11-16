"""Camera registry and media endpoints for VizenLink NVR."""

from __future__ import annotations

import asyncio
import logging
from ipaddress import IPv4Address
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
from vizenlink_nvr.camera.layer import CameraLayer
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.media_token import DEFAULT_TOKEN_TTL_SECONDS, default_media_token_service
from vizenlink_nvr.services.onboarding import AddOutcomeKind, AddRequest, OnboardingService
from vizenlink_nvr.services.registry import (
    CameraView,
    NewCameraRecord,
    archive_camera,
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


class DiscoveredCameraCredentials(BaseModel):
    host: IPv4Address
    port: int = Field(default=443, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128, pattern=r"\S")
    password: SecretStr
    new_camera_password: SecretStr | None = None

    async def current_password(self) -> SecretStr:
        return self.password

    async def new_password(self) -> SecretStr:
        if self.new_camera_password is not None and self.new_camera_password.get_secret_value():
            return self.new_camera_password
        raise RuntimeError("Discovered camera onboarding uses existing credentials")


def _resolve_vault(request: Request) -> Vault:
    """Resolve operational vault from runtime. Fails closed (503) when unavailable (D-18)."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and getattr(runtime, "vault", None) is not None:
        return cast(Vault, runtime.vault)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Camera credentials can't be stored because the NVR credential vault is unavailable.",
    )


@cameras_router.post("/discover")
async def discover_cameras_endpoint(user: RequireOperator, request: Request) -> dict[str, Any]:
    """Discover cameras from the recorder's LAN without terminal access."""
    from vizenlink_nvr.services.scan import run_scan

    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None or getattr(runtime, "settings", None) is None:
        raise HTTPException(
            status_code=503, detail="Camera discovery requires the NVR service to be running."
        )
    if getattr(request.app.state, "camera_scan_running", False):
        raise HTTPException(status_code=409, detail="A camera search is already running. Try again shortly.")
    request.app.state.camera_scan_running = True
    try:
        report = await asyncio.wait_for(run_scan(runtime.settings, timeout=2.0), timeout=30.0)
        return report.model_dump()
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504, detail="The camera search timed out. Check the network and try again."
        ) from exc
    except PermissionError as exc:
        logger.warning("Camera discovery blocked by local network permissions: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "The recorder was denied access to the local network. "
                "Check local network permissions for the process running the NVR, then retry."
            ),
        ) from exc
    except OSError as exc:
        logger.warning("Camera discovery network failure: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Couldn't search the recorder's network. Check its connection and try again.",
        ) from exc
    finally:
        request.app.state.camera_scan_running = False


@cameras_router.get("", response_model=list[CameraView])
async def list_cameras_endpoint(
    user: CurrentUser,
    db: DbSession,
    playback: bool = False,
) -> list[CameraView]:
    """List cameras. Viewers only see their assigned cameras (AUTH-05)."""
    all_cameras = await list_cameras(db, playback=playback)
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
    vault = _resolve_vault(request)

    existing = await get_camera(db, payload.serial)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Camera with serial '{payload.serial}' already exists",
        )

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


@cameras_router.post("/onboard", response_model=CameraView, status_code=status.HTTP_201_CREATED)
async def onboard_discovered_camera(
    payload: DiscoveredCameraCredentials, user: RequireOperator, request: Request, db: DbSession
) -> CameraView:
    """Verify credentials and register the camera with its actual device and stream information."""
    if not 0 < len(payload.password.get_secret_value()) <= 1024:
        raise HTTPException(status_code=400, detail="Enter the camera password.")
    vault = _resolve_vault(request)
    runtime = request.app.state.runtime
    host = str(payload.host)
    layer = CameraLayer.create(runtime.clock)
    try:
        service = OnboardingService(runtime, layer, vault)
        outcome = await service.add(
            AddRequest(host=host, port=payload.port), payload, username=payload.username.strip()
        )
    finally:
        await layer.aclose()

    if outcome.kind is not AddOutcomeKind.OK or outcome.camera is None:
        errors = {
            AddOutcomeKind.ALREADY_REGISTERED: (409, "This camera is already registered."),
            AddOutcomeKind.WRONG_CREDENTIALS: (400, "The camera rejected the username or password."),
            AddOutcomeKind.NEEDS_NEW_PASSWORD: (400, "Set a new password on the camera before adding it."),
            AddOutcomeKind.BLOCKED: (429, "The camera blocked sign-in attempts. Try again later."),
            AddOutcomeKind.FORBIDDEN: (403, "This camera account cannot read the required settings."),
            AddOutcomeKind.UNREACHABLE: (502, "Could not reach the camera. Check its connection."),
            AddOutcomeKind.TLS_CHANGED: (502, "The camera certificate changed during setup. Try again."),
            AddOutcomeKind.UNSUPPORTED_DEVICE: (400, "Could not verify this as a supported camera."),
            AddOutcomeKind.NO_SERIAL: (502, "The camera did not report a serial number."),
            AddOutcomeKind.STREAMS_UNAVAILABLE: (502, "The camera did not provide a usable video stream."),
            AddOutcomeKind.INVALID_INPUT: (400, "Choose a camera on the recorder’s local network."),
        }
        if outcome.kind is AddOutcomeKind.INVALID_INPUT and outcome.detail in (
            "Use 8 to 32 characters.",
            "Choose a password other than the factory password.",
        ):
            raise HTTPException(status_code=400, detail=outcome.detail)
        status_code, detail = errors.get(outcome.kind, (500, "Could not save the camera. Try again."))
        raise HTTPException(status_code=status_code, detail=detail)

    camera = outcome.camera
    await AuditService.record_event(
        session=db,
        action="camera.add",
        resource_type="camera",
        resource_id=camera.serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"host": camera.host, "name": camera.name},
        commit=True,
    )
    return camera


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
            raise HTTPException(500, "Could not purge recordings. Camera registration was kept.") from exc

    if keep_recordings:
        await archive_camera(db, cam)
    else:
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
    request: Request,
) -> dict[str, Any]:
    """Check the camera connection now (old VMS "Retry connection").

    Verifies the camera at its stored address, follows it if DHCP moved it, and refreshes
    capabilities and streams. Never accepts a changed certificate automatically.
    """
    cam = await get_camera(db, serial)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{serial}' not found",
        )
    from vizenlink_nvr.services.sim_camera import is_sim_camera

    if is_sim_camera(cam):
        return {
            "serial": serial,
            "reprobed": True,
            "status": cam.state,
            "kind": "SIMULATED_OK",
            "address": f"{cam.host}:{cam.https_port}",
            "warnings": [],
        }
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None or getattr(runtime, "settings", None) is None or not hasattr(runtime, "sessions"):
        # No live runtime (e.g. tests): report the stored state without contacting the camera.
        return {"serial": serial, "reprobed": False, "status": cam.state, "kind": None, "warnings": []}

    from vizenlink_nvr.camera.layer import CameraLayer
    from vizenlink_nvr.services.recovery import make_healer
    from vizenlink_nvr.services.reprobe import reprobe_camera

    layer = CameraLayer.create(runtime.clock)
    healer = make_healer(runtime, layer, runtime.settings)
    try:
        report = await asyncio.wait_for(reprobe_camera(runtime, layer, healer, serial), timeout=45.0)
    except TimeoutError:
        return {
            "serial": serial,
            "reprobed": True,
            "status": cam.state,
            "kind": "UNREACHABLE",
            "address": f"{cam.host}:{cam.https_port}",
            "warnings": ["The camera did not answer within 45 seconds."],
        }
    finally:
        await healer.aclose()
        await layer.aclose()

    await AuditService.record_event(
        session=db,
        action="camera.reprobe",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"kind": str(report.kind)},
        commit=True,
    )
    fresh = await get_camera(db, serial)
    return {
        "serial": serial,
        "reprobed": True,
        "status": fresh.state if fresh else cam.state,
        "kind": str(report.kind),
        "address": report.address,
        "warnings": report.warnings,
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
        path=f"cam/{serial}/{stream}",  # browser URL; the proxy maps it to the MediaMTX path
    )
