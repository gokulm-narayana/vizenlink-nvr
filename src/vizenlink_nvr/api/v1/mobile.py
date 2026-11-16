"""Mobile LAN Integration REST API endpoints (MOB-03, MOB-04, MOB-05, MOB-06, MOB-07)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
    RequireOwner,
    verify_camera_access,
)
from vizenlink_nvr.db.models import Camera, RecordingSettings, Segment
from vizenlink_nvr.media.config import camera_path_name
from vizenlink_nvr.services.health import RecorderHealthService
from vizenlink_nvr.services.media_token import DEFAULT_TOKEN_TTL_SECONDS, default_media_token_service
from vizenlink_nvr.services.mobile_auth import MobileAuthService
from vizenlink_nvr.services.recording_settings import (
    get_or_create_recording_settings,
    set_recording_mode,
)
from vizenlink_nvr.services.storage import get_storage_config
from vizenlink_nvr.services.timeline import TimelineService
from vizenlink_nvr.timeutil import UTC, utc_now

mobile_router = APIRouter(tags=["mobile"])

UserDep = CurrentUser
DbDep = DbSession
OperatorDep = RequireOperator
OwnerDep = RequireOwner


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MobileUserSummary(BaseModel):
    """Authenticated user info schema."""

    id: int
    username: str
    role: str


class MobilePairRequest(BaseModel):
    """Direct credential pairing request payload."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    device_id: str = Field(..., min_length=1)
    device_name: str = Field(..., min_length=1)
    platform: str = Field("unknown")


class MobilePairQRRequest(BaseModel):
    """QR code pairing redemption payload."""

    pairing_code: str = Field(..., min_length=1)
    device_id: str = Field(..., min_length=1)
    device_name: str = Field(..., min_length=1)
    platform: str = Field("unknown")


class MobileTokenResponse(BaseModel):
    """Pairing success token payload."""

    device_id: str
    access_token: str
    refresh_token: str
    expires_in: int
    user: MobileUserSummary


class MobileRefreshRequest(BaseModel):
    """Token refresh payload."""

    refresh_token: str = Field(..., min_length=1)


class MobileRefreshResponse(BaseModel):
    """Token refresh response payload."""

    access_token: str
    expires_in: int


class MobileQRInitResponse(BaseModel):
    """Ephemeral QR pairing initiation response."""

    pairing_code: str
    qr_payload: str
    expires_at: datetime


class PairedDeviceResponse(BaseModel):
    """Paired mobile device representation."""

    id: str
    device_id: str
    device_name: str
    platform: str
    user_id: int
    username: str | None = None
    paired_at: datetime
    last_seen_at: datetime
    is_revoked: bool
    revoked_at: datetime | None = None


class MobileLiveStreamResponse(BaseModel):
    """Mobile live streaming relay URLs."""

    camera_serial: str
    profile: str
    token: str
    webrtc_url: str
    hls_url: str
    rtsp_url: str


class MobileRecordingDatesResponse(BaseModel):
    """List of calendar dates with recorded footage."""

    camera_serial: str
    dates: list[str]


class MobileRecordingClip(BaseModel):
    """Recording timeline segment representation."""

    id: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    size_bytes: int
    trigger: str
    stream_url: str


class MobileRecordingsResponse(BaseModel):
    """Recording history clips for a single day."""

    camera_serial: str
    date: str
    recordings: list[MobileRecordingClip]


