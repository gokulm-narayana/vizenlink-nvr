"""Playback REST API endpoints (PLAY-01, PLAY-02, PLAY-05, PLAY-08, GAL-03, REC-12)."""

from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import Segment, StorageSettings
from vizenlink_nvr.media.clip_exporter import ClipExporter
from vizenlink_nvr.media.playback_streamer import RangeFileResponse
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.gallery import GalleryService
from vizenlink_nvr.services.timeline import TimelineService
from vizenlink_nvr.timeutil import utc_now

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
    user: CurrentUser,
    db: DbSession,
) -> Response:
    """Stream fMP4 video segment with HTTP 206 Byte-Range seeking support (PLAY-03, PLAY-04)."""
    seg = await db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
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
    year: int = Query(..., ge=2020, le=2050),
    month: int = Query(..., ge=1, le=12),
    user: CurrentUser = None,
    db: DbSession = None,
) -> CalendarDaysResponse:
    """Retrieve days containing recorded video for a given camera and month."""
    _verify_camera_access(user, camera_serial)

    days = await TimelineService.get_recorded_days(
        session=db,
        camera_serial=camera_serial,
        year=year,
        month=month,
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
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    event_type: str | None = None,
    user: CurrentUser = None,
    db: DbSession = None,
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

    seg.is_protected = True
    seg.protection_reason = f"evidence_lock:user_{user.id}"
    await db.commit()

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

    seg.is_protected = False
    seg.protection_reason = None
    await db.commit()

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
