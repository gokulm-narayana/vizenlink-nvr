"""Integration tests for MP4 clip export engine and snapshot capture service (PLAY-06, PLAY-07, LIVE-07)."""

from __future__ import annotations

import base64
import os
import struct
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import (
    AuditLog,
    Base,
    Camera,
    GalleryItem,
    Segment,
    StorageSettings,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.media.clip_exporter import ClipExporter, parse_isobmff_boxes
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


def make_box(box_type: str, payload: bytes = b"") -> bytes:
    """Helper to build an ISOBMFF box with big-endian 4-byte size header."""
    size = 8 + len(payload)
    return struct.pack(">I", size) + box_type.encode("ascii") + payload


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_clip_export.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    # Build synthetic fMP4 segments
    cam_dir = storage_root / "CAM-EXPORT"
    cam_dir.mkdir(parents=True, exist_ok=True)

    seg1_data = (
        make_box("ftyp", b"isommp42")
        + make_box("moov", b"track_header_meta")
        + make_box("moof", b"fragment_header_1")
        + make_box("mdat", b"video_payload_bytes_1")
    )
    seg2_data = (
        make_box("ftyp", b"isommp42")
        + make_box("moov", b"track_header_meta")
        + make_box("moof", b"fragment_header_2")
        + make_box("mdat", b"video_payload_bytes_2")
    )

    file1 = cam_dir / "seg1.mp4"
    file2 = cam_dir / "seg2.mp4"
    file1.write_bytes(seg1_data)
    file2.write_bytes(seg2_data)

    now = utc_now()
    t1 = now - timedelta(minutes=10)
    t2 = now - timedelta(minutes=5)
    t3 = now

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

        # Users: Owner and Viewer
        owner = User(
            username="export_owner",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="export_viewer",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer.permissions.append(
            UserCameraPermission(
                camera_serial="CAM-OTHER",
                created_at=now,
            )
        )

        # Cameras
        cam_export = Camera(
            serial="CAM-EXPORT",
            host="192.168.1.100",
            https_port=443,
            mac="AA:BB:CC:DD:EE:01",
            name="Export Camera",
            tls_fingerprint_sha256="aa" * 32,
            added_at=now,
            host_updated_at=now,
        )
        cam_other = Camera(
            serial="CAM-OTHER",
            host="192.168.1.101",
            https_port=443,
            mac="AA:BB:CC:DD:EE:02",
            name="Other Camera",
            tls_fingerprint_sha256="bb" * 32,
            added_at=now,
            host_updated_at=now,
        )

        session.add_all([owner, viewer, cam_export, cam_other])
        await session.flush()

        # Recording segments for CAM-EXPORT
        s1 = Segment(
            camera_serial="CAM-EXPORT",
            stream_type="main",
            file_path="CAM-EXPORT/seg1.mp4",
            start_time=t1,
            end_time=t2,
            duration_seconds=300.0,
            file_size_bytes=len(seg1_data),
            is_protected=False,
            created_at=t1,
        )
        s2 = Segment(
            camera_serial="CAM-EXPORT",
            stream_type="main",
            file_path="CAM-EXPORT/seg2.mp4",
            start_time=t2,
            end_time=t3,
            duration_seconds=300.0,
            file_size_bytes=len(seg2_data),
            is_protected=False,
            created_at=t2,
        )
        session.add_all([s1, s2])

        owner_session = await SessionManager.create_session(
            session,
            user_id=owner.id,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
        viewer_session = await SessionManager.create_session(
            session,
            user_id=viewer.id,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
        await session.commit()

        owner_token = owner_session.id
        viewer_token = viewer_session.id

    return {
        "app": app,
        "storage_root": storage_root,
        "session_factory": session_factory,
        "owner_token": owner_token,
        "viewer_token": viewer_token,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "seg1_file": file1,
        "seg2_file": file2,
    }


def test_clip_exporter_lossless_concatenation(tmp_path: Path):
    """Test pure ClipExporter ISOBMFF concatenation and atomic temp-then-rename."""
    seg1 = (
        make_box("ftyp", b"isommp42")
        + make_box("moov", b"header_metadata")
        + make_box("moof", b"f1")
        + make_box("mdat", b"payload1")
    )
    seg2 = (
        make_box("ftyp", b"isommp42")
        + make_box("moov", b"header_metadata")
        + make_box("moof", b"f2")
        + make_box("mdat", b"payload2")
    )

    f1 = tmp_path / "s1.mp4"
    f2 = tmp_path / "s2.mp4"
    f1.write_bytes(seg1)
    f2.write_bytes(seg2)

    out_file = tmp_path / "exported" / "clip.mp4"
    res = ClipExporter.export_fmp4_clip([f1, f2], out_file)

    assert res == out_file
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    if os.name == "posix":
        assert (out_file.stat().st_mode & 0o777) == 0o640

    # Ensure no leftover temp files exist
    parent_files = list(out_file.parent.iterdir())
    assert len(parent_files) == 1
    assert parent_files[0].name == "clip.mp4"

    # Verify ISOBMFF box structure
    boxes = parse_isobmff_boxes(out_file.read_bytes())
    box_types = [b[0] for b in boxes]
    # Header from first segment + fragments from all segments
    assert box_types == ["ftyp", "moov", "moof", "mdat", "moof", "mdat"]


def test_clip_exporter_invalid_inputs(tmp_path: Path):
    """Test ClipExporter with empty or missing segment files."""
    with pytest.raises(ValueError, match="No segment files provided"):
        ClipExporter.export_fmp4_clip([], tmp_path / "out.mp4")

    non_existent = tmp_path / "missing.mp4"
    with pytest.raises(ValueError, match="None of the provided segment files exist"):
        ClipExporter.export_fmp4_clip([non_existent], tmp_path / "out.mp4")


@pytest.mark.asyncio
async def test_api_export_clip_workflow(app_fixture):
    """Test POST /api/v1/playback/export creates clip, DB record, and audit log."""
    app = app_fixture["app"]
    owner_token = app_fixture["owner_token"]
    viewer_token = app_fixture["viewer_token"]
    t1 = app_fixture["t1"]
    t3 = app_fixture["t3"]
    session_factory = app_fixture["session_factory"]
    storage_root = app_fixture["storage_root"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer access denied to CAM-EXPORT (AUTH-05)
        resp_denied = await client.post(
            "/api/v1/playback/export",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "start_time": t1.isoformat(),
                "end_time": t3.isoformat(),
                "title": "Unauthorized Clip",
            },
        )
        assert resp_denied.status_code == 403

        # Invalid time range: end_time <= start_time
        resp_bad_range = await client.post(
            "/api/v1/playback/export",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "start_time": t3.isoformat(),
                "end_time": t1.isoformat(),
            },
        )
        assert resp_bad_range.status_code == 400

        # Successful export
        resp_export = await client.post(
            "/api/v1/playback/export",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "start_time": t1.isoformat(),
                "end_time": t3.isoformat(),
                "title": "Incident Investigation Clip",
            },
        )
        assert resp_export.status_code == 200
        data = resp_export.json()
        assert data["camera_serial"] == "CAM-EXPORT"
        assert data["item_type"] == "export_clip"
        assert data["title"] == "Incident Investigation Clip"
        assert data["file_size_bytes"] > 0
        assert data["file_path"].startswith("gallery/clips/cam-export/")

        # Verify file exists on disk
        clip_file = storage_root / data["file_path"]
        assert clip_file.exists()
        assert clip_file.stat().st_size == data["file_size_bytes"]

    # Verify database item and audit log
    async with session_factory() as session:
        item = await session.get(GalleryItem, data["id"])
        assert item is not None
        assert item.item_type == "export_clip"
        assert item.title == "Incident Investigation Clip"

        audit_stmt = select(AuditLog).where(
            AuditLog.action == "gallery.export_clip",
            AuditLog.resource_id == str(item.id),
        )
        audit_res = await session.execute(audit_stmt)
        audit_event = audit_res.scalar_one_or_none()
        assert audit_event is not None
        assert audit_event.actor_username == "export_owner"


@pytest.mark.asyncio
async def test_api_save_snapshot_workflow(app_fixture):
    """Test POST /api/v1/playback/snapshot saves JPEG, DB record, and audit log."""
    app = app_fixture["app"]
    owner_token = app_fixture["owner_token"]
    viewer_token = app_fixture["viewer_token"]
    session_factory = app_fixture["session_factory"]
    storage_root = app_fixture["storage_root"]

    # Synthetic valid JPEG (starts with \xFF\xD8\xFF)
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb"
    b64_jpeg = base64.b64encode(jpeg_bytes).decode("ascii")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer access denied to CAM-EXPORT (AUTH-05)
        resp_denied = await client.post(
            "/api/v1/playback/snapshot",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "image_base64": b64_jpeg,
                "title": "Viewer Snapshot",
            },
        )
        assert resp_denied.status_code == 403

        # Non-JPEG bytes
        bad_bytes = b"NOT_A_JPEG_DATA"
        bad_b64 = base64.b64encode(bad_bytes).decode("ascii")
        resp_invalid_jpeg = await client.post(
            "/api/v1/playback/snapshot",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "image_base64": bad_b64,
            },
        )
        assert resp_invalid_jpeg.status_code == 400

        # Successful snapshot save (with data:image/jpeg;base64 prefix)
        data_url_b64 = f"data:image/jpeg;base64,{b64_jpeg}"
        resp_snap = await client.post(
            "/api/v1/playback/snapshot",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "image_base64": data_url_b64,
                "title": "Perimeter Intrusion Frame",
            },
        )
        assert resp_snap.status_code == 200
        snap_data = resp_snap.json()
        assert snap_data["camera_serial"] == "CAM-EXPORT"
        assert snap_data["item_type"] == "snapshot"
        assert snap_data["title"] == "Perimeter Intrusion Frame"
        assert snap_data["file_size_bytes"] == len(jpeg_bytes)
        assert snap_data["file_path"].startswith("gallery/snapshots/cam-export/")

        # Verify file exists on disk with correct permissions
        snap_file = storage_root / snap_data["file_path"]
        assert snap_file.exists()
        assert snap_file.read_bytes() == jpeg_bytes
        if os.name == "posix":
            assert (snap_file.stat().st_mode & 0o777) == 0o640

    # Verify database item and audit log
    async with session_factory() as session:
        item = await session.get(GalleryItem, snap_data["id"])
        assert item is not None
        assert item.item_type == "snapshot"
        assert item.title == "Perimeter Intrusion Frame"

        audit_stmt = select(AuditLog).where(
            AuditLog.action == "gallery.save_snapshot",
            AuditLog.resource_id == str(item.id),
        )
        audit_res = await session.execute(audit_stmt)
        audit_event = audit_res.scalar_one_or_none()
        assert audit_event is not None
        assert audit_event.actor_username == "export_owner"


