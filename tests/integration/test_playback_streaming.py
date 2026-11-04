"""Integration tests for HTTP 206 Byte-Range streaming and MediaMTX playback auth."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import (
    Base,
    Camera,
    Segment,
    StorageSettings,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.media_token import default_media_token_service
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_playback_streaming.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    storage_root = tmp_path / "recordings"
    storage_root.mkdir(parents=True, exist_ok=True)

    # Create dummy video file on disk: 10,000 bytes
    dummy_video_bytes = b"\x00" * 10000
    cam_dir = storage_root / "CAM-STREAM"
    cam_dir.mkdir(parents=True, exist_ok=True)
    video_file = cam_dir / "test_seg.mp4"
    video_file.write_bytes(dummy_video_bytes)

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

        # Users: Owner and Viewer
        owner = User(
            username="stream_owner",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="stream_viewer",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        # Viewer only has access to CAM-OTHER
        viewer.permissions.append(
            UserCameraPermission(camera_serial="CAM-OTHER", created_at=now)
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
            serial="CAM-STREAM",
            host="192.168.1.30",
            name="Stream Cam",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-OTHER",
            host="192.168.1.31",
            name="Other Cam",
            tls_fingerprint_sha256="",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])

        # Segment for CAM-STREAM
        seg = Segment(
            id=501,
            camera_serial="CAM-STREAM",
            stream_type="main",
            start_time=now - timedelta(minutes=5),
            end_time=now,
            duration_seconds=300.0,
            file_path=str(video_file),
            file_size_bytes=10000,
            status="active",
            is_protected=False,
            created_at=now - timedelta(minutes=5),
        )
        session.add(seg)
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_session, viewer_session, owner.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_segment_full_streaming(app_fixture):
    client, owner_session, _, _ = app_fixture

    resp = await client.get(
        "/api/v1/playback/segment/501",
        headers={"Authorization": f"Bearer {owner_session}"},
    )
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-length"] == "10000"
    assert len(resp.content) == 10000


@pytest.mark.asyncio
async def test_segment_byte_range_streaming(app_fixture):
    client, owner_session, _, _ = app_fixture

    # Range: bytes=0-1023 (first 1024 bytes)
    resp = await client.get(
        "/api/v1/playback/segment/501",
        headers={
            "Authorization": f"Bearer {owner_session}",
            "Range": "bytes=0-1023",
        },
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 0-1023/10000"
    assert resp.headers["content-length"] == "1024"
    assert len(resp.content) == 1024

    # Range: bytes=5000- (from byte 5000 to end)
    resp = await client.get(
        "/api/v1/playback/segment/501",
        headers={
            "Authorization": f"Bearer {owner_session}",
            "Range": "bytes=5000-",
        },
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 5000-9999/10000"
    assert resp.headers["content-length"] == "5000"
    assert len(resp.content) == 5000

    # Out of bounds range
    resp_invalid = await client.get(
        "/api/v1/playback/segment/501",
        headers={
            "Authorization": f"Bearer {owner_session}",
            "Range": "bytes=20000-30000",
        },
    )
    assert resp_invalid.status_code == 416


@pytest.mark.asyncio
async def test_segment_streaming_viewer_scoping(app_fixture):
    client, _, viewer_session, _ = app_fixture

    # Viewer does not have access to CAM-STREAM -> 403
    resp = await client.get(
        "/api/v1/playback/segment/501",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp.status_code == 403

    # Non-existent segment -> 404
    resp_missing = await client.get(
        "/api/v1/playback/segment/9999",
        headers={"Authorization": f"Bearer {viewer_session}"},
    )
    assert resp_missing.status_code == 404


@pytest.mark.asyncio
async def test_mediamtx_playback_auth_webhook(app_fixture):
    client, _, _, owner_id = app_fixture

    # Generate media token for playback
    valid_token = default_media_token_service.generate_token(
        user_id=owner_id,
        camera_serial="CAM-STREAM",
        stream="main",
        ttl_seconds=900,
    )

    # MediaMTX sends action="playback"
    resp = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "127.0.0.1",
            "user": "",
            "password": "",
            "path": "cam/CAM-STREAM/main",
            "protocol": "playback",
            "id": "play-session-1",
            "action": "playback",
            "query": f"token={valid_token}",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Missing token -> 401
    resp_missing = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "127.0.0.1",
            "user": "",
            "password": "",
            "path": "cam/CAM-STREAM/main",
            "protocol": "playback",
            "id": "play-session-2",
            "action": "playback",
            "query": "",
        },
    )
    assert resp_missing.status_code == 401
