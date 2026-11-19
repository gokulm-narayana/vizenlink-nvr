"""Mobile LAN Integration REST API endpoints (MOB-03, MOB-04, MOB-05, MOB-06, MOB-07)."""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import subprocess
import tempfile
import uuid
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

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
from vizenlink_nvr.api.v1.cameras import (
    DiscoveredCameraCredentials,
    onboard_discovered_camera,
    remove_camera_endpoint,
)
from vizenlink_nvr.api.v1.playback import (
    GalleryItemModel,
    SaveSnapshotRequest,
    _resolve_storage_root,
    save_snapshot,
)
from vizenlink_nvr.db.models import Camera, RecordingSettings, Segment
from vizenlink_nvr.network.mdns import get_local_ip
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.gallery import GalleryService
from vizenlink_nvr.services.health import RecorderHealthService, RecordingState
from vizenlink_nvr.services.media_token import DEFAULT_TOKEN_TTL_SECONDS, default_media_token_service
from vizenlink_nvr.services.mobile_auth import MobileAuthService
from vizenlink_nvr.services.rate_limiter import login_rate_limiter
from vizenlink_nvr.services.recording_settings import (
    get_or_create_recording_settings,
    set_recording_mode,
    should_record_now,
)
from vizenlink_nvr.services.settings import read_site_timezone
from vizenlink_nvr.services.storage import StorageHealthState, get_storage_config
from vizenlink_nvr.services.timeline import TimelineService
from vizenlink_nvr.services.watchdog import check_camera_gaps
from vizenlink_nvr.timeutil import UTC, local_day_bounds_utc, utc_now

mobile_router = APIRouter(tags=["mobile"])
logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")  # noqa: S104


def _lan_base_url(request: Request) -> tuple[str, str | None, int]:
    """Return reachable (base_url, host, port), resolving loopback UI hosts to LAN IP."""
    scheme = request.url.scheme or "http"
    port = request.url.port or (443 if scheme == "https" else 80)
    req_host = request.url.hostname
    if not req_host or req_host in _LOOPBACK_HOSTS:
        candidate = get_local_ip()
        resolved_host = candidate if candidate not in _LOOPBACK_HOSTS else None
    else:
        resolved_host = req_host

    if resolved_host is None:
        return str(request.base_url).rstrip("/"), None, port

    formatted_host = (
        f"[{resolved_host}]" if ":" in resolved_host and not resolved_host.startswith("[") else resolved_host
    )
    is_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    host_part = formatted_host if is_default_port else f"{formatted_host}:{port}"
    return f"{scheme}://{host_part}", resolved_host, port

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
    server_url: str | None = None


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
    """Mobile live streaming relay URLs.

    ``webrtc_url`` is the authenticated WHEP proxy on this API's own host and port
    (``/cam/{serial}/{stream}/whep``) — POST an SDP offer there with the device's
    ``Authorization: Bearer`` header (or signed ``token`` query parameter).
    ``hls_url`` points to the authenticated HLS fallback proxy on the same NVR port
    (``/cam/{serial}/{stream}/hls/{token}/index.m3u8``) for clients/codecs (such as
    H.265) where WebRTC cannot negotiate. MediaMTX itself listens on loopback only, so
    ``rtsp_url`` is not reachable from a phone and stays null.
    """

    camera_serial: str
    profile: str
    token: str
    webrtc_url: str
    hls_url: str | None = None
    rtsp_url: str | None = None


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
    signed_stream_url: str | None = None


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


