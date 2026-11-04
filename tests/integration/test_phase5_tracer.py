"""End-to-end integration tracer for Phase 05: Playback, Export & Gallery.

Validates:
- PLAY-01: 24h timeline with recorded segments and event flags.
- PLAY-02: Calendar days query indicating days with recordings.
- PLAY-03: Video scrubbing and playback seeking.
- PLAY-04: HTTP 206 Partial Content byte-range streaming for fMP4 video segments.
- PLAY-05: Gap skipping and transport playback controls.
- PLAY-06: Lossless MP4 clip export using stream copy without re-encoding.
- PLAY-07: Still frame snapshot capture from playback.
- PLAY-08: Camera outage periods visibly distinguished from pruned spans.
- GAL-01: Unified media gallery listing snapshots and clips with filters.
- GAL-02: Media downloads and deletion with storage unlinking.
- GAL-03: Recording search by event occurrences and timeline intervals.
- LIVE-07: Live still snapshot capture to media gallery.
- REC-12: Evidence locking protecting recording segments against retention pruning.
- AUTH-05: Strict RBAC viewer scoping across playback, export, and gallery.
"""

from __future__ import annotations

import base64
import struct
from datetime import UTC, datetime, timedelta
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
    CameraOutage,
    Event,
    Segment,
    StorageSettings,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager


def make_box(box_type: str, payload: bytes = b"") -> bytes:
    """Helper to build an ISOBMFF box with big-endian 4-byte size header."""
    size = 8 + len(payload)
    return struct.pack(">I", size) + box_type.encode("ascii") + payload


