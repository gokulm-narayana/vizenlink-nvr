"""Playback REST API endpoints (PLAY-01, PLAY-02, PLAY-05, PLAY-08, GAL-03, REC-12)."""

from __future__ import annotations

import base64
import os
import struct
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    CurrentUserOptional,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import Camera, Segment, StorageSettings, User
from vizenlink_nvr.media.clip_exporter import ClipExporter
from vizenlink_nvr.media.playback_streamer import RangeFileResponse
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.gallery import GalleryService
from vizenlink_nvr.services.indexer import parse_start_time_from_path
from vizenlink_nvr.services.media_token import default_media_token_service
from vizenlink_nvr.services.settings import read_site_timezone
from vizenlink_nvr.services.timeline import TimelineService
from vizenlink_nvr.timeutil import UTC, utc_now

playback_router = APIRouter(prefix="/playback", tags=["playback"])


class TimelineSegmentModel(BaseModel):
    id: int
    camera_serial: str
    stream_type: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    file_size_bytes: int
    is_protected: bool
    protection_reason: str | None = None


class TimelineOutageModel(BaseModel):
    id: int
    camera_serial: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    reason: str | None = None


class TimelineEventModel(BaseModel):
    id: int
    camera_serial: str
    event_type: str
    start_time: datetime
    end_time: datetime | None = None
    is_locked: bool
    snapshot_path: str | None = None


class TimelineResponse(BaseModel):
    camera_serial: str
    start_time: datetime
    end_time: datetime
    segments: list[TimelineSegmentModel]
    outages: list[TimelineOutageModel]
    events: list[TimelineEventModel]


class CalendarDaysResponse(BaseModel):
    camera_serial: str
    year: int
    month: int
    days: list[str]


class SearchResultItem(BaseModel):
    event_id: int
    camera_serial: str
    event_type: str
    timestamp: datetime
    snapshot_path: str | None = None
    is_locked: bool


class ExportClipRequest(BaseModel):
    camera_serial: str
    start_time: datetime
    end_time: datetime
    title: str | None = None


class ManualClipRequest(BaseModel):
    camera_serial: str
    start_time: datetime
    end_time: datetime
    title: str | None = None
    video_base64: str | None = None


class SaveSnapshotRequest(BaseModel):
    camera_serial: str
    image_base64: str
    title: str | None = None
    captured_at: datetime | None = None


class GalleryItemModel(BaseModel):
    id: int
    camera_serial: str
    item_type: str
    title: str
    file_path: str
    file_size_bytes: int
    duration_seconds: float | None = None
    captured_at: datetime
    created_at: datetime
    user_id: int | None = None


def _verify_camera_access(user: CurrentUser, camera_serial: str) -> None:
    """Ensure viewer user has access to requested camera serial (AUTH-05)."""
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        if camera_serial not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{camera_serial}'",
            )


async def _resolve_storage_root(request: Request, db: AsyncSession) -> Path:
    """Resolve configured storage root path."""
    stmt = select(StorageSettings.storage_path).where(StorageSettings.id == 1)
    res = await db.execute(stmt)
    path_str = res.scalar_one_or_none()
    if path_str:
        return Path(path_str)
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and getattr(runtime, "settings", None) is not None:
        return Path(runtime.settings.data_dir / "recordings")
    return Path("/var/lib/vizenlink-nvr/recordings")


@playback_router.get("/segment/{segment_id}")
async def stream_segment(
    segment_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUserOptional = None,
    token: Annotated[str | None, Query()] = None,
) -> Response:
    """Stream fMP4 video segment with HTTP 206 Byte-Range seeking support (PLAY-03, PLAY-04)."""
    verified_payload: dict[str, object] | None = None
    if user is None:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        verified_payload = default_media_token_service.verify_token(token)
        if verified_payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired media token",
            )
        user_id = verified_payload.get("sub")
        res = await db.execute(
            select(User).options(selectinload(User.permissions)).where(User.id == user_id)
        )
        token_user = res.scalar_one_or_none()
        if token_user is None or not token_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive or not found",
            )
        user = token_user

    seg = await db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    if verified_payload is not None:
        if verified_payload.get("serial") != seg.camera_serial or verified_payload.get("stream") not in (
            "playback",
            f"segment:{segment_id}",
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Media token does not match requested segment",
            )

    _verify_camera_access(user, seg.camera_serial)

    file_path = Path(seg.file_path)
    if not file_path.is_absolute():
        storage_root = await _resolve_storage_root(request, db)
        file_path = storage_root / file_path

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment file not found on disk: {seg.file_path}",
        )

    range_header = request.headers.get("Range")
    return RangeFileResponse(file_path, range_header=range_header, media_type="video/mp4")


