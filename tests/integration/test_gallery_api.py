"""Integration tests for Gallery REST API, media downloads, deletion, and RBAC (GAL-01, GAL-02, AUTH-05)."""

from __future__ import annotations

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
    StorageSettings,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_gallery_api.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    # Create dummy snapshot & clip files on disk
    snap_dir = storage_root / "gallery" / "snapshots" / "cam-gal-1" / "2026" / "11" / "04"
    clip_dir = storage_root / "gallery" / "clips" / "cam-gal-1" / "2026" / "11" / "04"
    snap_dir.mkdir(parents=True, exist_ok=True)
    clip_dir.mkdir(parents=True, exist_ok=True)

    snap_file = snap_dir / "test_snap.jpg"
    clip_file = clip_dir / "test_clip.mp4"
    snap_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb"
    clip_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    snap_file.write_bytes(snap_bytes)
    clip_file.write_bytes(clip_bytes)

    # Second camera files (for RBAC testing)
    snap_dir2 = storage_root / "gallery" / "snapshots" / "cam-gal-2" / "2026" / "11" / "04"
    snap_dir2.mkdir(parents=True, exist_ok=True)
    snap_file2 = snap_dir2 / "test_snap2.jpg"
    snap_file2.write_bytes(snap_bytes)

    now = utc_now()
    t1 = now - timedelta(hours=2)
    t2 = now - timedelta(hours=1)
    t3 = now

    async with session_factory() as session:
        storage_setting = StorageSettings(
            id=1,
            storage_path=str(storage_root),
            allow_system_disk=True,
            reserve_bytes=10 * 1024**3,
            created_at=now,
            updated_at=now,
        )
        session.add(storage_setting)

        # Users: Owner, Operator, Viewer
        owner = User(
            username="gallery_owner",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        operator = User(
            username="gallery_operator",
            password_hash=hash_password("OperatorPassword123!"),
            role="operator",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="gallery_viewer",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        # Viewer only has access to CAM-GAL-1
        viewer.permissions.append(
            UserCameraPermission(
                camera_serial="CAM-GAL-1",
                created_at=now,
            )
        )

        cam1 = Camera(
            serial="CAM-GAL-1",
            host="192.168.1.10",
            https_port=443,
            mac="AA:BB:CC:DD:EE:11",
            name="Gallery Cam 1",
            tls_fingerprint_sha256="11" * 32,
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-GAL-2",
            host="192.168.1.11",
            https_port=443,
            mac="AA:BB:CC:DD:EE:22",
            name="Gallery Cam 2",
            tls_fingerprint_sha256="22" * 32,
            added_at=now,
            host_updated_at=now,
        )

        session.add_all([owner, operator, viewer, cam1, cam2])
        await session.flush()

        item1 = GalleryItem(
            camera_serial="CAM-GAL-1",
            item_type="snapshot",
            title="Front Door Motion",
            file_path="gallery/snapshots/cam-gal-1/2026/11/04/test_snap.jpg",
            file_size_bytes=len(snap_bytes),
            duration_seconds=None,
            captured_at=t1,
            user_id=owner.id,
            created_at=t1,
        )
        item2 = GalleryItem(
            camera_serial="CAM-GAL-1",
            item_type="export_clip",
            title="Front Door 5m Clip",
            file_path="gallery/clips/cam-gal-1/2026/11/04/test_clip.mp4",
            file_size_bytes=len(clip_bytes),
            duration_seconds=300.0,
            captured_at=t2,
            user_id=owner.id,
            created_at=t2,
        )
        item3 = GalleryItem(
            camera_serial="CAM-GAL-2",
            item_type="snapshot",
            title="Back Yard Intrusion",
            file_path="gallery/snapshots/cam-gal-2/2026/11/04/test_snap2.jpg",
            file_size_bytes=len(snap_bytes),
            duration_seconds=None,
            captured_at=t3,
            user_id=owner.id,
            created_at=t3,
        )
        session.add_all([item1, item2, item3])

        owner_session = await SessionManager.create_session(session, user_id=owner.id)
        operator_session = await SessionManager.create_session(session, user_id=operator.id)
        viewer_session = await SessionManager.create_session(session, user_id=viewer.id)
        await session.commit()

        owner_token = owner_session.id
        operator_token = operator_session.id
        viewer_token = viewer_session.id
        item1_id = item1.id
        item2_id = item2.id
        item3_id = item3.id

    return {
        "app": app,
        "storage_root": storage_root,
        "session_factory": session_factory,
        "owner_token": owner_token,
        "operator_token": operator_token,
        "viewer_token": viewer_token,
        "item1_id": item1_id,
        "item2_id": item2_id,
        "item3_id": item3_id,
        "snap_bytes": snap_bytes,
        "clip_bytes": clip_bytes,
        "snap_file": snap_file,
    }


@pytest.mark.asyncio
async def test_gallery_query_and_filtering(app_fixture):
    """Test GET /api/v1/gallery with filters, pagination, and RBAC scoping."""
    app = app_fixture["app"]
    owner_token = app_fixture["owner_token"]
    viewer_token = app_fixture["viewer_token"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Owner lists all items
        resp_all = await client.get(
            "/api/v1/gallery",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_all.status_code == 200
        data = resp_all.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

        # Filter by item_type=snapshot
        resp_snaps = await client.get(
            "/api/v1/gallery?item_type=snapshot",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_snaps.status_code == 200
        data_snaps = resp_snaps.json()
        assert data_snaps["total"] == 2
        assert all(i["item_type"] == "snapshot" for i in data_snaps["items"])

        # Filter by camera_serial=CAM-GAL-1
        resp_cam1 = await client.get(
            "/api/v1/gallery?camera_serial=CAM-GAL-1",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_cam1.status_code == 200
        assert resp_cam1.json()["total"] == 2

        # Viewer queries all: should only see items for CAM-GAL-1 (2 items, item3 excluded)
        resp_viewer = await client.get(
            "/api/v1/gallery",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp_viewer.status_code == 200
        viewer_items = resp_viewer.json()["items"]
        assert len(viewer_items) == 2
        assert all(i["camera_serial"] == "CAM-GAL-1" for i in viewer_items)

        # Viewer explicitly querying unauthorized camera CAM-GAL-2 -> 403 Forbidden
        resp_unauth = await client.get(
            "/api/v1/gallery?camera_serial=CAM-GAL-2",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp_unauth.status_code == 403


@pytest.mark.asyncio
async def test_gallery_item_detail_and_download(app_fixture):
    """Test GET /api/v1/gallery/{id} and download endpoint with MIME typing and RBAC."""
    app = app_fixture["app"]
    owner_token = app_fixture["owner_token"]
    viewer_token = app_fixture["viewer_token"]
    item1_id = app_fixture["item1_id"]
    item2_id = app_fixture["item2_id"]
    item3_id = app_fixture["item3_id"]
    snap_bytes = app_fixture["snap_bytes"]
    clip_bytes = app_fixture["clip_bytes"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get item detail
        resp_detail = await client.get(
            f"/api/v1/gallery/{item1_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_detail.status_code == 200
        assert resp_detail.json()["title"] == "Front Door Motion"

        # Download snapshot: returns image/jpeg
        resp_snap_dl = await client.get(
            f"/api/v1/gallery/{item1_id}/download",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_snap_dl.status_code == 200
        assert resp_snap_dl.headers["content-type"].startswith("image/jpeg")
        assert resp_snap_dl.content == snap_bytes

        # Download clip: returns video/mp4
        resp_clip_dl = await client.get(
            f"/api/v1/gallery/{item2_id}/download",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_clip_dl.status_code == 200
        assert resp_clip_dl.headers["content-type"].startswith("video/mp4")
        assert resp_clip_dl.content == clip_bytes

        # Viewer can download permitted camera item
        resp_viewer_ok = await client.get(
            f"/api/v1/gallery/{item1_id}/download",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp_viewer_ok.status_code == 200

        # Viewer cannot download unpermitted camera item (item3 on CAM-GAL-2)
        resp_viewer_denied = await client.get(
            f"/api/v1/gallery/{item3_id}/download",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp_viewer_denied.status_code == 403


@pytest.mark.asyncio
async def test_gallery_item_deletion_and_rbac(app_fixture):
    """Test DELETE /api/v1/gallery/{id} requires Operator role, unlinks file, and creates audit log."""
    app = app_fixture["app"]
    operator_token = app_fixture["operator_token"]
    viewer_token = app_fixture["viewer_token"]
    item1_id = app_fixture["item1_id"]
    snap_file = app_fixture["snap_file"]
    session_factory = app_fixture["session_factory"]

    assert snap_file.exists()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer attempting deletion -> 403 Forbidden
        resp_viewer_del = await client.delete(
            f"/api/v1/gallery/{item1_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp_viewer_del.status_code == 403
        assert snap_file.exists()

        # Operator deletes item
        resp_op_del = await client.delete(
            f"/api/v1/gallery/{item1_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp_op_del.status_code == 200
        assert resp_op_del.json() == {"status": "deleted", "id": item1_id}

        # Verify file is deleted on disk
        assert not snap_file.exists()

        # Verify 404 when querying deleted item
        resp_not_found = await client.get(
            f"/api/v1/gallery/{item1_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp_not_found.status_code == 404

    # Verify DB record removed and audit log created
    async with session_factory() as session:
        item = await session.get(GalleryItem, item1_id)
        assert item is None

        audit_stmt = select(AuditLog).where(
            AuditLog.action == "gallery.delete_item",
            AuditLog.resource_id == str(item1_id),
        )
        audit_res = await session.execute(audit_stmt)
        audit_entry = audit_res.scalar_one_or_none()
        assert audit_entry is not None
        assert audit_entry.actor_username == "gallery_operator"
