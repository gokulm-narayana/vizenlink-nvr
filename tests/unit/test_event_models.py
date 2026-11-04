"""Unit tests for Event data models, topics, and repository (EVT-01, REC-04, HLTH-09)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.db.models import Base, Camera, RecordingSettings
from vizenlink_nvr.services.events import (
    ClockSyncState,
    EventRecord,
    EventType,
    canonicalize_event_topic,
    get_event,
    insert_event,
    list_events,
    set_event_locked,
)
from vizenlink_nvr.timeutil import utc_now


def test_canonicalize_event_topics() -> None:
    """Verify raw topic substrings map to canonical event classifications."""
    assert canonicalize_event_topic("tns1:RuleEngine/CellMotionDetector/Motion") == EventType.MOTION
    assert canonicalize_event_topic("tns1:RuleEngine/LineDetector/LineCrossed") == EventType.LINE_CROSSING
    assert canonicalize_event_topic("tns1:RuleEngine/TamperDetector/Tamper") == EventType.TAMPER
    assert canonicalize_event_topic("tns1:VideoAnalytics/Person") == EventType.PERSON
    assert canonicalize_event_topic("tns1:VideoAnalytics/Vehicle") == EventType.VEHICLE
    assert canonicalize_event_topic("tns1:Device/Trigger/DigitalInput") == EventType.DIGITAL_INPUT
    assert canonicalize_event_topic("tns1:UnknownVendor/Alert") == EventType.GENERIC
    assert canonicalize_event_topic("") == EventType.GENERIC


@pytest.mark.asyncio
async def test_event_crud_and_locking(tmp_path: Path) -> None:
    """Test inserting event records, querying, and updating lock status."""
    db_path = tmp_path / "test_events.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = utc_now()

    async with session_factory() as session:
        cam = Camera(
            serial="CAM-EVT-01",
            host="192.168.1.50",
            name="Front Gate",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        rec_settings = RecordingSettings(
            camera_serial="CAM-EVT-01",
            mode="event",
            pre_roll_seconds=15,
            post_roll_seconds=20,
            created_at=now,
            updated_at=now,
        )
        session.add_all([cam, rec_settings])
        await session.commit()

        # Check pre-roll / post-roll defaults
        assert rec_settings.pre_roll_seconds == 15
        assert rec_settings.post_roll_seconds == 20

        # Insert motion event
        evt_record = EventRecord(
            camera_serial="CAM-EVT-01",
            event_type=EventType.MOTION,
            start_time=now,
            raw_topic="tns1:RuleEngine/CellMotionDetector/Motion",
            clock_sync_state=ClockSyncState.SYNCED,
            details={"motion_level": 85},
        )
        created = await insert_event(session, evt_record)
        assert created.id is not None
        assert created.camera_serial == "CAM-EVT-01"
        assert created.event_type == "motion"
        assert created.is_locked is False

        # Retrieve event
        fetched = await get_event(session, created.id)
        assert fetched is not None
        assert fetched.event_type == "motion"

        # Lock event
        locked = await set_event_locked(session, created.id, locked=True)
        assert locked is not None
        assert locked.is_locked is True

        # Query events list
        evts = await list_events(session, camera_serial="CAM-EVT-01", is_locked=True)
        assert len(evts) == 1
        assert evts[0].id == created.id

    await engine.dispose()