@pytest.mark.asyncio
async def test_api_manual_clip_workflow(app_fixture):
    """Test POST /api/v1/playback/manual-clip creates manual_clip item, file, and audit log."""
    app = app_fixture["app"]
    owner_token = app_fixture["owner_token"]
    viewer_token = app_fixture["viewer_token"]
    t1 = app_fixture["t1"]
    t3 = app_fixture["t3"]
    session_factory = app_fixture["session_factory"]
    storage_root = app_fixture["storage_root"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer access denied to CAM-EXPORT (AUTH-05)
        resp_denied = await client.post(
            "/api/v1/playback/manual-clip",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "start_time": t1.isoformat(),
                "end_time": t3.isoformat(),
            },
        )
        assert resp_denied.status_code == 403

        # Invalid time range
        resp_bad = await client.post(
            "/api/v1/playback/manual-clip",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "start_time": t3.isoformat(),
                "end_time": t1.isoformat(),
            },
        )
        assert resp_bad.status_code == 400

        # Manual clip assembled from recording segments
        resp_seg = await client.post(
            "/api/v1/playback/manual-clip",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-EXPORT",
                "start_time": t1.isoformat(),
                "end_time": t3.isoformat(),
                "title": "Live Manual Clip",
            },
        )
        assert resp_seg.status_code == 200
        seg_data = resp_seg.json()
        assert seg_data["item_type"] == "manual_clip"
        assert seg_data["title"] == "Live Manual Clip"
        assert seg_data["file_path"].startswith("gallery/clips/cam-export/")
        seg_file = storage_root / seg_data["file_path"]
        assert seg_file.exists()
        assert seg_file.stat().st_size == seg_data["file_size_bytes"]

        # Manual clip uploaded via video_base64 fallback on camera without segments
        raw_mp4 = make_box("ftyp", b"isommp42") + make_box("mdat", b"live_bytes")
        b64_mp4 = base64.b64encode(raw_mp4).decode("ascii")
        resp_b64 = await client.post(
            "/api/v1/playback/manual-clip",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-OTHER",
                "start_time": t1.isoformat(),
                "end_time": t3.isoformat(),
                "video_base64": f"data:video/mp4;base64,{b64_mp4}",
            },
        )
        assert resp_b64.status_code == 200
        b64_data = resp_b64.json()
        assert b64_data["item_type"] == "manual_clip"
        assert (storage_root / b64_data["file_path"]).read_bytes() == raw_mp4

        # Unknown camera with no segments -> 404
        resp_missing = await client.post(
            "/api/v1/playback/manual-clip",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "camera_serial": "CAM-UNKNOWN",
                "start_time": t1.isoformat(),
                "end_time": t3.isoformat(),
            },
        )
        assert resp_missing.status_code == 404

    async with session_factory() as session:
        item = await session.get(GalleryItem, seg_data["id"])
        assert item is not None
        assert item.item_type == "manual_clip"

        audit_stmt = select(AuditLog).where(
            AuditLog.action == "gallery.manual_clip",
            AuditLog.resource_id == str(item.id),
        )
        audit_event = (await session.execute(audit_stmt)).scalar_one_or_none()
        assert audit_event is not None
        assert audit_event.actor_username == "export_owner"