# Camera onboarding from mobile reuses the web UI's payload (host, port, username,
# password, optional new_camera_password) so both go through OnboardingService.
MobileCameraAddRequest = DiscoveredCameraCredentials


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
    request: Request,
    db: DbDep,
) -> MobileTokenResponse:
    """Enroll mobile device using direct username and password."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    username = payload.username.strip()

    if login_rate_limiter.is_locked(username):
        rem = login_rate_limiter.remaining_lockout_seconds(username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to too many failed attempts. Try again in {rem} seconds.",
        )
    if login_rate_limiter.is_locked(client_ip):
        rem = login_rate_limiter.remaining_lockout_seconds(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"IP temporarily locked due to too many failed attempts. Try again in {rem} seconds.",
        )

    try:
        device, access_token, refresh_token = await MobileAuthService.pair_via_credentials(
            db=db,
            username=username,
            password=payload.password,
            device_id=payload.device_id,
            device_name=payload.device_name,
            platform=payload.platform,
        )
    except ValueError as err:
        login_rate_limiter.record_failure(username)
        login_rate_limiter.record_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        ) from err

    login_rate_limiter.reset(username)
    login_rate_limiter.reset(client_ip)

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
    request: Request,
    user: UserDep,
    db: DbDep,
) -> MobileQRInitResponse:
    """Generate ephemeral QR pairing code for web UI display.

    The payload also carries ``host``/``port``/``scheme`` so a phone scanning the QR
    knows which NVR to redeem it against. When the web UI is opened via loopback
    (localhost / 127.0.0.1), the host's LAN IP is resolved automatically.
    """
    sess, payload = await MobileAuthService.create_qr_pairing_session(db, user.id)
    base, resolved_host, port = _lan_base_url(request)
    server_url: str | None = None
    if resolved_host is not None:
        scheme = request.url.scheme or "http"
        payload = f"{payload}&host={resolved_host}&port={port}&scheme={scheme}"
        server_url = base
    return MobileQRInitResponse(
        pairing_code=sess.pairing_code,
        qr_payload=payload,
        expires_at=sess.expires_at,
        server_url=server_url,
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

    # The phone reaches the NVR on the same scheme/host/port it used for this call (or
    # LAN IP if invoked over loopback); /cam proxies WHEP and HLS to loopback MediaMTX.
    base, _, _ = _lan_base_url(request)
    # Keep the serial's original case: the proxy checks per-camera permissions with it
    # (and lower-cases it itself, via camera_path_name, for the MediaMTX path).
    webrtc_url = f"{base}/cam/{camera_id}/{profile}/whep?token={token}"
    hls_url = f"{base}/cam/{camera_id}/{profile}/hls/{token}/index.m3u8"

    return MobileLiveStreamResponse(
        camera_serial=camera_id,
        profile=profile,
        token=token,
        webrtc_url=webrtc_url,
        hls_url=hls_url,
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
    """Return site-timezone dates with footage for calendar timeline."""
    verify_camera_access(camera_id, user)
    tz_name = await read_site_timezone(db)
    local_now = utc_now().astimezone(ZoneInfo(tz_name))
    target_year = year or local_now.year
    target_month = month or local_now.month

    days = await TimelineService.get_recorded_days(
        session=db,
        camera_serial=camera_id,
        year=target_year,
        month=target_month,
        tz_name=tz_name,
    )
    return MobileRecordingDatesResponse(camera_serial=camera_id, dates=days)


@mobile_router.get(
    "/cameras/{camera_id}/recordings",
    response_model=MobileRecordingsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_mobile_recordings(
    camera_id: str,
    request: Request,
    user: UserDep,
    db: DbDep,
    date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> MobileRecordingsResponse:
    """Return recorded clips for a specific site-timezone calendar day."""
    verify_camera_access(camera_id, user)

    tz_name = await read_site_timezone(db)
    zone = ZoneInfo(tz_name)
    try:
        local_day = date_cls.fromisoformat(date)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format, expected YYYY-MM-DD",
        ) from err

    day_start, day_end = local_day_bounds_utc(local_day, zone)

    timeline_data = await TimelineService.get_timeline(
        session=db,
        camera_serial=camera_id,
        start_time=day_start,
        end_time=day_end,
    )

    base, _, _ = _lan_base_url(request)
    seg_token = default_media_token_service.generate_token(
        user_id=user.id,
        camera_serial=camera_id,
        stream="playback",
        ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
    )

    clips: list[MobileRecordingClip] = []
    for s in timeline_data.segments:
        trigger = "event" if s.is_protected else "continuous"
        rel_url = f"/api/v1/playback/segment/{s.id}"
        clips.append(
            MobileRecordingClip(
                id=s.id,
                start_time=s.start_time,
                end_time=s.end_time,
                duration_seconds=s.duration_seconds,
                size_bytes=s.file_size_bytes,
                trigger=trigger,
                stream_url=rel_url,
                signed_stream_url=f"{base}{rel_url}?token={seg_token}",
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
    request: Request,
    user: UserDep,
    db: DbDep,
) -> MobileStatusResponse:
    """Consolidated recorder status and camera telemetry for mobile dashboard."""
    runtime = getattr(request.app.state, "runtime", None)
    default_path = (
        Path(runtime.settings.data_dir) / "recordings"
        if runtime is not None and getattr(runtime, "settings", None) is not None
        else Path("/var/lib/vizenlink-nvr/recordings")
    )
    storage_cfg = await get_storage_config(session=db, default_path=default_path)

    recorder = getattr(request.app.state, "recorder", None)
    mediamtx_ok = bool(recorder.status().get("mediamtx_running", False)) if recorder is not None else True

    health = await RecorderHealthService.get_recorder_status(
        db,
        media_status=mediamtx_ok,
        storage_status=storage_cfg.health_state,
    )
    system_status = (
        health.status.value if hasattr(health.status, "value") else str(health.status)
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
        .order_by(Camera.serial)
    )
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        stmt = stmt.where(Camera.serial.in_(allowed))

    cameras = (await db.execute(stmt)).scalars().all()
    tz_name = await read_site_timezone(db)
    live_state = await check_camera_gaps(db) if recorder is not None else None

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
        if live_state is not None:
            cam_health = live_state.get(cam.serial)
            is_rec = bool(
                is_online
                and mediamtx_ok
                and storage_cfg.health_state == StorageHealthState.OK
                and cam_health is not None
                and cam_health.recording_state == RecordingState.RECORDING
            )
        else:
            is_rec = bool(is_online and await should_record_now(db, cam.serial, tz_name=tz_name))

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
    request: Request,
    db: DbDep,
) -> dict[str, Any]:
    """Onboard a camera from mobile (Owner only).

    Same path as the web UI's ``POST /cameras/onboard``: signs in to the camera,
    reads its serial/streams, pins its TLS certificate and stores the credentials
    in the vault, so the camera actually records. Errors map to the same HTTP codes.
    """
    camera = await onboard_discovered_camera(payload, user, request, db)
    return {"serial": camera.serial, "name": camera.name, "created": True}


@mobile_router.delete(
    "/cameras/{camera_id}",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def remove_mobile_camera(
    camera_id: str,
    user: OwnerDep,
    db: DbDep,
    keep_recordings: bool = True,
) -> dict[str, Any]:
    """Remove a camera from mobile (Owner only); keeps its recordings by default."""
    result = await remove_camera_endpoint(camera_id, user, db, keep_recordings=keep_recordings)
    return {"serial": camera_id, "deleted": True, "recordings_deleted": result["recordings_deleted"]}


# ---------------------------------------------------------------------------
# Snapshot of a recorded moment (mobile Playback "Snapshot")
# ---------------------------------------------------------------------------


class MobileSnapshotAtRequest(BaseModel):
    """The recorded moment to grab a still from."""

    at: datetime
    title: str | None = None


def _extract_frame_jpeg(segment_path: Path, offset_seconds: float) -> bytes | None:
    """One JPEG frame at ``offset_seconds`` into a recorded segment, via ffmpeg.

    Done on the NVR because a phone's video player cannot reliably hand back the
    frame it is showing (hardware-decoded textures read back as black on Android).
    Returns None when ffmpeg is missing or the frame cannot be decoded.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None or not segment_path.is_file():
        return None
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(offset_seconds, 0.0):.3f}",
        "-i",
        str(segment_path),
        "-frames:v",
        "1",
        "-f",
        "image2",
        "-vcodec",
        "mjpeg",
        "-q:v",
        "3",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=20, check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ffmpeg frame grab failed for %s: %s", segment_path, exc)
        return None
    if proc.returncode != 0 or not proc.stdout.startswith(b"\xff\xd8\xff"):
        return None
    return proc.stdout


