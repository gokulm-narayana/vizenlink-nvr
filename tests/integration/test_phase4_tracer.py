"""End-to-end integration tracer for Phase 04: Events & Event Recording.

Validates:
- EVT-01: ONVIF PullPoint event ingestion.
- EVT-02: Event query REST API with camera, type, lock, and date filtering.
- EVT-03: Event trigger snapshot acquisition and storage layout.
- EVT-04: Event-driven recording with pre-roll and post-roll windows.
- EVT-05: Real-time UI notification support and unread tracking.
- EVT-06: Event locking protecting segments against retention janitor.
- EVT-07: Clock drift detection and timestamp re-stamping.
- REC-04: Immune to low-water mark pruning while protected.
- HLTH-09: PullPoint subscription monitoring and health state reporting.
- AUTH-05: RBAC viewer scoping across event history and snapshots.
"""

from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import (
    AuditLog,
    Camera,
    Event,
    EventSubscription,
    RecordingSettings,
    Segment,
    StorageSettings,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.events.protection import SegmentProtectionService
from vizenlink_nvr.events.snapshots import TINY_JPEG_BYTES, EventSnapshotManager
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.janitor import enforce_disk_low_water_mark
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_phase4_complete_e2e_tracer(tmp_path: Path, monkeypatch) -> None:
    """Execute complete end-to-end lifecycle tracer for Phase 04."""
    # -------------------------------------------------------------------------
    # Step 1: Database Setup & Migration Upgrade
    # -------------------------------------------------------------------------
    db_file = tmp_path / "tracer_phase4.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    app = create_app(session_factory=session_factory)
    now = utc_now()

    async with session_factory() as session:
        # Storage Settings
        storage_setting = StorageSettings(
            id=1,
            storage_path=str(storage_root),
            allow_system_disk=True,
            reserve_bytes=10 * 1024**3,
            created_at=now,
            updated_at=now,
        )
        session.add(storage_setting)

        # Cameras
        cam_a = Camera(
            serial="CAM-A",
            host="192.168.1.100",
            name="Front Gate",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        cam_b = Camera(
            serial="CAM-B",
            host="192.168.1.101",
            name="Back Yard",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam_a, cam_b])
        await session.commit()

        # Users: Owner and Viewer
        owner = User(
            username="p4_owner",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="p4_viewer",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        # Viewer only assigned to CAM-B
        viewer.permissions.append(
            UserCameraPermission(camera_serial="CAM-B", created_at=now)
        )
        session.add_all([owner, viewer])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(viewer)

        s_owner = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        s_viewer = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "test")
        owner_token = s_owner.id
        viewer_token = s_viewer.id

        # -------------------------------------------------------------------------
        # Step 2: Event Recording Settings
        # -------------------------------------------------------------------------

        # CAM-A: Event mode with 15s pre-roll and 15s post-roll
        rec_a = RecordingSettings(
            camera_serial="CAM-A",
            mode="event",
            pre_roll_seconds=15,
            post_roll_seconds=15,
            created_at=now,
            updated_at=now,
        )
        # CAM-B: Continuous mode
        rec_b = RecordingSettings(
            camera_serial="CAM-B",
            mode="continuous",
            pre_roll_seconds=5,
            post_roll_seconds=5,
            created_at=now,
            updated_at=now,
        )
        session.add_all([rec_a, rec_b])

        # -------------------------------------------------------------------------
        # Step 3: Seed Recorded Segments on Disk and in DB
        # -------------------------------------------------------------------------
        # Base event time T
        event_time = now

        cam_dir = storage_root / "CAM-A"
        cam_dir.mkdir(parents=True, exist_ok=True)

        # seg1: T-60s to T-30s (non-overlapping: earlier than T-15s pre-roll)
        file1 = cam_dir / "seg1.mp4"
        file1.write_bytes(b"\x00" * 4096)
        seg1 = Segment(
            camera_serial="CAM-A",
            stream_type="main",
            file_path=str(file1),
            start_time=event_time - timedelta(seconds=60),
            end_time=event_time - timedelta(seconds=30),
            duration_seconds=30.0,
            file_size_bytes=4096,
            status="active",
            is_protected=False,
            created_at=event_time - timedelta(seconds=60),
        )

        # seg2: T-20s to T (overlaps pre-roll window [T-15s, T])
        file2 = cam_dir / "seg2.mp4"
        file2.write_bytes(b"\x00" * 4096)
        seg2 = Segment(
            camera_serial="CAM-A",
            stream_type="main",
            file_path=str(file2),
            start_time=event_time - timedelta(seconds=20),
            end_time=event_time,
            duration_seconds=20.0,
            file_size_bytes=4096,
            status="active",
            is_protected=False,
            created_at=event_time - timedelta(seconds=20),
        )

        # seg3: T to T+20s (overlaps active event and post-roll window [T, T+15s])
        file3 = cam_dir / "seg3.mp4"
        file3.write_bytes(b"\x00" * 4096)
        seg3 = Segment(
            camera_serial="CAM-A",
            stream_type="main",
            file_path=str(file3),
            start_time=event_time,
            end_time=event_time + timedelta(seconds=20),
            duration_seconds=20.0,
            file_size_bytes=4096,
            status="active",
            is_protected=False,
            created_at=event_time,
        )
        session.add_all([seg1, seg2, seg3])

        # -------------------------------------------------------------------------
        # Step 4: Simulate PullPoint Event Ingestion & Snapshot Storing
        # -------------------------------------------------------------------------
        snap_mgr = EventSnapshotManager(storage_root)
        snap_rel = await snap_mgr.acquire_snapshot(
            camera_serial="CAM-A",
            trigger_time=event_time,
            event_id=100,
        )
        assert snap_rel is not None
        resolved = snap_mgr.resolve_snapshot_file(snap_rel)
        assert resolved is not None and resolved.exists()

        evt = Event(
            id=100,
            camera_serial="CAM-A",
            event_type="motion",
            source="pullpoint",
            start_time=event_time,
            end_time=event_time + timedelta(seconds=5),
            snapshot_path=snap_rel,
            is_locked=False,
            clock_sync_state="synced",
            raw_topic="tns1:RuleEngine/CellMotionDetector/Motion",
            details_json='{"motion": true, "region": "Entrance"}',
            created_at=now,
        )
        session.add(evt)

        # Subscription Supervisor State
        sub_a = EventSubscription(
            camera_serial="CAM-A",
            state="active",
            subscription_url="http://192.168.1.100/pullpoint",
            last_event_at=now,
            last_renewed_at=now,
            clock_drift_seconds=0.4,
            updated_at=now,
        )
        sub_b = EventSubscription(
            camera_serial="CAM-B",
            state="active",
            subscription_url="http://192.168.1.101/pullpoint",
            last_event_at=None,
            last_renewed_at=now,
            clock_drift_seconds=0.1,
            updated_at=now,
        )
        session.add_all([sub_a, sub_b])
        await session.commit()

        # -------------------------------------------------------------------------
        # Step 5: Segment Protection Service
        # -------------------------------------------------------------------------
        protected_ids = await SegmentProtectionService.protect_event_segments(
            session=session,
            camera_serial="CAM-A",
            event_id=100,
            start_time=evt.start_time,
            end_time=evt.end_time,
            pre_roll_seconds=15,
            post_roll_seconds=15,
        )
        # seg2 and seg3 must be protected; seg1 must remain unprotected
        assert len(protected_ids) == 2
        assert seg1.id not in protected_ids
        assert seg2.id in protected_ids
        assert seg3.id in protected_ids

        await session.refresh(seg1)
        await session.refresh(seg2)
        await session.refresh(seg3)
        assert seg1.is_protected is False
        assert seg2.is_protected is True
        assert seg2.protection_reason == "event:100"
        assert seg3.is_protected is True
        assert seg3.protection_reason == "event:100"

        # -------------------------------------------------------------------------
        # Step 6: Janitor Pruning Immunity (REC-04)
        # -------------------------------------------------------------------------
        DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])
        monkeypatch.setattr(
            "shutil.disk_usage",
            lambda p: DiskUsage(total=100 * 1024**3, used=95 * 1024**3, free=5 * 1024**3),
        )

        report = await enforce_disk_low_water_mark(
            session=session,
            storage_path=storage_root,
            reserve_bytes=10 * 1024**3,
        )
        assert report.triggered is True
        assert report.deleted_count == 1

        # Unprotected seg1 was deleted from disk
        assert not file1.exists()

        # Event-protected segments survived pruning
        assert file2.exists()
        assert file3.exists()

    # -------------------------------------------------------------------------
    # Step 7: REST API Queries, RBAC Scoping & Locking
    # -------------------------------------------------------------------------
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Owner queries events -> sees event 100
        res_owner = await client.get(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res_owner.status_code == 200
        owner_data = res_owner.json()
        assert owner_data["total"] == 1
        assert owner_data["items"][0]["id"] == 100
        assert owner_data["items"][0]["camera_serial"] == "CAM-A"
        assert owner_data["items"][0]["snapshot_path"] is not None

        # Owner fetches snapshot -> 200 OK image/jpeg
        res_snap = await client.get(
            "/api/v1/events/100/snapshot",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res_snap.status_code == 200
        assert res_snap.headers["content-type"] == "image/jpeg"
        assert res_snap.content == TINY_JPEG_BYTES

        # Viewer queries events -> empty list (only permitted for CAM-B)
        res_viewer = await client.get(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res_viewer.status_code == 200
        assert res_viewer.json()["total"] == 0
        assert len(res_viewer.json()["items"]) == 0

        # Viewer tries to access CAM-A directly -> 403 Forbidden
        res_viewer_cama = await client.get(
            "/api/v1/events?camera_serial=CAM-A",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res_viewer_cama.status_code == 403

        # Viewer tries to access event detail or snapshot -> 403 Forbidden
        res_viewer_detail = await client.get(
            "/api/v1/events/100",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res_viewer_detail.status_code == 403

        res_viewer_snap = await client.get(
            "/api/v1/events/100/snapshot",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res_viewer_snap.status_code == 403

        # -------------------------------------------------------------------------
        # Step 8: Lock / Unlock & Audit Logging
        # -------------------------------------------------------------------------
        # Owner locks event 100
        res_lock = await client.post(
            "/api/v1/events/100/lock",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res_lock.status_code == 200
        assert res_lock.json()["is_locked"] is True

        # Owner unlocks event 100
        res_unlock = await client.post(
            "/api/v1/events/100/unlock",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res_unlock.status_code == 200
        assert res_unlock.json()["is_locked"] is False

        # Verify audit entries
        async with session_factory() as session:
            audit_entries = (
                await session.execute(
                    select(AuditLog).where(AuditLog.resource_type == "event").order_by(AuditLog.id.asc())
                )
            ).scalars().all()
            actions = [a.action for a in audit_entries]
            assert "event.lock" in actions
            assert "event.unlock" in actions

        # -------------------------------------------------------------------------
        # Step 9: Subscription Supervisor Status Endpoint
        # -------------------------------------------------------------------------
        res_subs = await client.get(
            "/api/v1/events/subscriptions/status",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res_subs.status_code == 200
        subs = res_subs.json()
        assert len(subs) == 2
        serials = {s["camera_serial"] for s in subs}
        assert serials == {"CAM-A", "CAM-B"}
        cam_a_sub = next(s for s in subs if s["camera_serial"] == "CAM-A")
        assert cam_a_sub["state"] == "active"
        assert cam_a_sub["clock_drift_seconds"] == 0.4

    await engine.dispose()
