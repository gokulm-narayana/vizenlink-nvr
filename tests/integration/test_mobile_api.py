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
    # WHEP goes through the authenticated /cam proxy on the API's own host:port,
    # never straight to the loopback-only MediaMTX port.
    assert data_sub["webrtc_url"].startswith("http://test/cam/CAM-MOB-1/sub/whep?token=")
    assert ":8889" not in data_sub["webrtc_url"]
    assert data_sub["hls_url"] == f"http://test/cam/CAM-MOB-1/sub/hls/{data_sub['token']}/index.m3u8"
    assert ":8888" not in data_sub["hls_url"]
    assert ":8889" not in data_sub["hls_url"]
    assert data_sub["rtsp_url"] is None

    # The returned proxy URL authorises the same viewer (permission check uses the serial's case).
    from vizenlink_nvr.api import cam_proxy

    async def _fake_proxy(*_args: Any, **_kwargs: Any) -> Any:
        from fastapi import Response

        return Response(status_code=201, content=b"v=0", media_type="application/sdp")

    original = cam_proxy._proxy_request
    cam_proxy._proxy_request = _fake_proxy  # type: ignore[assignment]
    try:
        whep_path = data_sub["webrtc_url"].removeprefix("http://test")
        res_whep = await client.post(
            whep_path,
            content=b"v=0",
            headers={**headers, "Content-Type": "application/sdp"},
        )
    finally:
        cam_proxy._proxy_request = original  # type: ignore[assignment]
    assert res_whep.status_code == 201, res_whep.text

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
    assert clips[0]["stream_url"] == f"/api/v1/playback/segment/{clips[0]['id']}"


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

    # 6. Owner adds camera from mobile — goes through the same onboarding as the web UI.
    from vizenlink_nvr.api.v1 import mobile as mobile_module

    seen: dict[str, Any] = {}

    async def _fake_onboard(payload: Any, user: Any, request: Any, db: Any) -> Any:
        seen["host"] = str(payload.host)
        seen["password"] = payload.password.get_secret_value()
        cam = Camera(
            serial="CAM-MOB-NEW",
            name="Side Yard",
            host=str(payload.host),
            https_port=payload.port,
            tls_fingerprint_sha256="ab" * 32,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )
        db.add(cam)
        await db.commit()
        return cam

    original_onboard = mobile_module.onboard_discovered_camera
    mobile_module.onboard_discovered_camera = _fake_onboard  # type: ignore[assignment]
    try:
        res_add = await client.post(
            "/api/v1/mobile/cameras",
            json={"host": "192.168.1.99", "port": 443, "username": "admin", "password": "CamPass123!"},
            headers=owner_headers,
        )
    finally:
        mobile_module.onboard_discovered_camera = original_onboard  # type: ignore[assignment]
    assert res_add.status_code == 201, res_add.text
    assert res_add.json() == {"serial": "CAM-MOB-NEW", "name": "Side Yard", "created": True}
    assert seen == {"host": "192.168.1.99", "password": "CamPass123!"}

    # 6b. No silent default password any more: a missing password is rejected up front.
    res_add_nopw = await client.post(
        "/api/v1/mobile/cameras",
        json={"host": "192.168.1.99", "username": "admin"},
        headers=owner_headers,
    )
    assert res_add_nopw.status_code == 422, res_add_nopw.text

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


@pytest.mark.asyncio
async def test_qr_payload_carries_nvr_address(app_fixture: dict[str, Any]) -> None:
    """The QR the web UI shows tells the phone which NVR to redeem it against."""
    client: httpx.AsyncClient = app_fixture["client"]
    res = await client.post("/api/v1/mobile/qr/init", headers={"Cookie": app_fixture["owner_cookie"]})
    assert res.status_code == 200, res.text
    payload = res.json()["qr_payload"]
    assert payload.startswith("vizenlink://pair?code=")
    assert payload.endswith("&host=test&port=80&scheme=http")


