"""Unit tests for in-app alert evaluation service (HLTH-08)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.db.models import Base, CameraOutage
from vizenlink_nvr.services.alert_service import AlertService
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def session_fixture(tmp_path: Path):
    db_path = tmp_path / "test_alerts_unit.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_prolonged_camera_offline_alert(session_fixture) -> None:
    """Outage longer than threshold triggers alert; short outage does not."""
    session = session_fixture
    now = utc_now()

    # Outage 1: 10 minutes ago (should trigger alert)
    long_outage = CameraOutage(
        camera_serial="CAM-LONG-OFFLINE",
        started_at=now - timedelta(minutes=10),
        ended_at=None,
        reason="Network timeout",
    )
    # Outage 2: 1 minute ago (should not trigger alert with 5 min threshold)
    short_outage = CameraOutage(
        camera_serial="CAM-SHORT-OFFLINE",
        started_at=now - timedelta(minutes=1),
        ended_at=None,
        reason="Brief blip",
    )
    # Outage 3: Already recovered (ended_at is not None)
    closed_outage = CameraOutage(
        camera_serial="CAM-CLOSED",
        started_at=now - timedelta(hours=1),
        ended_at=now - timedelta(minutes=50),
        duration_seconds=600.0,
    )

    session.add_all([long_outage, short_outage, closed_outage])
    await session.commit()

    alerts = await AlertService.evaluate_active_alerts(
        session=session,
        now=now,
        offline_threshold_seconds=300.0,
    )

    offline_alerts = [a for a in alerts if a.source.startswith("camera:")]
    assert len(offline_alerts) == 1
    assert offline_alerts[0].id == "camera_offline_CAM-LONG-OFFLINE"
    assert offline_alerts[0].severity == "warning"
    assert "10 minutes" in offline_alerts[0].message


@pytest.mark.asyncio
async def test_watchdog_gap_alerts(session_fixture) -> None:
    """Recording gap alarms passed into evaluate_active_alerts generate warning alerts."""
    session = session_fixture

    alerts = await AlertService.evaluate_active_alerts(
        session=session,
        gap_serials=["CAM-GAP-01", "CAM-GAP-02"],
    )

    gap_alerts = [a for a in alerts if a.source.startswith("watchdog:")]
    assert len(gap_alerts) == 2
    assert {a.id for a in gap_alerts} == {"recording_gap_CAM-GAP-01", "recording_gap_CAM-GAP-02"}
    assert all(a.severity == "warning" for a in gap_alerts)