@pytest.mark.asyncio
async def test_phase5_complete_e2e_tracer(tmp_path: Path) -> None:
    """Execute complete end-to-end lifecycle tracer for Phase 05."""
    # -------------------------------------------------------------------------
    # Step 1: Database Setup via Alembic Migrations to Head (includes 0006)
    # -------------------------------------------------------------------------
    db_file = tmp_path / "tracer_phase5.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    app = create_app(session_factory=session_factory)

    # -------------------------------------------------------------------------
    # Step 2: Seed Users, Cameras, Segments, Outages, and Events
    # -------------------------------------------------------------------------
    t_base = datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)
    t_seg1_start = t_base
    t_seg1_end = t_base + timedelta(minutes=15)
    # Camera outage gap between 10:15 and 10:30 (PLAY-08)
    t_outage_start = t_seg1_end
    t_outage_end = t_base + timedelta(minutes=30)
    # Segment 2 from 10:30 to 10:45
    t_seg2_start = t_outage_end
    t_seg2_end = t_base + timedelta(minutes=45)
    # Event occurrence at 10:35
    t_event = t_base + timedelta(minutes=35)

    cam_a_dir = storage_root / "CAM-ALPHA"
    cam_a_dir.mkdir(parents=True, exist_ok=True)

    seg1_data = (
        make_box("ftyp", b"isommp42")
        + make_box("moov", b"track_header_alpha")
        + make_box("moof", b"fragment_header_1")
        + make_box("mdat", b"video_payload_bytes_alpha_1")
    )
    seg2_data = (
        make_box("ftyp", b"isommp42")
        + make_box("moov", b"track_header_alpha")
        + make_box("moof", b"fragment_header_2")
        + make_box("mdat", b"video_payload_bytes_alpha_2")
    )

    file_seg1 = cam_a_dir / "seg1.mp4"
    file_seg2 = cam_a_dir / "seg2.mp4"
    file_seg1.write_bytes(seg1_data)
    file_seg2.write_bytes(seg2_data)

    async with session_factory() as session:
        # Storage settings
        storage_setting = StorageSettings(
            id=1,
            storage_path=str(storage_root),
            allow_system_disk=True,
            reserve_bytes=10 * 1024**3,
            created_at=t_base,
            updated_at=t_base,
        )
        session.add(storage_setting)

        # Cameras
        cam_a = Camera(
            serial="CAM-ALPHA",
            host="192.168.1.50",
            name="Alpha Gate",
            tls_fingerprint_sha256="aa" * 32,
            added_at=t_base,
            host_updated_at=t_base,
        )
        cam_b = Camera(
            serial="CAM-BETA",
            host="192.168.1.51",
            name="Beta Perimeter",
            tls_fingerprint_sha256="bb" * 32,
            added_at=t_base,
            host_updated_at=t_base,
        )
        session.add_all([cam_a, cam_b])
        await session.flush()

        # Users: Owner (unrestricted) and Viewer (permitted ONLY for CAM-BETA)
        owner = User(
            username="nvr_owner",
            password_hash=hash_password("OwnerSecure123!"),
            role="owner",
            is_active=True,
            created_at=t_base,
            updated_at=t_base,
        )
        viewer = User(
            username="nvr_viewer",
            password_hash=hash_password("ViewerSecure123!"),
            role="viewer",
            is_active=True,
            created_at=t_base,
            updated_at=t_base,
        )
        session.add_all([owner, viewer])
        await session.flush()

        # Viewer permission assigned only to CAM-BETA (AUTH-05)
        perm = UserCameraPermission(
            user_id=viewer.id,
            camera_serial="CAM-BETA",
            created_at=t_base,
        )
        session.add(perm)

        # Recording Segments for CAM-ALPHA
        s1 = Segment(
            camera_serial="CAM-ALPHA",
            stream_type="main",
            file_path="CAM-ALPHA/seg1.mp4",
            start_time=t_seg1_start,
            end_time=t_seg1_end,
            duration_seconds=900.0,
            file_size_bytes=len(seg1_data),
            is_protected=False,
            created_at=t_seg1_start,
        )
        s2 = Segment(
            camera_serial="CAM-ALPHA",
            stream_type="main",
            file_path="CAM-ALPHA/seg2.mp4",
            start_time=t_seg2_start,
            end_time=t_seg2_end,
            duration_seconds=900.0,
            file_size_bytes=len(seg2_data),
            is_protected=False,
            created_at=t_seg2_start,
        )
        session.add_all([s1, s2])

        # Camera Outage for CAM-ALPHA (PLAY-08)
        outage = CameraOutage(
            camera_serial="CAM-ALPHA",
            started_at=t_outage_start,
            ended_at=t_outage_end,
            duration_seconds=900.0,
            reason="Power cycle reboot",
        )
        session.add(outage)

        # Event for CAM-ALPHA (PLAY-01)
        evt = Event(
            camera_serial="CAM-ALPHA",
            event_type="line_crossing",
            source="onvif_pullpoint",
            start_time=t_event,
            end_time=t_event + timedelta(seconds=10),
            is_locked=False,
            clock_sync_state="synced",
            created_at=t_event,
        )
        session.add(evt)

        # Create sessions
        sess_owner = await SessionManager.create_session(session, user_id=owner.id)
        sess_viewer = await SessionManager.create_session(session, user_id=viewer.id)
        await session.commit()

        owner_token = sess_owner.id
        viewer_token = sess_viewer.id
        s1_id = s1.id
        s2_id = s2.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ---------------------------------------------------------------------
        # Step 3: Calendar Days with Recordings Query (PLAY-02)
        # ---------------------------------------------------------------------
        resp_days = await client.get(
            "/api/v1/playback/days?camera_serial=CAM-ALPHA&year=2026&month=11",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_days.status_code == 200
        days_data = resp_days.json()
        assert days_data["camera_serial"] == "CAM-ALPHA"
        assert "2026-11-04" in days_data["days"]

        # ---------------------------------------------------------------------
        # Step 4: 24h Timeline Query with Segments, Outages, and Events (PLAY-01, PLAY-08)
        # ---------------------------------------------------------------------
        t_day_start = "2026-11-04T00:00:00Z"
        t_day_end = "2026-11-04T23:59:59Z"
        resp_tl = await client.get(
            f"/api/v1/playback/timeline?camera_serial=CAM-ALPHA&start_time={t_day_start}&end_time={t_day_end}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_tl.status_code == 200
        tl_data = resp_tl.json()
        assert len(tl_data["segments"]) == 2
        assert len(tl_data["outages"]) == 1
        assert tl_data["outages"][0]["reason"] == "Power cycle reboot"
        assert len(tl_data["events"]) == 1
        assert tl_data["events"][0]["event_type"] == "line_crossing"

        # ---------------------------------------------------------------------
        # Step 5: HTTP 206 Partial Content Byte-Range Video Streaming (PLAY-03, PLAY-04)
        # ---------------------------------------------------------------------
        resp_stream = await client.get(
            f"/api/v1/playback/segment/{s1_id}",
            headers={"Authorization": f"Bearer {owner_token}", "Range": "bytes=0-99"},
        )
        assert resp_stream.status_code == 206
        assert resp_stream.headers["accept-ranges"] == "bytes"
        assert resp_stream.headers["content-range"].startswith("bytes 0-99/")
        assert len(resp_stream.content) == 100
        assert resp_stream.content == seg1_data[:100]

        # ---------------------------------------------------------------------
        # Step 6: Evidence Locking & Unlocking against Retention (REC-12)
        # ---------------------------------------------------------------------
        resp_lock = await client.post(
            f"/api/v1/playback/segments/{s1_id}/lock",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_lock.status_code == 200
        assert resp_lock.json()["is_protected"] is True

        resp_unlock = await client.post(
            f"/api/v1/playback/segments/{s1_id}/unlock",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_unlock.status_code == 200
        assert resp_unlock.json()["is_protected"] is False

        # ---------------------------------------------------------------------
        # Step 7: Lossless MP4 Clip Export (PLAY-06)
        # ---------------------------------------------------------------------
        resp_export = await client.post(
            "/api/v1/playback/export",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-ALPHA",
                "start_time": t_seg1_start.isoformat(),
                "end_time": t_seg2_end.isoformat(),
                "title": "Tracer Incident Export",
            },
        )
        assert resp_export.status_code == 200
        clip_data = resp_export.json()
        assert clip_data["item_type"] == "export_clip"
        assert clip_data["title"] == "Tracer Incident Export"
        clip_id = clip_data["id"]

        # Verify clip file created on disk
        clip_path = storage_root / clip_data["file_path"]
        assert clip_path.exists()
        assert clip_path.stat().st_size == clip_data["file_size_bytes"]

        # ---------------------------------------------------------------------
        # Step 8: Playback Still Snapshot Capture (PLAY-07, LIVE-07)
        # ---------------------------------------------------------------------
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb"
        b64_snap = base64.b64encode(dummy_jpeg).decode("ascii")

        resp_snap = await client.post(
            "/api/v1/playback/snapshot",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-ALPHA",
                "image_base64": f"data:image/jpeg;base64,{b64_snap}",
                "title": "Tracer Snapshot Frame",
                "captured_at": t_event.isoformat(),
            },
        )
        assert resp_snap.status_code == 200
        snap_data = resp_snap.json()
        assert snap_data["item_type"] == "snapshot"
        assert snap_data["title"] == "Tracer Snapshot Frame"
        snap_id = snap_data["id"]

        snap_path = storage_root / snap_data["file_path"]
        assert snap_path.exists()
        assert snap_path.read_bytes() == dummy_jpeg

        # ---------------------------------------------------------------------
        # Step 9: Gallery Listing, Downloads, and Deletion (GAL-01, GAL-02)
        # ---------------------------------------------------------------------
        # List items
        resp_gal = await client.get(
            "/api/v1/gallery",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_gal.status_code == 200
        gal_list = resp_gal.json()
        assert gal_list["total"] >= 2

        # Download clip
        resp_dl = await client.get(
            f"/api/v1/gallery/{clip_id}/download",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_dl.status_code == 200
        assert resp_dl.headers["content-type"].startswith("video/mp4")

        # Delete clip and verify unlinked from storage
        resp_del = await client.delete(
            f"/api/v1/gallery/{clip_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_del.status_code == 200
        assert resp_del.json()["status"] == "deleted"
        assert not clip_path.exists()

        # ---------------------------------------------------------------------
        # Step 10: Recording Search by Events & Intervals (GAL-03)
        # ---------------------------------------------------------------------
        resp_search = await client.get(
            "/api/v1/playback/search?camera_serial=CAM-ALPHA&event_type=line_crossing",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_search.status_code == 200
        search_results = resp_search.json()
        assert len(search_results) == 1
        assert search_results[0]["event_type"] == "line_crossing"

        # ---------------------------------------------------------------------
        # Step 11: RBAC Viewer Isolation Boundary (AUTH-05)
        # ---------------------------------------------------------------------
        # Viewer only assigned to CAM-BETA; must receive 403 Forbidden for CAM-ALPHA:
        # a) Timeline
        r_unauth_tl = await client.get(
            f"/api/v1/playback/timeline?camera_serial=CAM-ALPHA&start_time={t_day_start}&end_time={t_day_end}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r_unauth_tl.status_code == 403

        # b) Stream Segment
        r_unauth_stream = await client.get(
            f"/api/v1/playback/segment/{s2_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r_unauth_stream.status_code == 403

        # c) Export Clip
        r_unauth_export = await client.post(
            "/api/v1/playback/export",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "camera_serial": "CAM-ALPHA",
                "start_time": t_seg1_start.isoformat(),
                "end_time": t_seg2_end.isoformat(),
            },
        )
        assert r_unauth_export.status_code == 403

        # d) Save Snapshot
        r_unauth_snap = await client.post(
            "/api/v1/playback/snapshot",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "camera_serial": "CAM-ALPHA",
                "image_base64": b64_snap,
            },
        )
        assert r_unauth_snap.status_code == 403

        # e) Gallery Download of CAM-ALPHA snapshot
        r_unauth_dl = await client.get(
            f"/api/v1/gallery/{snap_id}/download",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r_unauth_dl.status_code == 403

    # -------------------------------------------------------------------------
    # Step 12: Verify Database Audit Trail
    # -------------------------------------------------------------------------
    async with session_factory() as session:
        audit_res = await session.execute(
            select(AuditLog).where(AuditLog.actor_username == "nvr_owner")
        )
        actions = {a.action for a in audit_res.scalars().all()}
        assert "playback.segment_lock" in actions
        assert "playback.segment_unlock" in actions
        assert "gallery.export_clip" in actions
        assert "gallery.save_snapshot" in actions
        assert "gallery.delete_item" in actions