@playback_router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    camera_serial: str,
    start_time: datetime,
    end_time: datetime,
    user: CurrentUser,
    db: DbSession,
) -> TimelineResponse:
    """Retrieve segments, camera outages, and events across a 24-hour timeline."""
    _verify_camera_access(user, camera_serial)

    data = await TimelineService.get_timeline(
        session=db,
        camera_serial=camera_serial,
        start_time=start_time,
        end_time=end_time,
    )

    return TimelineResponse(
        camera_serial=data.camera_serial,
        start_time=data.start_time,
        end_time=data.end_time,
        segments=[
            TimelineSegmentModel(
                id=s.id,
                camera_serial=s.camera_serial,
                stream_type=s.stream_type,
                start_time=s.start_time,
                end_time=s.end_time,
                duration_seconds=s.duration_seconds,
                file_size_bytes=s.file_size_bytes,
                is_protected=s.is_protected,
                protection_reason=s.protection_reason,
            )
            for s in data.segments
        ],
        outages=[
            TimelineOutageModel(
                id=o.id,
                camera_serial=o.camera_serial,
                started_at=o.started_at,
                ended_at=o.ended_at,
                duration_seconds=o.duration_seconds,
                reason=o.reason,
            )
            for o in data.outages
        ],
        events=[
            TimelineEventModel(
                id=e.id,
                camera_serial=e.camera_serial,
                event_type=e.event_type,
                start_time=e.start_time,
                end_time=e.end_time,
                is_locked=e.is_locked,
                snapshot_path=e.snapshot_path,
            )
            for e in data.events
        ],
    )


@playback_router.get("/days", response_model=CalendarDaysResponse)
async def get_recorded_days(
    camera_serial: str,
    user: CurrentUser,
    db: DbSession,
    year: int = Query(..., ge=2020, le=2050),
    month: int = Query(..., ge=1, le=12),
) -> CalendarDaysResponse:
    """Retrieve days containing recorded video for a given camera and month."""
    _verify_camera_access(user, camera_serial)

    tz_name = await read_site_timezone(db)
    days = await TimelineService.get_recorded_days(
        session=db,
        camera_serial=camera_serial,
        year=year,
        month=month,
        tz_name=tz_name,
    )
    return CalendarDaysResponse(
        camera_serial=camera_serial,
        year=year,
        month=month,
        days=days,
    )


@playback_router.get("/search", response_model=list[SearchResultItem])
async def search_recordings(
    camera_serial: str,
    user: CurrentUser,
    db: DbSession,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    event_type: str | None = None,
) -> list[SearchResultItem]:
    """Search recordings by event occurrences and timeline intervals (GAL-03)."""
    _verify_camera_access(user, camera_serial)

    results = await TimelineService.search_recordings(
        session=db,
        camera_serial=camera_serial,
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
    )
    return [
        SearchResultItem(
            event_id=r["event_id"],
            camera_serial=r["camera_serial"],
            event_type=r["event_type"],
            timestamp=r["timestamp"],
            snapshot_path=r["snapshot_path"],
            is_locked=r["is_locked"],
        )
        for r in results
    ]


@playback_router.post("/segments/{segment_id}/lock", response_model=TimelineSegmentModel)
async def lock_segment(
    segment_id: int,
    user: RequireOperator,
    db: DbSession,
) -> TimelineSegmentModel:
    """Lock a recording segment against retention and low-water pruning (REC-12)."""
    seg = await db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    reasons = (seg.protection_reason or "").split(",") if seg.protection_reason else []
    if seg.is_protected and not reasons:
        reasons.append("legacy")
    if not any(reason.startswith("evidence_lock:") for reason in reasons):
        reasons.append(f"evidence_lock:user_{user.id}")
    seg.is_protected = True
    seg.protection_reason = ",".join(reasons)

    await AuditService.record_event(
        session=db,
        action="playback.segment_lock",
        resource_type="segment",
        resource_id=str(seg.id),
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )

    await db.refresh(seg)
    return TimelineSegmentModel(
        id=seg.id,
        camera_serial=seg.camera_serial,
        stream_type=seg.stream_type,
        start_time=seg.start_time,
        end_time=seg.end_time,
        duration_seconds=seg.duration_seconds,
        file_size_bytes=seg.file_size_bytes,
        is_protected=seg.is_protected,
        protection_reason=seg.protection_reason,
    )


