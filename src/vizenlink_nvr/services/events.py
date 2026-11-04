"""Event domain types, topic canonicalization, and database repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import Event
from vizenlink_nvr.timeutil import utc_now


class EventType(StrEnum):
    """Canonical event classification types."""

    MOTION = "motion"
    LINE_CROSSING = "line_crossing"
    TAMPER = "tamper"
    PERSON = "person"
    VEHICLE = "vehicle"
    DIGITAL_INPUT = "digital_input"
    GENERIC = "generic"


class ClockSyncState(StrEnum):
    """Camera clock synchronization status relative to NVR."""

    SYNCED = "synced"
    UNCERTAIN = "uncertain"
    DRIFT_DETECTED = "drift_detected"


TOPIC_MAPPINGS: list[tuple[str, EventType]] = [
    ("LineDetector/LineCrossed", EventType.LINE_CROSSING),
    ("LineCrossed", EventType.LINE_CROSSING),
    ("TamperDetector/Tamper", EventType.TAMPER),
    ("Tamper", EventType.TAMPER),
    ("CellMotionDetector/Motion", EventType.MOTION),
    ("MotionRegionDetector/Motion", EventType.MOTION),
    ("Motion", EventType.MOTION),
    ("VideoAnalytics/Person", EventType.PERSON),
    ("Human", EventType.PERSON),
    ("Person", EventType.PERSON),
    ("VideoAnalytics/Vehicle", EventType.VEHICLE),
    ("Vehicle", EventType.VEHICLE),
    ("Trigger/DigitalInput", EventType.DIGITAL_INPUT),
    ("DigitalInput", EventType.DIGITAL_INPUT),
]


def canonicalize_event_topic(topic: str) -> EventType:
    """Map raw ONVIF or vendor event topic string to canonical EventType."""
    if not topic:
        return EventType.GENERIC

    for pattern, event_type in TOPIC_MAPPINGS:
        if pattern.lower() in topic.lower():
            return event_type

    return EventType.GENERIC


@dataclass(frozen=True)
class EventRecord:
    """In-memory domain representation of an ingested camera event."""

    camera_serial: str
    event_type: EventType
    start_time: datetime
    end_time: datetime | None = None
    source: str = "onvif_pullpoint"
    snapshot_path: str | None = None
    is_locked: bool = False
    clock_sync_state: ClockSyncState = ClockSyncState.SYNCED
    raw_topic: str | None = None
    details: dict[str, Any] | None = None


async def insert_event(session: AsyncSession, record: EventRecord) -> Event:
    """Persist a new event record into the database."""
    now = utc_now()
    details_str = json.dumps(record.details) if record.details else None

    row = Event(
        camera_serial=record.camera_serial,
        event_type=record.event_type.value,
        source=record.source,
        start_time=record.start_time,
        end_time=record.end_time,
        snapshot_path=record.snapshot_path,
        is_locked=record.is_locked,
        clock_sync_state=record.clock_sync_state.value,
        raw_topic=record.raw_topic,
        details_json=details_str,
        created_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_event(session: AsyncSession, event_id: int) -> Event | None:
    """Fetch event by primary key ID."""
    return await session.get(Event, event_id)


async def set_event_locked(session: AsyncSession, event_id: int, locked: bool) -> Event | None:
    """Toggle event lock status."""
    event = await get_event(session, event_id)
    if event is None:
        return None

    event.is_locked = locked
    await session.commit()
    await session.refresh(event)
    return event


async def list_events(
    session: AsyncSession,
    camera_serial: str | None = None,
    allowed_cameras: set[str] | None = None,
    event_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    is_locked: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Event]:
    """Query events with filtering and pagination."""
    stmt = select(Event).order_by(Event.start_time.desc())

    if camera_serial:
        stmt = stmt.where(Event.camera_serial == camera_serial)
    elif allowed_cameras is not None:
        stmt = stmt.where(Event.camera_serial.in_(allowed_cameras))

    if event_type:
        stmt = stmt.where(Event.event_type == event_type)

    if start_time:
        stmt = stmt.where(Event.start_time >= start_time)

    if end_time:
        stmt = stmt.where(Event.start_time <= end_time)

    if is_locked is not None:
        stmt = stmt.where(Event.is_locked == is_locked)

    stmt = stmt.limit(limit).offset(offset)
    res = await session.execute(stmt)
    return list(res.scalars().all())