@mobile_router.post(
    "/cameras/{camera_id}/snapshot-at",
    response_model=GalleryItemModel,
    status_code=status.HTTP_201_CREATED,
)
async def snapshot_recorded_moment(
    camera_id: str,
    payload: MobileSnapshotAtRequest,
    request: Request,
    user: UserDep,
    db: DbDep,
) -> GalleryItemModel:
    """Save a still of the recording at ``at`` into the NVR gallery (same as a web snapshot)."""
    verify_camera_access(camera_id, user)
    at = payload.at if payload.at.tzinfo is not None else payload.at.replace(tzinfo=UTC)

    stmt = (
        select(Segment)
        .where(
            Segment.camera_serial == camera_id,
            Segment.start_time <= at,
            Segment.end_time > at,
        )
        # Prefer the main (full-resolution) stream when both were recorded.
        .order_by(Segment.stream_type.asc())
    )
    seg = (await db.execute(stmt)).scalars().first()
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nothing was recorded at that moment.",
        )

    path = Path(seg.file_path)
    if not path.is_absolute():
        path = (await _resolve_storage_root(request, db)) / path
    offset = (at - seg.start_time).total_seconds()
    jpeg = await asyncio.to_thread(_extract_frame_jpeg, path, offset)
    if jpeg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not take a picture from this recording (the VMS needs ffmpeg installed).",
        )

    return await save_snapshot(
        SaveSnapshotRequest(
            camera_serial=camera_id,
            image_base64=base64.b64encode(jpeg).decode("ascii"),
            title=payload.title,
            captured_at=at,
        ),
        request,
        user,
        db,
    )


# ---------------------------------------------------------------------------
# Exact-range clip (mobile "Save to VMS" and the AI assistant's save_clip)
# ---------------------------------------------------------------------------

MAX_CLIP_SECONDS = 600


class MobileClipRequest(BaseModel):
    """The exact recorded range to cut into a gallery clip."""

    start: datetime
    end: datetime
    title: str | None = Field(default=None, max_length=200)


