"""Integration tests for /api/v1/events endpoints, RBAC scoping, and locking."""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import (
    Base,
    Camera,
    Event,
    EventSubscription,
    RecordingSettings,
    Segment,
    StorageSettings,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.events.snapshots import TINY_JPEG_BYTES
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_api_events.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    # Prepare snapshot file on disk
    snap_rel = "events/CAM-PERMITTED/2026/11/04/1.jpg"
    snap_abs = storage_root / snap_rel
    snap_abs.parent.mkdir(parents=True, exist_ok=True)
    snap_abs.write_bytes(TINY_JPEG_BYTES)

    now = utc_now()

    async with session_factory() as session:
        # Storage settings
        storage_setting = StorageSettings(
            id=1,
            storage_path=str(storage_root),
            allow_system_disk=True,
            reserve_bytes=10 * 1024 * 1024 * 1024,
            created_at=now,
            updated_at=now,
        )
        session.add(storage_setting)

        # Users
        owner = User(
            username="owner_user",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="viewer_user",
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
            host="192.168.1.10",
            name="Front Gate",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-FORBIDDEN",
            host="192.168.1.11",
            name="Back Alley",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])

        rec_settings = RecordingSettings(
            camera_serial="CAM-PERMITTED",
            mode="event",
            pre_roll_seconds=10,
            post_roll_seconds=10,
            created_at=now,
            updated_at=now,
        )
        session.add(rec_settings)

        # Segments
        seg = Segment(
            camera_serial="CAM-PERMITTED",
            stream_type="sub",
            start_time=now - datetime.timedelta(seconds=5),
            end_time=now + datetime.timedelta(seconds=5),
            duration_seconds=10.0,
            file_path="recordings/CAM-PERMITTED/seg1.mp4",
            file_size_bytes=1000,
            status="active",
            is_protected=False,
            created_at=now,
        )
        session.add(seg)

        # Events
        evt1 = Event(
            id=1,
            camera_serial="CAM-PERMITTED",
            event_type="motion",
            source="pullpoint",
            start_time=now,
            end_time=now + datetime.timedelta(seconds=2),
            snapshot_path=snap_rel,
            is_locked=False,
            clock_sync_state="synced",
            raw_topic="tns1:RuleEngine/MotionRegionDetector/Motion",
            details_json='{"rule": "Motion"}',
            created_at=now,
        )
        evt2 = Event(
            id=2,
            camera_serial="CAM-FORBIDDEN",
            event_type="line_crossing",
            source="pullpoint",
            start_time=now - datetime.timedelta(minutes=10),
            end_time=now - datetime.timedelta(minutes=9),
            snapshot_path=None,
            is_locked=True,
            clock_sync_state="synced",
            raw_topic="tns1:RuleEngine/LineDetector/Crossed",
            details_json='{"line": "Fence"}',
            created_at=now,
        )
        session.add_all([evt1, evt2])

        # Subscriptions
        sub1 = EventSubscription(
            camera_serial="CAM-PERMITTED",
            state="active",
            subscription_url="http://192.168.1.10/subscription",
            last_event_at=now,
            last_renewed_at=now,
            clock_drift_seconds=0.5,
            updated_at=now,
        )
        sub2 = EventSubscription(
            camera_serial="CAM-FORBIDDEN",
            state="failed",
            subscription_url=None,
            error_reason="Connection refused",
            clock_drift_seconds=None,
            updated_at=now,
        )
        session.add_all([sub1, sub2])

        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_session, viewer_session, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_owner_query_events(app_fixture):
    client, owner_session, _, _ = app_fixture

    resp = await client.get(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Filter by camera
    resp = await client.get(
        "/api/v1/events?camera_serial=CAM-PERMITTED",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["camera_serial"] == "CAM-PERMITTED"

    # Filter by event_type
    resp = await client.get(
        "/api/v1/events?event_type=line_crossing",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["event_type"] == "line_crossing"


@pytest.mark.asyncio
async def test_viewer_query_events_rbac(app_fixture):
    client, _, viewer_session, _ = app_fixture

    # Viewer queries all events -> scoped to CAM-PERMITTED only
    resp = await client.get(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["camera_serial"] == "CAM-PERMITTED"

    # Viewer explicitly requests forbidden camera -> 403
    resp = await client.get(
        "/api/v1/events?camera_serial=CAM-FORBIDDEN",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_event_detail_and_snapshot(app_fixture):
    client, owner_session, viewer_session, _ = app_fixture

    # Detail access permitted
    resp = await client.get(
        "/api/v1/events/1",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == 1

    # Detail access forbidden
    resp = await client.get(
        "/api/v1/events/2",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 403

    # Snapshot retrieval permitted
    resp = await client.get(
        "/api/v1/events/1/snapshot",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == TINY_JPEG_BYTES

    # Snapshot forbidden
    resp = await client.get(
        "/api/v1/events/2/snapshot",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_event_locking_and_protection(app_fixture):
    client, owner_session, viewer_session, session_factory = app_fixture

    # Viewer cannot lock (requires operator or owner)
    resp = await client.post(
        "/api/v1/events/1/lock",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 403

    # Owner locks event 1
    resp = await client.post(
        "/api/v1/events/1/lock",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_locked"] is True

    # Verify segment was marked protected
    async with session_factory() as session:
        seg = (await session.execute(Segment.__table__.select())).first()
        assert seg.is_protected is True

    # Owner unlocks event 1
    resp = await client.post(
        "/api/v1/events/1/unlock",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_locked"] is False

    # Verify segment protection is released
    async with session_factory() as session:
        seg = (await session.execute(Segment.__table__.select())).first()
        assert seg.is_protected is False


@pytest.mark.asyncio
async def test_subscription_status(app_fixture):
    client, owner_session, viewer_session, _ = app_fixture

    # Owner sees all subscriptions
    resp = await client.get(
        "/api/v1/events/subscriptions/status",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Viewer sees only CAM-PERMITTED
    resp = await client.get(
        "/api/v1/events/subscriptions/status",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["camera_serial"] == "CAM-PERMITTED"


@pytest.mark.asyncio
async def test_alert_review_workflow(app_fixture) -> None:
    """Phase 10: severity, search, acknowledge / resolve / reopen, acknowledge-all, hide."""
    client, owner_session, viewer_session = app_fixture[0], app_fixture[1], app_fixture[2]

    client.cookies.set("session_id", owner_session)
    items = {i["id"]: i for i in (await client.get("/api/v1/events")).json()["items"]}
    assert items[1]["severity"] == "info" and items[1]["review_state"] == "new"
    assert items[2]["severity"] == "warning"

    # Severity and search filters
    assert [i["id"] for i in (await client.get("/api/v1/events?severity=warning")).json()["items"]] == [2]
    assert [i["id"] for i in (await client.get("/api/v1/events?severity=info")).json()["items"]] == [1]
    assert [i["id"] for i in (await client.get("/api/v1/events?q=front")).json()["items"]] == [1]
    assert [i["id"] for i in (await client.get("/api/v1/events?q=line crossing")).json()["items"]] == [2]

    # Viewer can acknowledge their own camera's alert but not someone else's
    client.cookies.set("session_id", viewer_session)
    res = await client.post("/api/v1/events/1/acknowledge")
    assert res.status_code == 200
    body = res.json()
    assert body["review_state"] == "acknowledged" and body["reviewed_by"] == "viewer_user"
    assert (await client.post("/api/v1/events/2/acknowledge")).status_code == 403
    # Viewers cannot hide alerts
    assert (await client.post("/api/v1/events/1/hide")).status_code == 403

    client.cookies.set("session_id", owner_session)
    assert (await client.post("/api/v1/events/1/resolve")).json()["review_state"] == "resolved"
    assert [i["id"] for i in (await client.get("/api/v1/events?review_state=open")).json()["items"]] == [2]
    assert (await client.post("/api/v1/events/1/reopen")).json()["review_state"] == "new"

    # Acknowledge all open alerts
    assert (await client.post("/api/v1/events/acknowledge-all", json={})).json() == {"acknowledged": 2}
    assert (await client.get("/api/v1/events?review_state=new")).json()["total"] == 0

    # Locked alerts cannot be hidden (footage protection); unlocked ones disappear from lists
    assert (await client.post("/api/v1/events/2/hide")).status_code == 409
    assert (await client.post("/api/v1/events/1/hide")).json() == {"hidden": True}
    listed = (await client.get("/api/v1/events")).json()
    assert [i["id"] for i in listed["items"]] == [2] and listed["total"] == 1
    assert (await client.get("/api/v1/events/1")).status_code == 404
    assert (await client.post("/api/v1/events/1/acknowledge")).status_code == 404

    # Audit trail records the review actions
    audit = (await client.get("/api/v1/audit-logs?limit=200")).json()
    actions = {a["action"] for a in audit["items"]}
    assert {"event.acknowledge", "event.resolve", "event.acknowledge_all", "event.hide"} <= actions