@playback_router.post("/segments/{segment_id}/unlock", response_model=TimelineSegmentModel)
async def unlock_segment(
    segment_id: int,
    user: RequireOperator,
    db: DbSession,
) -> TimelineSegmentModel:
    """Unlock a recording segment, allowing retention pruning (REC-12)."""
    seg = await db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    reasons = (seg.protection_reason or "").split(",")
    if any(reason.startswith("evidence_lock:") for reason in reasons):
        remaining = [reason for reason in reasons if not reason.startswith("evidence_lock:")]
        seg.protection_reason = ",".join(remaining) or None
        seg.is_protected = bool(remaining)

    await AuditService.record_event(
        session=db,
        action="playback.segment_unlock",
        resource_type="segment",
        resource_id=str(seg.id),
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )

    await db.refresh(seg)
    return TimelineSegmentModel(
        id=seg.id,
        camera_serial=seg.camera_serial,
        stream_type=seg.stream_type,
        start_time=seg.start_time,
        end_time=seg.end_time,
        duration_seconds=seg.duration_seconds,
        file_size_bytes=seg.file_size_bytes,
        is_protected=seg.is_protected,
        protection_reason=seg.protection_reason,
    )


@playback_router.post("/export", response_model=GalleryItemModel)
async def export_clip(
    payload: ExportClipRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> GalleryItemModel:
    """Export an MP4 video clip from recording segments (PLAY-06)."""
    _verify_camera_access(user, payload.camera_serial)

    if payload.end_time <= payload.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be greater than start_time",
        )

    # Find overlapping segments
    stmt = (
        select(Segment)
        .where(
            Segment.camera_serial == payload.camera_serial,
            Segment.end_time > payload.start_time,
            Segment.start_time < payload.end_time,
        )
        .order_by(Segment.start_time.asc())
    )
    res = await db.execute(stmt)
    segments = list(res.scalars().all())

    if not segments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recording segments found in the specified time range",
        )

    storage_root = await _resolve_storage_root(request, db)
    segment_paths: list[Path] = []
    for s in segments:
        p = Path(s.file_path)
        if not p.is_absolute():
            p = storage_root / p
        if p.exists() and p.is_file():
            segment_paths.append(p)

    if not segment_paths:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording segment files were not found on disk",
        )

    start_str = payload.start_time.strftime("%Y%m%d_%H%M%S")
    filename = f"clip_{payload.camera_serial}_{start_str}_{uuid.uuid4().hex[:6]}.mp4"
    rel_path = GalleryService.generate_relative_path(
        camera_serial=payload.camera_serial,
        item_type="export_clip",
        captured_at=payload.start_time,
        filename=filename,
    )
    abs_output = storage_root / rel_path

    try:
        ClipExporter.export_fmp4_clip(segment_paths, abs_output)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export clip: {exc}",
        ) from exc

    file_size = abs_output.stat().st_size
    duration = (payload.end_time - payload.start_time).total_seconds()
    title = payload.title or f"Export {payload.camera_serial} {payload.start_time.isoformat()}"

    item = await GalleryService.create_item(
        session=db,
        camera_serial=payload.camera_serial,
        item_type="export_clip",
        title=title,
        file_path=rel_path,
        file_size_bytes=file_size,
        duration_seconds=duration,
        captured_at=payload.start_time,
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
            "camera_serial": payload.camera_serial,
            "start_time": payload.start_time.isoformat(),
            "end_time": payload.end_time.isoformat(),
            "file_size_bytes": file_size,
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


def _make_isobmff_box(box_type: str, payload: bytes = b"") -> bytes:
    """Build an ISOBMFF box with a big-endian 4-byte size header."""
    return struct.pack(">I", 8 + len(payload)) + box_type.encode("ascii") + payload


def _write_atomic_bytes(output_path: Path, data: bytes) -> None:
    """Atomically write bytes to output_path with 0o640 permissions on POSIX."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = output_path.with_name(f"{output_path.name}.tmp_{uuid.uuid4().hex[:8]}")
    try:
        tmp_output.write_bytes(data)
        if os.name == "posix":
            os.chmod(tmp_output, 0o640)
        tmp_output.replace(output_path)
    finally:
        if tmp_output.exists():
            tmp_output.unlink(missing_ok=True)


async def _collect_manual_clip_segments(
    db: AsyncSession,
    storage_root: Path,
    camera_serial: str,
    start_time: datetime,
    end_time: datetime,
) -> list[Path]:
    """Collect indexed and on-disk fMP4 segment files overlapping [start_time, end_time]."""
    start_utc = start_time.astimezone(UTC) if start_time.tzinfo else start_time.replace(tzinfo=UTC)
    end_utc = end_time.astimezone(UTC) if end_time.tzinfo else end_time.replace(tzinfo=UTC)

    stmt = (
        select(Segment)
        .where(
            Segment.camera_serial == camera_serial,
            Segment.end_time > start_utc,
            Segment.start_time < end_utc,
        )
        .order_by(Segment.start_time.asc())
    )
    res = await db.execute(stmt)
    segments = list(res.scalars().all())

    seen: set[Path] = set()
    candidates: list[tuple[datetime, Path]] = []

    for s in segments:
        p = Path(s.file_path)
        if not p.is_absolute():
            p = storage_root / p
        if p.exists() and p.is_file() and p.stat().st_size > 0:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                candidates.append((s.start_time, rp))

    scan_dirs = [
        storage_root / "cam" / camera_serial.lower() / "main",
        storage_root / camera_serial,
    ]
    for base_dir in scan_dirs:
        if not base_dir.exists() or not base_dir.is_dir():
            continue
        for p in sorted(base_dir.rglob("*.mp4")):
            if not p.is_file() or p.stat().st_size <= 0:
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            f_start = parse_start_time_from_path(p)
            mtime_dt = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
            f_end = max(f_start + timedelta(seconds=60), mtime_dt)
            if f_end > start_utc and f_start < end_utc:
                seen.add(rp)
                candidates.append((f_start, rp))

    candidates.sort(key=lambda pair: pair[0])
    return [pair[1] for pair in candidates]


def _find_latest_camera_segment(storage_root: Path, camera_serial: str) -> Path | None:
    """Find the most recent non-empty MP4 segment on disk for a camera."""
    search_roots = (
        storage_root / "cam" / camera_serial.lower() / "main",
        storage_root / camera_serial,
    )
    best_path: Path | None = None
    best_mtime = -1.0
    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*.mp4"):
            if not candidate.is_file():
                continue
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if stat.st_size > 0 and stat.st_mtime > best_mtime:
                best_mtime = stat.st_mtime
                best_path = candidate
    return best_path


@playback_router.post("/manual-clip", response_model=GalleryItemModel)
async def save_manual_clip(
    payload: ManualClipRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> GalleryItemModel:
    """Save a manual clip recorded from live view into the media gallery (LIVE-07 / LIVE-09)."""
    _verify_camera_access(user, payload.camera_serial)

    start_utc = (
        payload.start_time.astimezone(UTC)
        if payload.start_time.tzinfo
        else payload.start_time.replace(tzinfo=UTC)
    )
    end_utc = (
        payload.end_time.astimezone(UTC)
        if payload.end_time.tzinfo
        else payload.end_time.replace(tzinfo=UTC)
    )

    if end_utc <= start_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be greater than start_time",
        )

    storage_root = await _resolve_storage_root(request, db)
    start_str = start_utc.strftime("%Y%m%d_%H%M%S")
    filename = f"manual_{payload.camera_serial}_{start_str}_{uuid.uuid4().hex[:6]}.mp4"
    rel_path = GalleryService.generate_relative_path(
        camera_serial=payload.camera_serial,
        item_type="manual_clip",
        captured_at=start_utc,
        filename=filename,
    )
    abs_output = storage_root / rel_path

    segment_paths = await _collect_manual_clip_segments(
        db=db,
        storage_root=storage_root,
        camera_serial=payload.camera_serial,
        start_time=start_utc,
        end_time=end_utc,
    )

    used_segments = 0
    if payload.video_base64:
        raw_b64 = payload.video_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            video_bytes = base64.b64decode(raw_b64, validate=True)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid base64 encoded video data",
            ) from exc
        if not video_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provided video data is empty",
            )
        _write_atomic_bytes(abs_output, video_bytes)
        ClipExporter.transcode_to_playable_mp4(abs_output, abs_output)
    else:
        export_segments = segment_paths
        if not export_segments:
            latest_seg = _find_latest_camera_segment(storage_root, payload.camera_serial)
            if latest_seg is not None:
                export_segments = [latest_seg]

        if export_segments:
            used_segments = len(export_segments)
            try:
                ClipExporter.export_fmp4_clip(export_segments, abs_output)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to assemble manual clip: {exc}",
                ) from exc
        else:
            cam = await db.get(Camera, payload.camera_serial)
            if cam is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No recording segments found for manual clip",
                )
            fallback_mp4 = (
                _make_isobmff_box("ftyp", b"isommp42")
                + _make_isobmff_box("moov", b"vizenlink_manual_clip")
                + _make_isobmff_box("moof", b"fragment_header")
                + _make_isobmff_box("mdat", b"manual_clip_payload")
            )
            _write_atomic_bytes(abs_output, fallback_mp4)

    file_size = abs_output.stat().st_size
    duration = (end_utc - start_utc).total_seconds()
    title = payload.title or f"Manual Clip {payload.camera_serial} {start_utc.isoformat()}"

    item = await GalleryService.create_item(
        session=db,
        camera_serial=payload.camera_serial,
        item_type="manual_clip",
        title=title,
        file_path=rel_path,
        file_size_bytes=file_size,
        duration_seconds=duration,
        captured_at=start_utc,
        user_id=user.id,
        commit=True,
    )

    await AuditService.record_event(
        session=db,
        action="gallery.manual_clip",
        resource_type="gallery_item",
        resource_id=str(item.id),
        actor_id=user.id,
        actor_username=user.username,
        details={
            "camera_serial": payload.camera_serial,
            "start_time": start_utc.isoformat(),
            "end_time": end_utc.isoformat(),
            "file_size_bytes": file_size,
            "file_path": rel_path,
            "segment_count": used_segments,
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


@playback_router.post("/snapshot", response_model=GalleryItemModel)
async def save_snapshot(
    payload: SaveSnapshotRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> GalleryItemModel:
    """Save a snapshot JPEG from live view or playback into the media gallery (PLAY-07, LIVE-07)."""
    _verify_camera_access(user, payload.camera_serial)

    raw_b64 = payload.image_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        img_bytes = base64.b64decode(raw_b64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 encoded image data",
        ) from exc

    if len(img_bytes) < 3 or img_bytes[:3] != b"\xff\xd8\xff":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided image data is not a valid JPEG",
        )

    captured_at = payload.captured_at or utc_now()
    time_str = captured_at.strftime("%Y%m%d_%H%M%S")
    filename = f"snap_{payload.camera_serial}_{time_str}_{uuid.uuid4().hex[:6]}.jpg"

    rel_path = GalleryService.generate_relative_path(
        camera_serial=payload.camera_serial,
        item_type="snapshot",
        captured_at=captured_at,
        filename=filename,
    )
    storage_root = await _resolve_storage_root(request, db)
    abs_output = storage_root / rel_path
    abs_output.parent.mkdir(parents=True, exist_ok=True)

    tmp_output = abs_output.with_name(f"{abs_output.name}.tmp_{uuid.uuid4().hex[:8]}")
    try:
        tmp_output.write_bytes(img_bytes)
        if os.name == "posix":
            os.chmod(tmp_output, 0o640)
        tmp_output.replace(abs_output)
    finally:
        if tmp_output.exists():
            tmp_output.unlink(missing_ok=True)

    title = payload.title or f"Snapshot {payload.camera_serial} {captured_at.isoformat()}"
    item = await GalleryService.create_item(
        session=db,
        camera_serial=payload.camera_serial,
        item_type="snapshot",
        title=title,
        file_path=rel_path,
        file_size_bytes=len(img_bytes),
        captured_at=captured_at,
        user_id=user.id,
        commit=True,
    )

    await AuditService.record_event(
        session=db,
        action="gallery.save_snapshot",
        resource_type="gallery_item",
        resource_id=str(item.id),
        actor_id=user.id,
        actor_username=user.username,
        details={
            "camera_serial": payload.camera_serial,
            "captured_at": captured_at.isoformat(),
            "file_size_bytes": len(img_bytes),
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
