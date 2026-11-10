"""Events REST API endpoints (EVT-02, EVT-03, REC-12, HLTH-09)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import Camera, Event, EventSubscription, StorageSettings
from vizenlink_nvr.events.protection import SegmentProtectionService
from vizenlink_nvr.events.severity import Severity, event_types_for, severity_for
from vizenlink_nvr.events.snapshots import EventSnapshotManager
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.timeutil import utc_now

events_router = APIRouter(prefix="/events", tags=["events"])


class EventItemResponse(BaseModel):
    """Single event item schema."""

    id: int
    camera_serial: str
    event_type: str
    source: str
    start_time: datetime
    end_time: datetime | None = None
    snapshot_path: str | None = None
    is_locked: bool
    clock_sync_state: str
    raw_topic: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime
    # Phase 10 review workflow (additive fields).
    severity: str = "info"
    review_state: str = "new"
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class EventListResponse(BaseModel):
    """Paginated list of events."""

    items: list[EventItemResponse]
    total: int
    limit: int
    offset: int


class SubscriptionStatusItem(BaseModel):
    """Camera event subscription state schema."""

    camera_serial: str
    state: str
    subscription_url: str | None = None
    last_event_at: datetime | None = None
    last_renewed_at: datetime | None = None
    error_reason: str | None = None
    clock_drift_seconds: float | None = None
    updated_at: datetime


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


def _apply_review_filters(
    stmt: Any,
    count_stmt: Any,
    severity: str | None,
    review_state: str | None,
    q: str | None,
) -> tuple[Any, Any]:
    conds: list[Any] = []
    if severity == "info":
        conds.append(Event.event_type.not_in(event_types_for("critical") + event_types_for("warning")))
    elif severity:
        conds.append(Event.event_type.in_(event_types_for(severity)))  # type: ignore[arg-type]
    if review_state == "open":
        conds.append(Event.review_state.in_(["new", "acknowledged"]))
    elif review_state:
        conds.append(Event.review_state == review_state)
    if q:
        like = f"%{q.strip().lower()}%"
        cam_match = select(Camera.serial).where(
            or_(func.lower(Camera.name).like(like), func.lower(Camera.location).like(like))
        )
        conds.append(
            or_(
                func.lower(Event.event_type).like(like.replace(" ", "_")),
                func.lower(Event.camera_serial).like(like),
                Event.camera_serial.in_(cam_match),
            )
        )
    for c in conds:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)
    return stmt, count_stmt


def _to_event_response(row: Event) -> EventItemResponse:
    details_dict: dict[str, Any] | None = None
    if row.details_json:
        try:
            details_dict = json.loads(row.details_json)
        except Exception:
            details_dict = None

    return EventItemResponse(
        id=row.id,
        camera_serial=row.camera_serial,
        event_type=row.event_type,
        source=row.source,
        start_time=row.start_time,
        end_time=row.end_time,
        snapshot_path=row.snapshot_path,
        is_locked=row.is_locked,
        clock_sync_state=row.clock_sync_state,
        raw_topic=row.raw_topic,
        details=details_dict,
        created_at=row.created_at,
        severity=severity_for(row.event_type),
        review_state=row.review_state or "new",
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
    )


@events_router.get("", response_model=EventListResponse)
async def query_events(
    user: CurrentUser,
    db: DbSession,
    camera_serial: str | None = None,
    event_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    is_locked: bool | None = None,
    severity: Severity | None = None,
    review_state: str | None = Query(None, pattern="^(new|acknowledged|resolved|open)$"),
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EventListResponse:
    """Retrieve event history with filtering and RBAC camera scoping.

    Hidden events are never listed. review_state=open means new or acknowledged.
    """
    stmt = select(Event).where(Event.hidden_at.is_(None)).order_by(Event.start_time.desc())
    count_stmt = select(func.count(Event.id)).where(Event.hidden_at.is_(None))
    stmt, count_stmt = _apply_review_filters(stmt, count_stmt, severity, review_state, q)

    # RBAC viewer camera scoping (AUTH-05)
    if user.role not in ("owner", "operator"):
        allowed_cameras = {p.camera_serial for p in user.permissions}
        if camera_serial:
            if camera_serial not in allowed_cameras:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied to camera '{camera_serial}'",
                )
            stmt = stmt.where(Event.camera_serial == camera_serial)
            count_stmt = count_stmt.where(Event.camera_serial == camera_serial)
        else:
            stmt = stmt.where(Event.camera_serial.in_(allowed_cameras))
            count_stmt = count_stmt.where(Event.camera_serial.in_(allowed_cameras))
    elif camera_serial:
        stmt = stmt.where(Event.camera_serial == camera_serial)
        count_stmt = count_stmt.where(Event.camera_serial == camera_serial)

    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
        count_stmt = count_stmt.where(Event.event_type == event_type)

    if start_time:
        stmt = stmt.where(Event.start_time >= start_time)
        count_stmt = count_stmt.where(Event.start_time >= start_time)

    if end_time:
        stmt = stmt.where(Event.start_time <= end_time)
        count_stmt = count_stmt.where(Event.start_time <= end_time)

    if is_locked is not None:
        stmt = stmt.where(Event.is_locked == is_locked)
        count_stmt = count_stmt.where(Event.is_locked == is_locked)

    total_count = (await db.execute(count_stmt)).scalar_one()
    paged_stmt = stmt.limit(limit).offset(offset)
    res = await db.execute(paged_stmt)
    rows = list(res.scalars().all())

    return EventListResponse(
        items=[_to_event_response(r) for r in rows],
        total=total_count,
        limit=limit,
        offset=offset,
    )


@events_router.get("/subscriptions/status", response_model=list[SubscriptionStatusItem])
async def get_subscription_statuses(
    user: CurrentUser,
    db: DbSession,
) -> list[SubscriptionStatusItem]:
    """Retrieve event subscription states across cameras."""
    stmt = select(EventSubscription)
    if user.role not in ("owner", "operator"):
        allowed_cameras = {p.camera_serial for p in user.permissions}
        stmt = stmt.where(EventSubscription.camera_serial.in_(allowed_cameras))

    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    return [
        SubscriptionStatusItem(
            camera_serial=r.camera_serial,
            state=r.state,
            subscription_url=r.subscription_url,
            last_event_at=r.last_event_at,
            last_renewed_at=r.last_renewed_at,
            error_reason=r.error_reason,
            clock_drift_seconds=r.clock_drift_seconds,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@events_router.get("/{event_id}", response_model=EventItemResponse)
async def get_event_detail(
    event_id: int,
    user: CurrentUser,
    db: DbSession,
) -> EventItemResponse:
    """Retrieve event detail by ID (removed/hidden alerts are not found, same as the lists)."""
    event = await db.get(Event, event_id)
    if event is None or event.hidden_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")

    if user.role not in ("owner", "operator"):
        allowed_cameras = {p.camera_serial for p in user.permissions}
        if event.camera_serial not in allowed_cameras:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{event.camera_serial}'",
            )

    return _to_event_response(event)


@events_router.get("/{event_id}/snapshot")
async def get_event_snapshot(
    event_id: int,
    user: CurrentUser,
    request: Request,
    db: DbSession,
) -> Response:
    """Serve the trigger snapshot JPEG for the event."""
    event = await db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")

    if user.role not in ("owner", "operator"):
        allowed_cameras = {p.camera_serial for p in user.permissions}
        if event.camera_serial not in allowed_cameras:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{event.camera_serial}'",
            )

    if not event.snapshot_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot stored for this event")

    storage_root = await _resolve_storage_root(request, db)
    manager = EventSnapshotManager(storage_root)
    file_path = manager.resolve_snapshot_file(event.snapshot_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot file not found on disk")

    return FileResponse(file_path, media_type="image/jpeg")


@events_router.post("/{event_id}/lock", response_model=EventItemResponse)
async def lock_event(
    event_id: int,
    user: RequireOperator,
    db: DbSession,
) -> EventItemResponse:
    """Lock an event and protect underlying video footage from retention pruning."""
    event = await db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")

    event.is_locked = True
    await db.commit()

    # Protect overlapping segments
    await SegmentProtectionService.protect_event_segments(
        session=db,
        camera_serial=event.camera_serial,
        event_id=event.id,
        start_time=event.start_time,
        end_time=event.end_time,
    )

    await AuditService.record_event(
        session=db,
        action="event.lock",
        resource_type="event",
        resource_id=str(event.id),
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )

    await db.refresh(event)
    return _to_event_response(event)


@events_router.post("/{event_id}/unlock", response_model=EventItemResponse)
async def unlock_event(
    event_id: int,
    user: RequireOperator,
    db: DbSession,
) -> EventItemResponse:
    """Unlock an event, releasing protected video footage."""
    event = await db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")

    event.is_locked = False
    await db.commit()

    # Release segment protection
    await SegmentProtectionService.release_event_segments(session=db, event_id=event.id)

    await AuditService.record_event(
        session=db,
        action="event.unlock",
        resource_type="event",
        resource_id=str(event.id),
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )

    await db.refresh(event)
    return _to_event_response(event)



class ReviewAllRequest(BaseModel):
    """Acknowledge every open alert matching the same filters as the list."""

    camera_serial: str | None = None
    event_type: str | None = None
    severity: Severity | None = None


async def _load_accessible_event(event_id: int, user: Any, db: AsyncSession) -> Event:
    event = await db.get(Event, event_id)
    if event is None or event.hidden_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        if event.camera_serial not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this event")
    return event


_REVIEW_ACTIONS = {"acknowledged": "event.acknowledge", "resolved": "event.resolve", "new": "event.reopen"}


async def _set_review(event_id: int, state: str, user: Any, db: AsyncSession) -> EventItemResponse:
    event = await _load_accessible_event(event_id, user, db)
    event.review_state = state
    event.reviewed_at = utc_now()
    event.reviewed_by = user.username
    await db.commit()
    await AuditService.record_event(
        session=db,
        action=_REVIEW_ACTIONS[state],
        resource_type="event",
        resource_id=str(event.id),
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )
    await db.refresh(event)
    return _to_event_response(event)


@events_router.post("/acknowledge-all", response_model=dict[str, int])
async def acknowledge_all_events(
    payload: ReviewAllRequest, user: CurrentUser, db: DbSession
) -> dict[str, int]:
    """Acknowledge all new alerts the user can see (optionally filtered)."""
    stmt = select(Event).where(Event.hidden_at.is_(None), Event.review_state == "new")
    if user.role not in ("owner", "operator"):
        stmt = stmt.where(Event.camera_serial.in_({p.camera_serial for p in user.permissions}))
    if payload.camera_serial:
        stmt = stmt.where(Event.camera_serial == payload.camera_serial)
    if payload.event_type:
        stmt = stmt.where(Event.event_type == payload.event_type)
    stmt, _ = _apply_review_filters(
        stmt, select(func.count(Event.id)), payload.severity, None, None
    )
    rows = list((await db.execute(stmt)).scalars().all())
    now = utc_now()
    for ev in rows:
        ev.review_state = "acknowledged"
        ev.reviewed_at = now
        ev.reviewed_by = user.username
    await db.commit()
    await AuditService.record_event(
        session=db,
        action="event.acknowledge_all",
        resource_type="event",
        resource_id=f"{len(rows)} events",
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )
    return {"acknowledged": len(rows)}


@events_router.post("/{event_id}/acknowledge", response_model=EventItemResponse)
async def acknowledge_event(event_id: int, user: CurrentUser, db: DbSession) -> EventItemResponse:
    """Mark an alert as seen (any user with access to the camera)."""
    return await _set_review(event_id, "acknowledged", user, db)


@events_router.post("/{event_id}/resolve", response_model=EventItemResponse)
async def resolve_event(event_id: int, user: CurrentUser, db: DbSession) -> EventItemResponse:
    """Mark an alert as handled."""
    return await _set_review(event_id, "resolved", user, db)


@events_router.post("/{event_id}/reopen", response_model=EventItemResponse)
async def reopen_event(event_id: int, user: CurrentUser, db: DbSession) -> EventItemResponse:
    """Undo acknowledge/resolve."""
    return await _set_review(event_id, "new", user, db)


@events_router.post("/{event_id}/hide", response_model=dict[str, bool])
async def hide_event(event_id: int, user: RequireOperator, db: DbSession) -> dict[str, bool]:
    """Remove an alert from lists (old VMS "Delete").

    The event row is kept so footage protection and the audit trail stay intact.
    Locked events cannot be hidden.
    """
    event = await _load_accessible_event(event_id, user, db)
    if event.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This alert is locked to protect its footage. Unlock it before removing it.",
        )
    event.hidden_at = utc_now()
    await db.commit()
    await AuditService.record_event(
        session=db,
        action="event.hide",
        resource_type="event",
        resource_id=str(event.id),
        actor_id=user.id,
        actor_username=user.username,
        commit=True,
    )
    return {"hidden": True}
