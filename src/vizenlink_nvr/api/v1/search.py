"""Search the recorder's index, scoped to the signed-in user's cameras."""

from datetime import datetime
from typing import Annotated, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, exists, func, literal, or_, select
from sqlalchemy.orm import InstrumentedAttribute

from vizenlink_nvr.api.dependencies import CurrentUser, DbSession, verify_camera_access
from vizenlink_nvr.db.models import Camera, Event, GalleryItem, Segment

search_router = APIRouter(prefix="/search", tags=["search"])


class SearchItem(BaseModel):
    id: int
    kind: str
    camera_serial: str
    camera_name: str
    location: str
    title: str
    timestamp: datetime
    end_time: datetime | None = None
    duration_seconds: float | None = None
    thumbnail_url: str | None = None
    href: str
    is_protected: bool = False


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    limit: int
    offset: int


@search_router.get("", response_model=SearchResponse)
async def search_index(
    user: CurrentUser,
    db: DbSession,
    kind: Literal["events", "recordings", "snapshots"] = "events",
    q: str = Query("", max_length=100),
    camera_serial: str | None = None,
    event_type: str | None = Query(None, max_length=64),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    camera_serials: Annotated[list[str] | None, Query()] = None,
) -> SearchResponse:
    """Find indexed events, active footage or snapshots; never scan video with a model."""
    if start_time and end_time:
        try:
            invalid = end_time <= start_time
        except TypeError as exc:
            raise HTTPException(422, "Use timezone-aware dates for both bounds.") from exc
        if invalid:
            raise HTTPException(422, "End time must be after start time.")
    selected_cameras = set(camera_serials or [])
    if camera_serial:
        selected_cameras.add(camera_serial)
    for serial in selected_cameras:
        verify_camera_access(serial, user)

    models: dict[str, type[Event] | type[Segment] | type[GalleryItem]] = {
        "events": Event,
        "recordings": Segment,
        "snapshots": GalleryItem,
    }
    model = models[kind]
    timestamp = {
        "events": Event.start_time,
        "recordings": Segment.start_time,
        "snapshots": GalleryItem.captured_at,
    }[kind]
    stmt = select(model, Camera).join(Camera, model.camera_serial == Camera.serial)
    if user.role not in ("owner", "operator"):
        stmt = stmt.where(model.camera_serial.in_({p.camera_serial for p in user.permissions}))
    if selected_cameras:
        stmt = stmt.where(model.camera_serial.in_(selected_cameras))
    if kind == "events":
        stmt = stmt.where(Event.hidden_at.is_(None))
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
    elif kind == "recordings":
        stmt = stmt.where(Segment.status == "active")
        if event_type:
            matching_events = select(Event.id).where(
                Event.camera_serial == Segment.camera_serial,
                Event.event_type == event_type,
                Event.hidden_at.is_(None),
                Event.start_time >= Segment.start_time,
                Event.start_time < Segment.end_time,
            )
            if start_time:
                matching_events = matching_events.where(Event.start_time >= start_time)
            if end_time:
                matching_events = matching_events.where(Event.start_time < end_time)
            stmt = stmt.where(exists(matching_events))
    else:
        stmt = stmt.where(GalleryItem.item_type == "snapshot")
    if start_time:
        # Include recordings overlapping the selected interval, even if they started earlier.
        if kind == "recordings":
            stmt = stmt.where(Segment.end_time > start_time)
        else:
            stmt = stmt.where(timestamp >= start_time)
    if end_time:
        stmt = stmt.where(timestamp < end_time)
    if q.strip():
        terms: list[ColumnElement[str] | InstrumentedAttribute[str]] = [
            Camera.name,
            Camera.location,
            Camera.serial,
        ]
        if kind == "events":
            terms.append(func.replace(Event.event_type, "_", " "))
        if kind == "snapshots":
            terms.append(GalleryItem.title)
        stmt = stmt.where(
            or_(*(func.lower(col).contains(q.strip().lower(), autoescape=True) for col in terms))
        )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    event_has_recording = exists(
        select(Segment.id).where(
            Segment.camera_serial == Event.camera_serial,
            Segment.stream_type == "main",
            Segment.status == "active",
            Segment.start_time <= Event.start_time,
            Segment.end_time > Event.start_time,
        )
    )
    rows = (
        await db.execute(
            stmt.add_columns(event_has_recording if kind == "events" else literal(False))
            .order_by(timestamp.desc(), model.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = []
    for indexed_item, camera, has_recording in rows:
        row = cast(Event | Segment | GalleryItem, indexed_item)
        if isinstance(row, GalleryItem):
            at = row.captured_at
            title = row.title
            thumb = f"/api/v1/gallery/{row.id}/download"
            href = f"/gallery?item={row.id}"
        else:
            at = row.start_time
            title = "Recorded footage"
            thumb = None
            if isinstance(row, Event):
                title = row.event_type.replace("_", " ").title()
                if row.snapshot_path:
                    thumb = f"/api/v1/events/{row.id}/snapshot"
            href = "/playback?" + urlencode({"camera": camera.serial, "t": at.isoformat()})
            if isinstance(row, Event) and not has_recording:
                href = f"/events/{row.id}"
        items.append(
            SearchItem(
                id=row.id,
                kind=kind,
                camera_serial=camera.serial,
                camera_name=camera.name,
                location=camera.location,
                title=title,
                timestamp=at,
                end_time=getattr(row, "end_time", None),
                duration_seconds=getattr(row, "duration_seconds", None),
                thumbnail_url=thumb,
                href=href,
                is_protected=bool(getattr(row, "is_locked", False) or getattr(row, "is_protected", False)),
            )
        )
    return SearchResponse(items=items, total=total, limit=limit, offset=offset)
