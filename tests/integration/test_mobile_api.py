"""Integration tests for Mobile LAN Integration REST API (MOB-03 through MOB-07)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import (
    Base,
    Camera,
    RecordingSettings,
    Segment,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    """Setup in-memory SQLite database, seed test data, and configure FastAPI test client."""
    db_path = tmp_path / "test_mobile_api.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    now = utc_now()

    async with session_factory() as session:
        # 1. Users
        owner = User(
            username="mobile_owner",
            password_hash=hash_password("OwnerSecret123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="mobile_viewer",
            password_hash=hash_password("ViewerSecret123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add_all([owner, viewer])
        await session.flush()

        # 2. Camera with recording settings
        cam1 = Camera(
            serial="CAM-MOB-1",
            host="192.168.1.50",
            https_port=443,
            mac="11:22:33:44:55:66",
            name="Front Gate",
            tls_fingerprint_sha256="",
            state="active",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-MOB-2",
            host="192.168.1.51",
            https_port=443,
            mac="11:22:33:44:55:77",
            name="Back Yard",
            tls_fingerprint_sha256="",
            state="active",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])
        await session.flush()

        rec1 = RecordingSettings(
            camera_serial="CAM-MOB-1",
            mode="continuous",
            schedule_json="{}",
            audio_enabled=True,
            updated_at=now,
        )
        session.add(rec1)

        # Viewer only has access to CAM-MOB-1
        perm = UserCameraPermission(
            user_id=viewer.id,
            camera_serial="CAM-MOB-1",
            created_at=now,
        )
        session.add(perm)

        # 3. Segments for today
        seg1 = Segment(
            camera_serial="CAM-MOB-1",
            stream_type="main",
            file_path="/storage/cam1/2026/11/04/seg1.mp4",
            start_time=now - timedelta(minutes=10),
            end_time=now - timedelta(minutes=5),
            duration_seconds=300.0,
            file_size_bytes=10485760,
            status="active",
            is_protected=False,
            created_at=now,
        )
        seg2 = Segment(
            camera_serial="CAM-MOB-1",
            stream_type="main",
            file_path="/storage/cam1/2026/11/04/seg2.mp4",
            start_time=now - timedelta(minutes=5),
            end_time=now,
            duration_seconds=300.0,
            file_size_bytes=10485760,
            status="active",
            is_protected=True,
            created_at=now,
        )
        session.add_all([seg1, seg2])

        await session.commit()

        # Web session tokens for test setup
        owner_sess = await SessionManager.create_session(session, owner.id)
        viewer_sess = await SessionManager.create_session(session, viewer.id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "session_factory": session_factory,
            "owner_cookie": f"session_id={owner_sess.id}",
            "viewer_cookie": f"session_id={viewer_sess.id}",
        }

    await engine.dispose()


@pytest.mark.asyncio
async def test_mobile_pairing_and_token_rotation(app_fixture: dict[str, Any]) -> None:
    """Test direct credential pairing, QR code pairing, refresh, and revocation (MOB-03)."""
    client: httpx.AsyncClient = app_fixture["client"]
    owner_cookie: str = app_fixture["owner_cookie"]

    # 1. Direct credential pairing
    res_pair = await client.post(
        "/api/v1/mobile/pair",
        json={
            "username": "mobile_owner",
            "password": "OwnerSecret123!",
            "device_id": "phone-alpha",
            "device_name": "Owner's iPhone",
            "platform": "ios",
        },
    )
    assert res_pair.status_code == 200, res_pair.text
    data_pair = res_pair.json()
    assert data_pair["device_id"] == "phone-alpha"
    access_token = data_pair["access_token"]
    refresh_token = data_pair["refresh_token"]
    assert data_pair["user"]["role"] == "owner"

    # 2. Token refresh
    res_refresh = await client.post(
        "/api/v1/mobile/refresh",
        json={"refresh_token": refresh_token},
    )
    assert res_refresh.status_code == 200, res_refresh.text
    new_access_token = res_refresh.json()["access_token"]
    assert new_access_token != access_token

    # 3. Use new mobile token with Bearer authentication
    headers = {"Authorization": f"Bearer {new_access_token}"}
    res_auth = await client.get("/api/v1/mobile/status", headers=headers)
    assert res_auth.status_code == 200, res_auth.text
    assert res_auth.json()["status"] in ("healthy", "ready", "ok", "degraded")

    # 4. QR pairing flow
    res_init_qr = await client.post(
        "/api/v1/mobile/qr/init",
        headers={"Cookie": owner_cookie},
    )
    assert res_init_qr.status_code == 200, res_init_qr.text
    pairing_code = res_init_qr.json()["pairing_code"]

    res_claim_qr = await client.post(
        "/api/v1/mobile/pair-qr",
        json={
            "pairing_code": pairing_code,
            "device_id": "tablet-beta",
            "device_name": "Owner's iPad",
            "platform": "ios",
        },
    )
    assert res_claim_qr.status_code == 200, res_claim_qr.text
    assert res_claim_qr.json()["device_id"] == "tablet-beta"

    # 5. List paired devices
    res_devs = await client.get("/api/v1/mobile/devices", headers=headers)
    assert res_devs.status_code == 200, res_devs.text
    dev_list = res_devs.json()
    assert len(dev_list) >= 2
    dev_alpha = next(d for d in dev_list if d["device_id"] == "phone-alpha")
    assert dev_alpha["is_revoked"] is False

    # 6. Revoke phone-alpha
    res_rev = await client.post(
        f"/api/v1/mobile/devices/{dev_alpha['id']}/revoke",
        headers={"Cookie": owner_cookie},
    )
    assert res_rev.status_code == 200, res_rev.text
    assert res_rev.json()["revoked"] is True

    # 7. Access with revoked token is immediately rejected with 401
    res_blocked = await client.get("/api/v1/mobile/status", headers=headers)
    assert res_blocked.status_code == 401, res_blocked.text


@pytest.mark.asyncio
async def test_mobile_live_stream_relay(app_fixture: dict[str, Any]) -> None:
    """Test mobile live streaming relay defaulting to sub stream (MOB-04)."""
    client: httpx.AsyncClient = app_fixture["client"]

    # Pair a device for viewer
    res_pair = await client.post(
        "/api/v1/mobile/pair",
        json={
            "username": "mobile_viewer",
            "password": "ViewerSecret123!",
            "device_id": "viewer-phone",
            "device_name": "Viewer Phone",
            "platform": "android",
        },
    )
    headers = {"Authorization": f"Bearer {res_pair.json()['access_token']}"}

    # 1. Fetch live stream for permitted camera (defaults to sub stream)
    res_sub = await client.get("/api/v1/mobile/cameras/CAM-MOB-1/live-stream", headers=headers)
    assert res_sub.status_code == 200, res_sub.text
    data_sub = res_sub.json()
    assert data_sub["camera_serial"] == "CAM-MOB-1"
    assert data_sub["profile"] == "sub"
    assert "token" in data_sub
    assert "/cam/CAM-MOB-1/sub/whep?token=" in data_sub["webrtc_url"]
    assert "/cam/CAM-MOB-1/sub/index.m3u8?token=" in data_sub["hls_url"]
    assert "rtsp://" in data_sub["rtsp_url"]

    # 2. Explicit main stream request
    res_main = await client.get(
        "/api/v1/mobile/cameras/CAM-MOB-1/live-stream?profile=main", headers=headers
    )
    assert res_main.status_code == 200, res_main.text
    assert res_main.json()["profile"] == "main"

    # 3. Unpermitted camera access is forbidden (HTTP 403)
    res_forbidden = await client.get(
        "/api/v1/mobile/cameras/CAM-MOB-2/live-stream", headers=headers
    )
    assert res_forbidden.status_code == 403, res_forbidden.text


@pytest.mark.asyncio
async def test_mobile_recordings_history(app_fixture: dict[str, Any]) -> None:
    """Test calendar dates and daily recording spans retrieval (MOB-05)."""
    client: httpx.AsyncClient = app_fixture["client"]
    owner_cookie: str = app_fixture["owner_cookie"]
    headers = {"Cookie": owner_cookie}

    now = utc_now()
    today_str = now.strftime("%Y-%m-%d")

    # 1. Fetch dates with footage
    res_dates = await client.get(
        f"/api/v1/mobile/cameras/CAM-MOB-1/recording-dates?year={now.year}&month={now.month}",
        headers=headers,
    )
    assert res_dates.status_code == 200, res_dates.text
    dates = res_dates.json()["dates"]
    assert today_str in dates

    # 2. Fetch clips for today
    res_clips = await client.get(
        f"/api/v1/mobile/cameras/CAM-MOB-1/recordings?date={today_str}",
        headers=headers,
    )
    assert res_clips.status_code == 200, res_clips.text
    clips = res_clips.json()["recordings"]
    assert len(clips) == 2
    assert clips[0]["trigger"] == "continuous"
    assert clips[1]["trigger"] == "event"
    assert "/api/v1/playback/stream/" in clips[0]["stream_url"]


@pytest.mark.asyncio
async def test_mobile_status_and_camera_management(app_fixture: dict[str, Any]) -> None:
    """Test mobile status telemetry and RBAC on camera operations (MOB-06, MOB-07)."""
    client: httpx.AsyncClient = app_fixture["client"]

    # 1. Pair Owner device
    res_owner_pair = await client.post(
        "/api/v1/mobile/pair",
        json={
            "username": "mobile_owner",
            "password": "OwnerSecret123!",
            "device_id": "owner-device-mgr",
            "device_name": "Admin Mobile",
            "platform": "ios",
        },
    )
    owner_headers = {"Authorization": f"Bearer {res_owner_pair.json()['access_token']}"}

    # 2. Pair Viewer device
    res_viewer_pair = await client.post(
        "/api/v1/mobile/pair",
        json={
            "username": "mobile_viewer",
            "password": "ViewerSecret123!",
            "device_id": "viewer-device-mgr",
            "device_name": "Viewer Mobile",
            "platform": "android",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {res_viewer_pair.json()['access_token']}"}

    # 3. Status summary
    res_status = await client.get("/api/v1/mobile/status", headers=owner_headers)
    assert res_status.status_code == 200, res_status.text
    status_data = res_status.json()
    assert "storage" in status_data
    assert len(status_data["cameras"]) == 2
    cam1 = next(c for c in status_data["cameras"] if c["serial"] == "CAM-MOB-1")
    assert cam1["is_online"] is True
    assert cam1["recording_mode"] == "continuous"

    # 4. Owner updates recording mode
    res_mode = await client.put(
        "/api/v1/mobile/cameras/CAM-MOB-1/recording-mode",
        json={"mode": "event"},
        headers=owner_headers,
    )
    assert res_mode.status_code == 200, res_mode.text
    assert res_mode.json()["mode"] == "event"

    # 5. Viewer attempts to update recording mode -> Forbidden (HTTP 403)
    res_mode_refused = await client.put(
        "/api/v1/mobile/cameras/CAM-MOB-1/recording-mode",
        json={"mode": "continuous"},
        headers=viewer_headers,
    )
    assert res_mode_refused.status_code == 403, res_mode_refused.text

    # 6. Owner adds camera from mobile
    res_add = await client.post(
        "/api/v1/mobile/cameras",
        json={
            "serial": "CAM-MOB-NEW",
            "name": "Side Yard",
            "host": "192.168.1.99",
            "https_port": 443,
        },
        headers=owner_headers,
    )
    assert res_add.status_code == 201, res_add.text
    assert res_add.json()["created"] is True

    # 7. Viewer attempts to delete camera -> Forbidden (HTTP 403)
    res_del_refused = await client.delete(
        "/api/v1/mobile/cameras/CAM-MOB-NEW",
        headers=viewer_headers,
    )
    assert res_del_refused.status_code == 403, res_del_refused.text

    # 8. Owner deletes camera
    res_del = await client.delete(
        "/api/v1/mobile/cameras/CAM-MOB-NEW",
        headers=owner_headers,
    )
    assert res_del.status_code == 200, res_del.text
    assert res_del.json()["deleted"] is True