@pytest.mark.asyncio
async def test_snapshot_of_recorded_moment(app_fixture: dict[str, Any], tmp_path: Path) -> None:
    """Playback 'Snapshot' grabs the frame at a time from the recording and saves it to the gallery."""
    from vizenlink_nvr.api.v1 import mobile as mobile_module
    from vizenlink_nvr.db.models import StorageSettings

    client: httpx.AsyncClient = app_fixture["client"]
    async with app_fixture["session_factory"]() as session:
        session.add(StorageSettings(storage_path=str(tmp_path), updated_at=utc_now()))
        await session.commit()

    grabbed: dict[str, Any] = {}

    def _fake_grab(path: Path, offset: float) -> bytes:
        grabbed["path"] = str(path)
        grabbed["offset"] = offset
        return b"\xff\xd8\xff\xe0fake-jpeg"

    original = mobile_module._extract_frame_jpeg
    mobile_module._extract_frame_jpeg = _fake_grab  # type: ignore[assignment]
    try:
        at = utc_now() - timedelta(minutes=8)  # inside seg1 (10..5 minutes ago)
        res = await client.post(
            "/api/v1/mobile/cameras/CAM-MOB-1/snapshot-at",
            json={"at": at.isoformat()},
            headers={"Cookie": app_fixture["owner_cookie"]},
        )
        assert res.status_code == 201, res.text
        assert res.json()["item_type"] == "snapshot"
        assert grabbed["path"].endswith("seg1.mp4")
        assert 115 < grabbed["offset"] < 125

        # Nothing recorded at that time -> 404 with a readable message.
        res_none = await client.post(
            "/api/v1/mobile/cameras/CAM-MOB-1/snapshot-at",
            json={"at": (utc_now() - timedelta(days=3)).isoformat()},
            headers={"Cookie": app_fixture["owner_cookie"]},
        )
        assert res_none.status_code == 404
    finally:
        mobile_module._extract_frame_jpeg = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_exact_clip_cuts_the_requested_range(app_fixture: dict[str, Any], tmp_path: Path) -> None:
    """9:01-9:02 style request -> a clip of exactly that length, across a file boundary."""
    import json
    import shutil
    import subprocess

    from vizenlink_nvr.db.models import StorageSettings

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        pytest.skip("ffmpeg not installed")

    client: httpx.AsyncClient = app_fixture["client"]
    base = utc_now().replace(microsecond=0) - timedelta(hours=1)
    seg_files = []
    for i in range(2):
        out = tmp_path / f"seg{i}.mp4"
        subprocess.run(  # noqa: S603, ASYNC221 - test fixture setup
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
             "testsrc=size=320x180:rate=10", "-t", "6", "-pix_fmt", "yuv420p", "-y", str(out)],
            check=True,
        )
        seg_files.append(out)

    async with app_fixture["session_factory"]() as session:
        session.add(StorageSettings(storage_path=str(tmp_path), updated_at=utc_now()))
        for i, f in enumerate(seg_files):
            session.add(
                Segment(
                    camera_serial="CAM-MOB-1",
                    stream_type="main",
                    file_path=str(f),
                    start_time=base + timedelta(seconds=6 * i),
                    end_time=base + timedelta(seconds=6 * (i + 1)),
                    duration_seconds=6.0,
                    file_size_bytes=f.stat().st_size,
                    status="active",
                    is_protected=False,
                    created_at=utc_now(),
                )
            )
        await session.commit()

    headers = {"Cookie": app_fixture["owner_cookie"]}
    res = await client.post(
        "/api/v1/mobile/cameras/CAM-MOB-1/clip",
        json={
            "start": (base + timedelta(seconds=4)).isoformat(),
            "end": (base + timedelta(seconds=9)).isoformat(),
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    item = res.json()
    assert item["item_type"] == "export_clip"
    assert item["duration_seconds"] == pytest.approx(5.0)

    clip_path = tmp_path / item["file_path"]
    probe = subprocess.run(  # noqa: S603, ASYNC221 - test assertion
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(clip_path)],
        capture_output=True,
        check=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert 4.7 <= duration <= 5.3

    # The phone plays/shares it through the gallery download with its token.
    res_dl = await client.get(f"/api/v1/gallery/{item['id']}/download", headers=headers)
    assert res_dl.status_code == 200
    assert res_dl.headers["content-type"].startswith("video/")


@pytest.mark.asyncio
async def test_exact_clip_rejects_bad_ranges(app_fixture: dict[str, Any]) -> None:
    client: httpx.AsyncClient = app_fixture["client"]
    headers = {"Cookie": app_fixture["owner_cookie"]}
    now = utc_now()
    backwards = await client.post(
        "/api/v1/mobile/cameras/CAM-MOB-1/clip",
        json={"start": now.isoformat(), "end": (now - timedelta(seconds=5)).isoformat()},
        headers=headers,
    )
    assert backwards.status_code == 400
    too_long = await client.post(
        "/api/v1/mobile/cameras/CAM-MOB-1/clip",
        json={"start": now.isoformat(), "end": (now + timedelta(minutes=11)).isoformat()},
        headers=headers,
    )
    assert too_long.status_code == 400
    nothing = await client.post(
        "/api/v1/mobile/cameras/CAM-MOB-1/clip",
        json={
            "start": (now - timedelta(days=3)).isoformat(),
            "end": (now - timedelta(days=3) + timedelta(seconds=30)).isoformat(),
        },
        headers=headers,
    )
    assert nothing.status_code == 404


@pytest.mark.asyncio
async def test_qr_init_from_localhost_resolves_lan_ip(
    app_fixture: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When accessed from localhost, qr/init embeds the host LAN IP instead of dropping server info."""
    client: httpx.AsyncClient = app_fixture["client"]
    monkeypatch.setattr("vizenlink_nvr.api.v1.mobile.get_local_ip", lambda: "192.168.50.10")

    res = await client.post(
        "http://localhost:8000/api/v1/mobile/qr/init",
        headers={"Cookie": app_fixture["owner_cookie"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["server_url"] == "http://192.168.50.10:8000"
    assert body["qr_payload"].endswith("&host=192.168.50.10&port=8000&scheme=http")


@pytest.mark.asyncio
async def test_mobile_pair_rate_limiting(app_fixture: dict[str, Any]) -> None:
    """Repeated bad credential pairing attempts trigger HTTP 429 lockout."""
    from vizenlink_nvr.services.rate_limiter import login_rate_limiter

    client: httpx.AsyncClient = app_fixture["client"]
    for ident in ("pair_rate_user", "127.0.0.1", "testclient"):
        login_rate_limiter.reset(ident)
    try:
        statuses: list[int] = []
        for _ in range(7):
            res = await client.post(
                "/api/v1/mobile/pair",
                json={
                    "username": "pair_rate_user",
                    "password": "WrongPassword!",
                    "device_id": "brute-phone",
                    "device_name": "Brute Phone",
                    "platform": "android",
                },
            )
            statuses.append(res.status_code)
            if res.status_code == 429:
                break
        assert 401 in statuses
        assert statuses[-1] == 429
    finally:
        for ident in ("pair_rate_user", "127.0.0.1", "testclient"):
            login_rate_limiter.reset(ident)


@pytest.mark.asyncio
async def test_web_auth_lifecycle_revokes_mobile_tokens(app_fixture: dict[str, Any]) -> None:
    """Auth logout, sign-out-others, and password change also revoke paired mobile devices."""
    client: httpx.AsyncClient = app_fixture["client"]

    async def _pair_owner(dev_id: str, pw: str = "OwnerSecret123!") -> str:
        res = await client.post(
            "/api/v1/mobile/pair",
            json={
                "username": "mobile_owner",
                "password": pw,
                "device_id": dev_id,
                "device_name": f"Device {dev_id}",
                "platform": "android",
            },
        )
        assert res.status_code == 200, res.text
        return str(res.json()["access_token"])

    # 1. /auth/logout with mobile Bearer revokes that mobile token
    tok_logout = await _pair_owner("phone-logout")
    res_logout = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tok_logout}"},
    )
    assert res_logout.status_code == 200
    assert (
        await client.get("/api/v1/mobile/status", headers={"Authorization": f"Bearer {tok_logout}"})
    ).status_code == 401

    # 2. /auth/sessions/sign-out-others revokes other paired mobile tokens
    tok_other = await _pair_owner("phone-other")
    res_signout = await client.post(
        "/api/v1/auth/sessions/sign-out-others",
        headers={"Cookie": app_fixture["owner_cookie"]},
    )
    assert res_signout.status_code == 200
    assert res_signout.json()["revoked"] >= 1
    assert (
        await client.get("/api/v1/mobile/status", headers={"Authorization": f"Bearer {tok_other}"})
    ).status_code == 401

    # 3. /auth/password revokes all paired mobile tokens for that user
    tok_pw = await _pair_owner("phone-pw")
    res_pw = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "OwnerSecret123!", "new_password": "NewOwnerSecret456!"},
        headers={"Cookie": app_fixture["owner_cookie"]},
    )
    assert res_pw.status_code == 200
    # Clear the fresh web session cookie that /auth/password sets on the test client
    # so the check strictly exercises the paired mobile Bearer token.
    client.cookies.clear()
    assert (
        await client.get("/api/v1/mobile/status", headers={"Authorization": f"Bearer {tok_pw}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_mobile_status_reflects_recorder_and_camera_state(app_fixture: dict[str, Any]) -> None:
    """Mobile status checks real recorder MediaMTX status, camera online state, and recording mode."""
    client: httpx.AsyncClient = app_fixture["client"]
    owner_headers = {"Cookie": app_fixture["owner_cookie"]}
    app = app_fixture["client"]._transport.app

    class StubRecorder:
        def __init__(self, running: bool) -> None:
            self._running = running

        def status(self) -> dict[str, Any]:
            return {"mediamtx_running": self._running}

    async with app_fixture["session_factory"]() as session:
        cam2 = await session.get(Camera, "CAM-MOB-2")
        assert cam2 is not None
        cam2.state = "unreachable"
        rec2 = await session.get(RecordingSettings, "CAM-MOB-2")
        if rec2 is None:
            session.add(
                RecordingSettings(
                    camera_serial="CAM-MOB-2",
                    mode="continuous",
                    schedule_json="{}",
                    audio_enabled=False,
                    updated_at=utc_now(),
                )
            )
        await session.commit()

    app.state.recorder = StubRecorder(running=False)
    try:
        res = await client.get("/api/v1/mobile/status", headers=owner_headers)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "degraded"
        cam1 = next(c for c in data["cameras"] if c["serial"] == "CAM-MOB-1")
        cam2_item = next(c for c in data["cameras"] if c["serial"] == "CAM-MOB-2")
        assert cam1["is_recording"] is False
        assert cam2_item["is_online"] is False
        assert cam2_item["is_recording"] is False
    finally:
        app.state.recorder = None


@pytest.mark.asyncio
async def test_mobile_timezone_playback_and_signed_segment_streaming(
    app_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Calendar dates & day queries follow site_timezone and signed_stream_url streams without headers."""
    from datetime import UTC, datetime

    from vizenlink_nvr.db.models import StorageSettings
    from vizenlink_nvr.services.settings import SITE_TIMEZONE_KEY, put_setting

    client: httpx.AsyncClient = app_fixture["client"]
    owner_headers = {"Cookie": app_fixture["owner_cookie"]}

    seg_file = tmp_path / "ist_night.mp4"
    seg_bytes = b"ftypisom_mobile_segment_payload"
    seg_file.write_bytes(seg_bytes)

    # 2026-11-18T20:00:00Z is 2026-11-19 01:30:00 in Asia/Kolkata (+05:30).
    start_utc = datetime(2026, 11, 18, 20, 0, 0, tzinfo=UTC)
    end_utc = datetime(2026, 11, 18, 20, 5, 0, tzinfo=UTC)

    async with app_fixture["session_factory"]() as session:
        await put_setting(session, SITE_TIMEZONE_KEY, "Asia/Kolkata")
        session.add(
            StorageSettings(
                id=1,
                storage_path=str(tmp_path),
                allow_system_disk=True,
                updated_at=utc_now(),
            )
        )
        session.add(
            Segment(
                id=9001,
                camera_serial="CAM-MOB-1",
                stream_type="main",
                file_path=str(seg_file),
                start_time=start_utc,
                end_time=end_utc,
                duration_seconds=300.0,
                file_size_bytes=len(seg_bytes),
                status="active",
                is_protected=False,
                created_at=utc_now(),
            )
        )
        await session.commit()

    # Local date 2026-11-19 appears in recording-dates; 2026-11-18 has none of our 20:00Z segment.
    res_dates = await client.get(
        "/api/v1/mobile/cameras/CAM-MOB-1/recording-dates?year=2026&month=11",
        headers=owner_headers,
    )
    assert res_dates.status_code == 200, res_dates.text
    assert "2026-11-19" in res_dates.json()["dates"]

    res_recs = await client.get(
        "/api/v1/mobile/cameras/CAM-MOB-1/recordings?date=2026-11-19",
        headers=owner_headers,
    )
    assert res_recs.status_code == 200, res_recs.text
    match = next(r for r in res_recs.json()["recordings"] if r["id"] == 9001)
    assert match["stream_url"] == "/api/v1/playback/segment/9001"
    assert match["signed_stream_url"].startswith("http://test/api/v1/playback/segment/9001?token=")

    # Signed stream URL streams cleanly with NO cookie or Authorization header
    signed_path = match["signed_stream_url"].removeprefix("http://test")
    res_stream = await client.get(signed_path)
    assert res_stream.status_code == 200
    assert res_stream.content == seg_bytes

    # Unauthenticated request without token returns 401 (never 404 existence leak)
    assert (await client.get("/api/v1/playback/segment/999999")).status_code == 401