class MobileStorageStats(BaseModel):
    """Aggregated disk metrics."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    estimated_retention_days: float | None = None


class MobileCameraItemStatus(BaseModel):
    """Per-camera telemetry item."""

    serial: str
    name: str
    is_online: bool
    is_recording: bool
    recording_mode: str
    storage_used_bytes: int = 0


class MobileStatusResponse(BaseModel):
    """Consolidated mobile health and telemetry summary."""

    status: str
    storage: MobileStorageStats
    cameras: list[MobileCameraItemStatus]


class MobileRecordingModeUpdateRequest(BaseModel):
    """Payload to alter camera recording policy."""

    mode: str = Field(..., pattern="^(continuous|event|scheduled|off)$")


class MobileCameraAddRequest(BaseModel):
    """Simplified camera onboarding from mobile."""

    serial: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    https_port: int = 443
    username: str = "admin"
    password: str = "admin123"  # noqa: S105


# ---------------------------------------------------------------------------
# Pairing & Device Management Endpoints (MOB-03)
# ---------------------------------------------------------------------------


@mobile_router.post(
    "/pair",
    response_model=MobileTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def pair_device_credentials(
    payload: MobilePairRequest,
    db: DbDep,
) -> MobileTokenResponse:
    """Enroll mobile device using direct username and password."""
    try:
        device, access_token, refresh_token = await MobileAuthService.pair_via_credentials(
            db=db,
            username=payload.username,
            password=payload.password,
            device_id=payload.device_id,
            device_name=payload.device_name,
            platform=payload.platform,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        ) from err

    user = device.user
    return MobileTokenResponse(
        device_id=device.device_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
        user=MobileUserSummary(id=user.id, username=user.username, role=user.role),
    )


@mobile_router.post(
    "/pair-qr",
    response_model=MobileTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def pair_device_qr(
    payload: MobilePairQRRequest,
    db: DbDep,
) -> MobileTokenResponse:
    """Redeem ephemeral QR pairing code from mobile app."""
    try:
        device, access_token, refresh_token = await MobileAuthService.pair_via_qr(
            db=db,
            pairing_code=payload.pairing_code,
            device_id=payload.device_id,
            device_name=payload.device_name,
            platform=payload.platform,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    user = device.user
    return MobileTokenResponse(
        device_id=device.device_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
        user=MobileUserSummary(id=user.id, username=user.username, role=user.role),
    )


@mobile_router.post(
    "/refresh",
    response_model=MobileRefreshResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_mobile_token(
    payload: MobileRefreshRequest,
    db: DbDep,
) -> MobileRefreshResponse:
    """Issue a new access token using a valid, unrevoked refresh token."""
    try:
        new_token, exp = await MobileAuthService.refresh_token(db, payload.refresh_token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        ) from err

    return MobileRefreshResponse(access_token=new_token, expires_in=int((exp - utc_now()).total_seconds()))


@mobile_router.post(
    "/qr/init",
    response_model=MobileQRInitResponse,
    status_code=status.HTTP_200_OK,
)
async def init_qr_pairing(
    user: UserDep,
    db: DbDep,
) -> MobileQRInitResponse:
    """Generate ephemeral QR pairing code for web UI display."""
    sess, payload = await MobileAuthService.create_qr_pairing_session(db, user.id)
    return MobileQRInitResponse(
        pairing_code=sess.pairing_code,
        qr_payload=payload,
        expires_at=sess.expires_at,
    )


@mobile_router.get(
    "/devices",
    response_model=list[PairedDeviceResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paired_devices(
    user: UserDep,
    db: DbDep,
) -> list[PairedDeviceResponse]:
    """List paired mobile devices (all for Owner, self for other roles)."""
    filter_user = None if user.role == "owner" else user.id
    devices = await MobileAuthService.list_devices(db, user_id=filter_user)

    return [
        PairedDeviceResponse(
            id=d.id,
            device_id=d.device_id,
            device_name=d.device_name,
            platform=d.platform,
            user_id=d.user_id,
            username=d.user.username if d.user else None,
            paired_at=d.paired_at,
            last_seen_at=d.last_seen_at,
            is_revoked=d.is_revoked,
            revoked_at=d.revoked_at,
        )
        for d in devices
    ]


@mobile_router.post(
    "/devices/{device_id}/revoke",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
)
@mobile_router.delete(
    "/devices/{device_id}",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
)
async def revoke_device_endpoint(
    device_id: str,
    user: UserDep,
    db: DbDep,
) -> dict[str, bool]:
    """Revoke a paired mobile device, immediately blocking access."""
    try:
        ok = await MobileAuthService.revoke_device(db, device_id, actor=user)
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )
    return {"revoked": True}


# ---------------------------------------------------------------------------
# Mobile Live Streaming Relay (MOB-04)
# ---------------------------------------------------------------------------


@mobile_router.get(
    "/cameras/{camera_id}/live-stream",
    response_model=MobileLiveStreamResponse,
    status_code=status.HTTP_200_OK,
)
async def get_mobile_live_stream(
    camera_id: str,
    request: Request,
    user: UserDep,
    db: DbDep,
    profile: Annotated[Literal["main", "sub"], Query()] = "sub",
) -> MobileLiveStreamResponse:
    """Retrieve mobile live stream URLs defaulting to lightweight sub stream."""
    verify_camera_access(camera_id, user)

    # Verify camera exists
    cam = await db.get(Camera, camera_id)
    if cam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Camera '{camera_id}' not found")

    token = default_media_token_service.generate_token(
        user_id=user.id,
        camera_serial=camera_id,
        stream=profile,
        ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
    )

    host = request.url.hostname or "127.0.0.1"
    mediamtx_port = 8889
    rtsp_port = 8554

    path = camera_path_name(camera_id, profile)
    webrtc_url = f"http://{host}:{mediamtx_port}/{path}/whep?token={token}"
    hls_url = f"http://{host}:{mediamtx_port}/{path}/index.m3u8?token={token}"
    rtsp_url = f"rtsp://{host}:{rtsp_port}/{path}?token={token}"

    return MobileLiveStreamResponse(
        camera_serial=camera_id,
        profile=profile,
        token=token,
        webrtc_url=webrtc_url,
        hls_url=hls_url,
        rtsp_url=rtsp_url,
    )


# ---------------------------------------------------------------------------
# Mobile Recorded History Browsing (MOB-05)
# ---------------------------------------------------------------------------


@mobile_router.get(
    "/cameras/{camera_id}/recording-dates",
    response_model=MobileRecordingDatesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_mobile_recording_dates(
    camera_id: str,
    user: UserDep,
    db: DbDep,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
) -> MobileRecordingDatesResponse:
    """Return dates with footage for calendar timeline."""
    verify_camera_access(camera_id, user)
    now = utc_now()
    target_year = year or now.year
    target_month = month or now.month

    days = await TimelineService.get_recorded_days(
        session=db,
        camera_serial=camera_id,
        year=target_year,
        month=target_month,
    )
    return MobileRecordingDatesResponse(camera_serial=camera_id, dates=days)


@mobile_router.get(
    "/cameras/{camera_id}/recordings",
    response_model=MobileRecordingsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_mobile_recordings(
    camera_id: str,
    user: UserDep,
    db: DbDep,
    date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> MobileRecordingsResponse:
    """Return recorded clips for a specific calendar day."""
    verify_camera_access(camera_id, user)

    try:
        dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format, expected YYYY-MM-DD",
        ) from err

    day_start = dt
    day_end = dt + timedelta(days=1)

    timeline_data = await TimelineService.get_timeline(
        session=db,
        camera_serial=camera_id,
        start_time=day_start,
        end_time=day_end,
    )

    clips: list[MobileRecordingClip] = []
    for s in timeline_data.segments:
        trigger = "event" if s.is_protected else "continuous"
        clips.append(
            MobileRecordingClip(
                id=s.id,
                start_time=s.start_time,
                end_time=s.end_time,
                duration_seconds=s.duration_seconds,
                size_bytes=s.file_size_bytes,
                trigger=trigger,
                stream_url=f"/api/v1/playback/stream/{s.id}",
            )
        )

    return MobileRecordingsResponse(
        camera_serial=camera_id,
        date=date,
        recordings=clips,
    )


# ---------------------------------------------------------------------------
# Mobile Health & Telemetry Status (MOB-06)
# ---------------------------------------------------------------------------


@mobile_router.get(
    "/status",
    response_model=MobileStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_mobile_status(
    user: UserDep,
    db: DbDep,
) -> MobileStatusResponse:
    """Consolidated recorder status and camera telemetry for mobile dashboard."""
    # System health
    health = await RecorderHealthService.get_recorder_status(db)
    system_status = (
        health.status.value if hasattr(health.status, "value") else str(health.status)
    )

    # Storage config & telemetry
    from pathlib import Path
    storage_cfg = await get_storage_config(
        session=db,
        default_path=Path("/var/lib/vizenlink-nvr/recordings"),
    )
    telem = storage_cfg.telemetry
    storage_stats = MobileStorageStats(
        total_bytes=telem.total_bytes if telem else 0,
        used_bytes=telem.used_bytes if telem else 0,
        free_bytes=telem.free_bytes if telem else 0,
        estimated_retention_days=storage_cfg.estimated_retention_days,
    )

    # Cameras
    stmt = (
        select(Camera)
        .outerjoin(RecordingSettings, Camera.serial == RecordingSettings.camera_serial)
    )
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        stmt = stmt.where(Camera.serial.in_(allowed))

    cameras = (await db.execute(stmt)).scalars().all()

    camera_items: list[MobileCameraItemStatus] = []
    for cam in cameras:
        rec_settings = await get_or_create_recording_settings(db, cam.serial)

        # Count storage used for this camera
        size_stmt = (
            select(func.coalesce(func.sum(Segment.file_size_bytes), 0))
            .where(Segment.camera_serial == cam.serial)
        )
        cam_storage = (await db.execute(size_stmt)).scalar() or 0

        is_online = cam.state == "active"
        is_rec = rec_settings.mode in ("continuous", "scheduled", "event")

        camera_items.append(
            MobileCameraItemStatus(
                serial=cam.serial,
                name=cam.name,
                is_online=is_online,
                is_recording=is_rec,
                recording_mode=rec_settings.mode,
                storage_used_bytes=int(cam_storage),
            )
        )

    return MobileStatusResponse(
        status=system_status,
        storage=storage_stats,
        cameras=camera_items,
    )


# ---------------------------------------------------------------------------
# Mobile Camera Management & Recording Mode (MOB-07)
# ---------------------------------------------------------------------------


@mobile_router.put(
    "/cameras/{camera_id}/recording-mode",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def update_mobile_recording_mode(
    camera_id: str,
    payload: MobileRecordingModeUpdateRequest,
    user: OperatorDep,
    db: DbDep,
) -> dict[str, Any]:
    """Alter camera recording mode (Operator or Owner only)."""
    verify_camera_access(camera_id, user)
    cam = await db.get(Camera, camera_id)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found",
        )

    updated = await set_recording_mode(db, camera_id, payload.mode)
    return {
        "camera_serial": camera_id,
        "mode": updated.mode,
        "updated_at": updated.updated_at,
    }


@mobile_router.post(
    "/cameras",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
async def add_mobile_camera(
    payload: MobileCameraAddRequest,
    user: OwnerDep,
    db: DbDep,
) -> dict[str, Any]:
    """Onboard a new camera from mobile (Owner only)."""
    existing = await db.get(Camera, payload.serial)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Camera with serial '{payload.serial}' already exists",
        )

    cam = Camera(
        serial=payload.serial,
        name=payload.name,
        host=payload.host,
        https_port=payload.https_port,
        tls_fingerprint_sha256="",
        state="active",
        added_at=utc_now(),
        host_updated_at=utc_now(),
    )
    db.add(cam)
    await db.commit()
    await db.refresh(cam)

    return {"serial": cam.serial, "name": cam.name, "created": True}


@mobile_router.delete(
    "/cameras/{camera_id}",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def remove_mobile_camera(
    camera_id: str,
    user: OwnerDep,
    db: DbDep,
) -> dict[str, Any]:
    """Remove a camera from mobile (Owner only)."""
    cam = await db.get(Camera, camera_id)
    if cam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found",
        )

    await db.delete(cam)
    await db.commit()
    return {"serial": camera_id, "deleted": True}
