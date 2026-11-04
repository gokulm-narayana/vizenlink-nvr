"""Playback REST API endpoints (PLAY-01, PLAY-02, PLAY-05, PLAY-08, GAL-03, REC-12)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import Segment
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.timeline import TimelineService

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


def _verify_camera_access(user: CurrentUser, camera_serial: str) -> None:
    """Ensure viewer user has access to requested camera serial (AUTH-05)."""
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        if camera_serial not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{camera_serial}'",
            )


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
