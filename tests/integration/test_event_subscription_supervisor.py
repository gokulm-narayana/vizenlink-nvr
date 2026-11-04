"""Integration tests for EventSubscriptionSupervisor with resilient reconnects (EVT-01, EVT-06)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.db.models import Base, Camera, EventSubscription
from vizenlink_nvr.events.source import EventSource, RawCameraEvent
from vizenlink_nvr.events.supervisor import EventSubscriptionSupervisor
from vizenlink_nvr.services.events import ClockSyncState
from vizenlink_nvr.timeutil import utc_now


class MockEventSource(EventSource):
    """Mock event source simulating subscription, polling, renewal, and intermittent failures."""

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.subscribe_calls = 0
        self.renew_calls = 0
        self.unsubscribe_calls = 0
        self.fail_next_poll = False
        self.events_to_emit: list[RawCameraEvent] = []

    async def subscribe(self) -> str:
        self.subscribe_calls += 1
        return f"http://127.0.0.1/subscription/{self.serial}?idx={self.subscribe_calls}"

    async def poll(self, timeout_seconds: float = 5.0) -> list[RawCameraEvent]:
        if self.fail_next_poll:
            self.fail_next_poll = False
            raise ConnectionResetError("Simulated camera socket drop")

        if self.events_to_emit:
            res = list(self.events_to_emit)
            self.events_to_emit.clear()
            return res

        await asyncio.sleep(0.05)
        return []

    async def renew(self, seconds: int = 60) -> bool:
        self.renew_calls += 1
        return True

    async def unsubscribe(self) -> None:
        self.unsubscribe_calls += 1


@pytest.mark.asyncio
async def test_supervisor_lifecycle_and_reconnect(tmp_path: Path) -> None:
    """Test supervisor establishes subscriptions, handles events, and auto-reconnects on error."""
    db_path = tmp_path / "test_supervisor.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = utc_now()

    # Seed camera
    async with session_factory() as session:
        cam = Camera(
            serial="CAM-SUP-01",
            host="192.168.1.99",
            name="Loading Dock",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)
        await session.commit()

    received_events: list[RawCameraEvent] = []

    async def on_event(evt: RawCameraEvent) -> None:
        received_events.append(evt)

    source = MockEventSource("CAM-SUP-01")
    supervisor = EventSubscriptionSupervisor(session_factory, event_callback=on_event)
    supervisor.register_camera_source("CAM-SUP-01", source)

    # 1. Start supervisor
    await supervisor.start()
    await asyncio.sleep(0.1)

    # Verify subscription state is active
    async with session_factory() as session:
        sub = await session.get(EventSubscription, "CAM-SUP-01")
        assert sub is not None
        assert sub.state == "active"
        assert "CAM-SUP-01" in (sub.subscription_url or "")
        assert source.subscribe_calls == 1

    # 2. Emit an event through source
    source.events_to_emit.append(
        RawCameraEvent(
            camera_serial="CAM-SUP-01",
            topic="tns1:RuleEngine/CellMotionDetector/Motion",
            utc_time=now,
            data={"State": "true"},
            source_name="onvif_pullpoint",
            clock_drift_seconds=0.1,
            clock_sync_state=ClockSyncState.SYNCED,
        )
    )
    await asyncio.sleep(0.15)
    assert len(received_events) == 1
    assert received_events[0].topic == "tns1:RuleEngine/CellMotionDetector/Motion"

    # Verify last_event_at updated in database
    async with session_factory() as session:
        sub = await session.get(EventSubscription, "CAM-SUP-01")
        assert sub is not None
        assert sub.last_event_at is not None

    # 3. Simulate failure in poll loop -> supervisor should catch and resubscribe
    source.fail_next_poll = True
    await asyncio.sleep(0.2)  # Give time for error and reconnect loop

    # Allow resubscription backoff to elapse and succeed
    await asyncio.sleep(1.2)
    assert source.subscribe_calls >= 2

    async with session_factory() as session:
        sub = await session.get(EventSubscription, "CAM-SUP-01")
        assert sub is not None
        assert sub.state == "active"

    # 4. Clean shutdown
    await supervisor.stop()
    assert source.unsubscribe_calls >= 1

    await engine.dispose()