def _cut_clip(
    segment_paths: list[Path], offset_seconds: float, duration_seconds: float, output: Path
) -> bool:
    """Cut exactly ``duration_seconds`` starting ``offset_seconds`` into the joined
    segments, re-encoding so the clip starts on the requested second (a stream copy
    could only start at a keyframe). Returns False when ffmpeg is missing or fails.

    ``/playback/export`` joins whole recorded files instead, so asking it for
    9:01-9:02 returns the full 9:00-9:05 file; this is the exact version.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output.with_name(f"{output.stem}.tmp_{uuid.uuid4().hex[:8]}{output.suffix}")
    with tempfile.TemporaryDirectory() as tmp:
        concat_list = Path(tmp) / "segments.txt"
        concat_list.write_text(
            "".join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in segment_paths),
            encoding="utf-8",
        )
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-ss",
            f"{max(offset_seconds, 0.0):.3f}",
            "-t",
            f"{duration_seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-y",
            str(tmp_out),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=300, check=False)  # noqa: S603
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ffmpeg clip cut failed: %s", exc)
            tmp_out.unlink(missing_ok=True)
            return False
    if proc.returncode != 0 or not tmp_out.exists() or tmp_out.stat().st_size == 0:
        logger.warning("ffmpeg clip cut failed (%s): %s", proc.returncode, proc.stderr[-500:])
        tmp_out.unlink(missing_ok=True)
        return False
    tmp_out.replace(output)
    return True


@mobile_router.post(
    "/cameras/{camera_id}/clip",
    response_model=GalleryItemModel,
    status_code=status.HTTP_201_CREATED,
)
async def save_exact_clip(
    camera_id: str,
    payload: MobileClipRequest,
    request: Request,
    user: UserDep,
    db: DbDep,
) -> GalleryItemModel:
    """Cut exactly ``start``..``end`` (max 10 minutes) into the NVR gallery."""
    verify_camera_access(camera_id, user)
    start = payload.start if payload.start.tzinfo else payload.start.replace(tzinfo=UTC)
    end = payload.end if payload.end.tzinfo else payload.end.replace(tzinfo=UTC)
    if end <= start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The clip must end after it starts.")
    if (end - start).total_seconds() > MAX_CLIP_SECONDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A clip can be at most 10 minutes long.")

    stmt = (
        select(Segment)
        .where(
            Segment.camera_serial == camera_id,
            Segment.end_time > start,
            Segment.start_time < end,
        )
        .order_by(Segment.start_time.asc())
    )
    segments = list((await db.execute(stmt)).scalars().all())
    # One continuous track: the main stream when it was recorded.
    if any(s.stream_type == "main" for s in segments):
        segments = [s for s in segments if s.stream_type == "main"]
    if not segments:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing was recorded in that time range.")

    storage_root = await _resolve_storage_root(request, db)
    paths: list[Path] = []
    for seg in segments:
        path = Path(seg.file_path)
        if not path.is_absolute():
            path = storage_root / path
        if path.is_file():
            paths.append(path)
    if not paths:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The recording files for that time are missing.")

    # The clip can't start before the first recorded second or end after the last.
    actual_start = max(start, segments[0].start_time)
    actual_end = min(end, segments[-1].end_time)
    offset = (actual_start - segments[0].start_time).total_seconds()
    duration = (actual_end - actual_start).total_seconds()

    filename = f"clip_{camera_id}_{actual_start.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.mp4"
    rel_path = GalleryService.generate_relative_path(
        camera_serial=camera_id,
        item_type="export_clip",
        captured_at=actual_start,
        filename=filename,
    )
    abs_output = storage_root / rel_path
    ok = await asyncio.to_thread(_cut_clip, paths, offset, duration, abs_output)
    if not ok:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not cut the clip (the VMS needs ffmpeg installed).",
        )

    title = payload.title or f"Clip {camera_id} {actual_start.isoformat()}"
    item = await GalleryService.create_item(
        session=db,
        camera_serial=camera_id,
        item_type="export_clip",
        title=title,
        file_path=rel_path,
        file_size_bytes=abs_output.stat().st_size,
        duration_seconds=duration,
        captured_at=actual_start,
        user_id=user.id,
        commit=True,
    )
    await AuditService.record_event(
        session=db,
        action="gallery.export_clip",
        resource_type="gallery_item",
        resource_id=str(item.id),
        actor_id=user.id,
        actor_username=user.username,
        details={
            "camera_serial": camera_id,
            "start_time": actual_start.isoformat(),
            "end_time": actual_end.isoformat(),
            "exact": True,
            "file_path": rel_path,
        },
        commit=True,
    )
    return GalleryItemModel(
        id=item.id,
        camera_serial=item.camera_serial,
        item_type=item.item_type,
        title=item.title,
        file_path=item.file_path,
        file_size_bytes=item.file_size_bytes,
        duration_seconds=item.duration_seconds,
        captured_at=item.captured_at,
        created_at=item.created_at,
        user_id=item.user_id,
    )
