"""Phase 7 end-to-end integration tracer for Mobile LAN Integration (MOB-02 through MOB-07).

Validates:
- MOB-02: mDNS zero-configuration LAN service discovery and DNS-SD TXT properties.
- MOB-03: Secure device pairing via QR-code and credentials, token refresh, and administrative revocation.
- MOB-04: Mobile live streaming relay defaulting to low-bandwidth sub-stream with signed media tokens.
- MOB-05: Mobile recorded history browsing via calendar dates and timeline segment spans.
- MOB-06: Mobile health and storage telemetry aggregation.
- MOB-07: Mobile camera management and recording mode alteration with server-side RBAC enforcement.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

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
from vizenlink_nvr.network.mdns import SERVICE_TYPE, NvrMdnsAdvertiser
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_phase7_complete_e2e_tracer(tmp_path: Path) -> None:
    """Full end-to-end tracer exercising all Mobile LAN Integration requirements."""
    db_path = tmp_path / "phase7_tracer.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    now = utc_now()
    today_str = now.strftime("%Y-%m-%d")

    # ---------------------------------------------------------------------------
    # Step 1: Verify mDNS Service Advertisement (MOB-02)
    # ---------------------------------------------------------------------------
    mock_zc = MagicMock()
    advertiser = NvrMdnsAdvertiser(
        nvr_id="vizenlink-tracer-nvr",
        name="Tracer NVR",
        port=8000,
        ip_address="192.168.1.150",
        tls=False,
        api_version="v1",
        zeroconf_instance=mock_zc,
    )
    assert advertiser.start() is True
    assert advertiser.is_running is True
    info = advertiser.service_info
    assert info is not None
    assert info.type == SERVICE_TYPE
    assert info.name == "Tracer NVR._vizenlink-nvr._tcp.local."
    props = {k.decode("utf-8"): v.decode("utf-8") for k, v in info.properties.items()}
    assert props["api_version"] == "v1"
    assert props["nvr_id"] == "vizenlink-tracer-nvr"
    assert props["model"] == "VizenLink-NVR"
    assert props["port"] == "8000"
    mock_zc.register_service.assert_called_once_with(info)

    # ---------------------------------------------------------------------------
    # Seed Database: Owner, Viewer, Cameras, Recording Settings, Segments
    # ---------------------------------------------------------------------------
    async with session_factory() as session:
        owner = User(
            username="tracer_owner",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="tracer_viewer",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add_all([owner, viewer])
        await session.flush()

        cam1 = Camera(
            serial="CAM-P7-FRONT",
            host="192.168.1.200",
            https_port=443,
            mac="00:11:22:33:44:01",
            name="Front Gate Camera",
            tls_fingerprint_sha256="",
            state="active",
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-P7-BACK",
            host="192.168.1.201",
            https_port=443,
            mac="00:11:22:33:44:02",
            name="Back Yard Camera",
            tls_fingerprint_sha256="",
            state="active",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])
        await session.flush()

        rec1 = RecordingSettings(
            camera_serial="CAM-P7-FRONT",
            mode="continuous",
            schedule_json="{}",
            audio_enabled=True,
            updated_at=now,
        )
        session.add(rec1)

        # Viewer only has permission to CAM-P7-FRONT
        perm = UserCameraPermission(
            user_id=viewer.id,
            camera_serial="CAM-P7-FRONT",
            created_at=now,
        )
        session.add(perm)

        # Record segments for CAM-P7-FRONT
        seg_c = Segment(
            camera_serial="CAM-P7-FRONT",
            stream_type="main",
            file_path="/storage/cam1/2026/11/04/seg_c.mp4",
            start_time=now - timedelta(minutes=15),
            end_time=now - timedelta(minutes=10),
            duration_seconds=300.0,
            file_size_bytes=15728640,
            status="active",
            is_protected=False,
            created_at=now,
        )
        seg_e = Segment(
            camera_serial="CAM-P7-FRONT",
            stream_type="main",
            file_path="/storage/cam1/2026/11/04/seg_e.mp4",
            start_time=now - timedelta(minutes=10),
            end_time=now - timedelta(minutes=5),
            duration_seconds=300.0,
            file_size_bytes=15728640,
            status="active",
            is_protected=True,
            created_at=now,
        )
        session.add_all([seg_c, seg_e])
        await session.commit()

        owner_sess = await SessionManager.create_session(session, owner.id)

    owner_cookie = f"session_id={owner_sess.id}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ---------------------------------------------------------------------------
        # Step 2: Device Pairing Flow (MOB-03)
        # ---------------------------------------------------------------------------

        # 2a. QR-code initiation from web session
        res_qr_init = await client.post(
            "/api/v1/mobile/qr/init",
            headers={"Cookie": owner_cookie},
        )
        assert res_qr_init.status_code == 200, res_qr_init.text
        pairing_code = res_qr_init.json()["pairing_code"]
        assert len(pairing_code) == 32

        # 2b. Claim QR code from Phone A (iOS)
        res_pair_qr = await client.post(
            "/api/v1/mobile/pair-qr",
            json={
                "pairing_code": pairing_code,
                "device_id": "iphone-15-tracer",
                "device_name": "Gokul's iPhone 15",
                "platform": "ios",
            },
        )
        assert res_pair_qr.status_code == 200, res_pair_qr.text
        phone_a_data = res_pair_qr.json()
        token_a = phone_a_data["access_token"]
        refresh_a = phone_a_data["refresh_token"]
        assert phone_a_data["user"]["role"] == "owner"

        # 2c. Direct credential pairing from Phone B (Android, Viewer role)
        res_pair_cred = await client.post(
            "/api/v1/mobile/pair",
            json={
                "username": "tracer_viewer",
                "password": "ViewerPassword123!",
                "device_id": "pixel-8-tracer",
                "device_name": "Guard Pixel 8",
                "platform": "android",
            },
        )
        assert res_pair_cred.status_code == 200, res_pair_cred.text
        phone_b_data = res_pair_cred.json()
        token_b = phone_b_data["access_token"]
        assert phone_b_data["user"]["role"] == "viewer"

        # 2d. Token rotation / refresh for Phone A
        res_ref = await client.post(
            "/api/v1/mobile/refresh",
            json={"refresh_token": refresh_a},
        )
        assert res_ref.status_code == 200, res_ref.text
        new_token_a = res_ref.json()["access_token"]
        assert new_token_a != token_a

        headers_a = {"Authorization": f"Bearer {new_token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # ---------------------------------------------------------------------------
        # Step 3: Mobile Live Streaming Relay (MOB-04)
        # ---------------------------------------------------------------------------
        res_live = await client.get(
            "/api/v1/mobile/cameras/CAM-P7-FRONT/live-stream",
            headers=headers_a,
        )
        assert res_live.status_code == 200, res_live.text
        live_data = res_live.json()
        assert live_data["camera_serial"] == "CAM-P7-FRONT"
        # Defaults to sub-stream for mobile
        assert live_data["profile"] == "sub"
        assert "/cam/CAM-P7-FRONT/sub/whep?token=" in live_data["webrtc_url"]
        assert "/cam/CAM-P7-FRONT/sub/index.m3u8?token=" in live_data["hls_url"]
        assert "rtsp://" in live_data["rtsp_url"]

        # Viewer cannot access unpermitted camera CAM-P7-BACK
        res_unpermitted = await client.get(
            "/api/v1/mobile/cameras/CAM-P7-BACK/live-stream",
            headers=headers_b,
        )
        assert res_unpermitted.status_code == 403, res_unpermitted.text

        # ---------------------------------------------------------------------------
        # Step 4: Mobile Recorded History & Timeline Browsing (MOB-05)
        # ---------------------------------------------------------------------------
        res_dates = await client.get(
            f"/api/v1/mobile/cameras/CAM-P7-FRONT/recording-dates?year={now.year}&month={now.month}",
            headers=headers_a,
        )
        assert res_dates.status_code == 200, res_dates.text
        assert today_str in res_dates.json()["dates"]

        res_recordings = await client.get(
            f"/api/v1/mobile/cameras/CAM-P7-FRONT/recordings?date={today_str}",
            headers=headers_a,
        )
        assert res_recordings.status_code == 200, res_recordings.text
        recs = res_recordings.json()["recordings"]
        assert len(recs) == 2
        assert recs[0]["trigger"] == "continuous"
        assert recs[1]["trigger"] == "event"
        assert "/api/v1/playback/stream/" in recs[0]["stream_url"]

        # ---------------------------------------------------------------------------
        # Step 5: Mobile Health & Storage Telemetry (MOB-06)
        # ---------------------------------------------------------------------------
        res_status = await client.get("/api/v1/mobile/status", headers=headers_a)
        assert res_status.status_code == 200, res_status.text
        status_info = res_status.json()
        assert "status" in status_info
        assert "storage" in status_info
        assert len(status_info["cameras"]) == 2
        cam_front = next(c for c in status_info["cameras"] if c["serial"] == "CAM-P7-FRONT")
        assert cam_front["is_online"] is True
        assert cam_front["is_recording"] is True
        assert cam_front["storage_used_bytes"] > 0

        # ---------------------------------------------------------------------------
        # Step 6: Mobile Camera Management & RBAC Enforcement (MOB-07)
        # ---------------------------------------------------------------------------
        # 6a. Owner alters recording mode
        res_mode = await client.put(
            "/api/v1/mobile/cameras/CAM-P7-FRONT/recording-mode",
            json={"mode": "event"},
            headers=headers_a,
        )
        assert res_mode.status_code == 200, res_mode.text
        assert res_mode.json()["mode"] == "event"

        # 6b. Viewer attempts to alter recording mode -> HTTP 403 Forbidden
        res_mode_forbidden = await client.put(
            "/api/v1/mobile/cameras/CAM-P7-FRONT/recording-mode",
            json={"mode": "continuous"},
            headers=headers_b,
        )
        assert res_mode_forbidden.status_code == 403, res_mode_forbidden.text

        # 6c. Owner adds camera from mobile
        res_add_cam = await client.post(
            "/api/v1/mobile/cameras",
            json={
                "serial": "CAM-P7-NEW",
                "name": "Side Garden",
                "host": "192.168.1.205",
            },
            headers=headers_a,
        )
        assert res_add_cam.status_code == 201, res_add_cam.text

        # 6d. Viewer attempts to delete camera -> HTTP 403 Forbidden
        res_del_forbidden = await client.delete(
            "/api/v1/mobile/cameras/CAM-P7-NEW",
            headers=headers_b,
        )
        assert res_del_forbidden.status_code == 403, res_del_forbidden.text

        # 6e. Owner deletes camera
        res_del_ok = await client.delete(
            "/api/v1/mobile/cameras/CAM-P7-NEW",
            headers=headers_a,
        )
        assert res_del_ok.status_code == 200, res_del_ok.text

        # ---------------------------------------------------------------------------
        # Step 7: Device Revocation & Post-Revocation Rejection (MOB-03)
        # ---------------------------------------------------------------------------
        res_devs = await client.get("/api/v1/mobile/devices", headers=headers_a)
        assert res_devs.status_code == 200, res_devs.text
        all_devs = res_devs.json()
        dev_a = next(d for d in all_devs if d["device_id"] == "iphone-15-tracer")
        dev_b = next(d for d in all_devs if d["device_id"] == "pixel-8-tracer")
        assert dev_b["is_revoked"] is False

        # Admin revokes Phone A
        res_revoke = await client.post(
            f"/api/v1/mobile/devices/{dev_a['id']}/revoke",
            headers={"Cookie": owner_cookie},
        )
        assert res_revoke.status_code == 200, res_revoke.text
        assert res_revoke.json()["revoked"] is True

        # Phone A request is now rejected with HTTP 401
        res_a_blocked = await client.get("/api/v1/mobile/status", headers=headers_a)
        assert res_a_blocked.status_code == 401, res_a_blocked.text

        # Phone B remains authorized and active
        res_b_ok = await client.get("/api/v1/mobile/status", headers=headers_b)
        assert res_b_ok.status_code == 200, res_b_ok.text

    # ---------------------------------------------------------------------------
    # Step 8: Clean Deregistration & Shutdown
    # ---------------------------------------------------------------------------
    advertiser.stop()
    assert advertiser.is_running is False
    mock_zc.unregister_service.assert_called_once_with(info)

    await engine.dispose()
