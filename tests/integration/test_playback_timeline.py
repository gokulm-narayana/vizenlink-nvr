"""Integration tests for playback timeline, calendar days, search, and segment locking."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import (
    AuditLog,
    Base,
    Camera,
    CameraOutage,
    Event,
    RecordingSettings,
    Segment,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import UTC


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_playback_timeline.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    now = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)

    async with session_factory() as session:
        # Users
        owner = User(
            username="pb_owner",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="pb_viewer",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer.permissions.append(
            UserCameraPermission(camera_serial="CAM-PERMITTED", created_at=now)
        )
        session.add_all([owner, viewer])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(viewer)

        s_owner = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        s_viewer = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "test")
        owner_session = s_owner.id
        viewer_session = s_viewer.id

        # Cameras
        cam1 = Camera(
            serial="CAM-PERMITTED",
            host="192.168.1.20",
            name="Driveway",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-RESTRICTED",
            host="192.168.1.21",
            name="Office",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])

        # Recording Settings
        rec = RecordingSettings(
            camera_serial="CAM-PERMITTED",
            mode="continuous",
            created_at=now,
            updated_at=now,
        )
        session.add(rec)

        # Segments
        seg1 = Segment(
            id=101,
            camera_serial="CAM-PERMITTED",
            stream_type="main",
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1, minutes=55),
            duration_seconds=300.0,
            file_path="recordings/CAM-PERMITTED/seg1.mp4",
            file_size_bytes=5000000,
            status="active",
            is_protected=False,
            created_at=now - timedelta(hours=2),
        )
        seg2 = Segment(
            id=102,
            camera_serial="CAM-PERMITTED",
            stream_type="main",
            start_time=now - timedelta(hours=1),
            end_time=now - timedelta(minutes=55),
            duration_seconds=300.0,
            file_path="recordings/CAM-PERMITTED/seg2.mp4",
            file_size_bytes=5000000,
            status="active",
            is_protected=False,
            created_at=now - timedelta(hours=1),
        )
        session.add_all([seg1, seg2])

        # Camera Outage (PLAY-08: distinct outage gap)
        outage = CameraOutage(
            id=201,
            camera_serial="CAM-PERMITTED",
            started_at=now - timedelta(hours=1, minutes=50),
            ended_at=now - timedelta(hours=1, minutes=20),
            duration_seconds=1800.0,
            reason="Unreachable network connection",
        )
        session.add(outage)

        # Event marker
        evt = Event(
            id=301,
            camera_serial="CAM-PERMITTED",
            event_type="motion",
            source="pullpoint",
            start_time=now - timedelta(hours=1, minutes=58),
            end_time=now - timedelta(hours=1, minutes=57),
            snapshot_path="events/CAM-PERMITTED/2026/11/04/301.jpg",
            is_locked=False,
            clock_sync_state="synced",
            created_at=now,
        )
        session.add(evt)
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_session, viewer_session, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_timeline_query_and_outage_distinction(app_fixture):
    client, owner_session, _, _ = app_fixture

    start_iso = "2026-11-04T00:00:00Z"
    end_iso = "2026-11-04T23:59:59Z"

    resp = await client.get(
        f"/api/v1/playback/timeline?camera_serial=CAM-PERMITTED&start_time={start_iso}&end_time={end_iso}",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_serial"] == "CAM-PERMITTED"

    # Segments
    assert len(data["segments"]) == 2
    assert data["segments"][0]["id"] == 101
    assert data["segments"][0]["is_protected"] is False

    # Outages (PLAY-08)
    assert len(data["outages"]) == 1
    assert data["outages"][0]["id"] == 201
    assert data["outages"][0]["reason"] == "Unreachable network connection"

    # Events
    assert len(data["events"]) == 1
    assert data["events"][0]["id"] == 301
    assert data["events"][0]["event_type"] == "motion"


@pytest.mark.asyncio
async def test_calendar_days_query(app_fixture):
    client, owner_session, _, _ = app_fixture

    resp = await client.get(
        "/api/v1/playback/days?camera_serial=CAM-PERMITTED&year=2026&month=11",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_serial"] == "CAM-PERMITTED"
    assert data["year"] == 2026
    assert data["month"] == 11
    assert "2026-11-04" in data["days"]


@pytest.mark.asyncio
async def test_recordings_search(app_fixture):
    client, owner_session, _, _ = app_fixture

    resp = await client.get(
        "/api/v1/playback/search?camera_serial=CAM-PERMITTED&event_type=motion",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["event_id"] == 301
    assert results[0]["event_type"] == "motion"


@pytest.mark.asyncio
async def test_segment_locking_and_audit(app_fixture):
    client, owner_session, viewer_session, session_factory = app_fixture

    # Viewer cannot lock (requires operator or owner)
    resp_viewer = await client.post(
        "/api/v1/playback/segments/101/lock",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp_viewer.status_code == 403

    # Owner locks segment
    resp_lock = await client.post(
        "/api/v1/playback/segments/101/lock",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp_lock.status_code == 200
    assert resp_lock.json()["is_protected"] is True

    # Owner unlocks segment
    resp_unlock = await client.post(
        "/api/v1/playback/segments/101/unlock",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp_unlock.status_code == 200
    assert resp_unlock.json()["is_protected"] is False

    # Check audit log entries
    async with session_factory() as session:
        logs = (await session.execute(AuditLog.__table__.select())).all()
        actions = [log.action for log in logs]
        assert "playback.segment_lock" in actions
        assert "playback.segment_unlock" in actions


@pytest.mark.asyncio
async def test_viewer_rbac_scoping(app_fixture):
    client, _, viewer_session, _ = app_fixture

    start_iso = "2026-11-04T00:00:00Z"
    end_iso = "2026-11-04T23:59:59Z"

    # Viewer requests non-permitted camera timeline -> 403
    resp = await client.get(
        f"/api/v1/playback/timeline?camera_serial=CAM-RESTRICTED&start_time={start_iso}&end_time={end_iso}",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 403

    # Viewer requests non-permitted camera days -> 403
    resp_days = await client.get(
        "/api/v1/playback/days?camera_serial=CAM-RESTRICTED&year=2026&month=11",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp_days.status_code == 403


@pytest.mark.asyncio
async def test_unlock_keeps_event_protection(app_fixture):
    client, owner, _, sessions = app_fixture
    async with sessions() as session:
        segment = await session.get(Segment, 101)
        segment.is_protected = True
        segment.protection_reason = "event:12"
        await session.commit()
    headers = {"Authorization": f"Bearer {owner}"}
    for _ in range(2):
        response = await client.post("/api/v1/playback/segments/101/lock", headers=headers)
        assert response.json()["protection_reason"].count("evidence_lock:") == 1
    kept = await client.post("/api/v1/playback/segments/101/unlock", headers=headers)
    assert kept.json()["is_protected"] and kept.json()["protection_reason"] == "event:12"
