"""Integration tests for Camera Settings REST API, capability gating, RBAC, and audit logs (Plan 06-02).

Tests:
- GET /api/v1/cameras/{serial}/settings (aggregated settings & options)
- PUT /api/v1/cameras/{serial}/settings/identity (name, location, timezone, password)
- PUT /api/v1/cameras/{serial}/settings/encoder (bounds validation, codec, resolution)
- PUT /api/v1/cameras/{serial}/settings/imaging (ISP sliders, WDR capability gate, mirror/flip)
- PUT /api/v1/cameras/{serial}/settings/osd (text and timestamp overlays)
- POST /api/v1/cameras/{serial}/reboot (reboot trigger and audit)
- POST /api/v1/cameras/{serial}/factory-reset (Soft and Hard reset with confirmation)
- GET /api/v1/cameras/{serial}/health (uptime, clock sync state, firmware version)
- RBAC permissions (Viewer read-only & camera scoping, Operator/Owner mutations)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.camera.nuraeye.settings import NightVisionStatus
from vizenlink_nvr.camera.onvif.imaging import ImagingOptions, ImagingSettings
from vizenlink_nvr.camera.onvif.media2 import (
    MediaProfile,
    OsdConfig,
    VideoEncoderConfiguration,
    VideoEncoderConfigurationOptions,
    VideoResolution,
)
from vizenlink_nvr.camera.result import Failure, FailureKind, Success
from vizenlink_nvr.db.models import (
    AuditLog,
    Base,
    Camera,
    CameraCredential,
    CameraStream,
    Event,
    User,
    UserCameraPermission,
)
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now

M2_CLIENT = "vizenlink_nvr.camera.onvif.media2.OnvifMedia2Client"
IMG_CLIENT = "vizenlink_nvr.camera.onvif.imaging.OnvifImagingClient"
NE_CLIENT = "vizenlink_nvr.camera.nuraeye.settings.NuraeyeSettingsClient"
DEV_CLIENT = "vizenlink_nvr.camera.onvif.device.OnvifDeviceClient"


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_settings_api.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    vault = Vault(b"0" * 32, "test-vault-key", "memory")
    app.state.vault = vault

    now = utc_now()

    async with session_factory() as session:
        # 1. Users
        owner = User(
            username="settings_owner",
            password_hash=hash_password("OwnerPass123!"),
            role="owner",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        operator = User(
            username="settings_operator",
            password_hash=hash_password("OperatorPass123!"),
            role="operator",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        viewer = User(
            username="settings_viewer",
            password_hash=hash_password("ViewerPass123!"),
            role="viewer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add_all([owner, operator, viewer])
        await session.flush()

        # Viewer only has access to CAM-SET-1
        viewer_perm = UserCameraPermission(
            user_id=viewer.id,
            camera_serial="CAM-SET-1",
            created_at=now,
        )
        session.add(viewer_perm)

        # 2. Cameras
        cam1 = Camera(
            serial="CAM-SET-1",
            host="192.168.1.101",
            https_port=443,
            mac="AA:BB:CC:11:22:33",
            name="Front Porch",
            location="Front Entrance",
            group_tag="entrance",
            manufacturer="VizenLink",
            model="VZ-4K-PRO",
            firmware_version="v2.4.0",
            hardware_id="rev3",
            tls_fingerprint_sha256="11" * 32,
            added_at=now,
            host_updated_at=now,
        )
        cam2 = Camera(
            serial="CAM-SET-2",
            host="192.168.1.102",
            https_port=443,
            mac="AA:BB:CC:44:55:66",
            name="Back Yard",
            location="Garden",
            group_tag="back",
            manufacturer="VizenLink",
            model="VZ-2K-BASIC",
            firmware_version="v1.1.0",
            hardware_id="rev1",
            tls_fingerprint_sha256="22" * 32,
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam1, cam2])
        await session.flush()

        # 3. Credentials
        sealed1 = vault.seal(cam1.serial, "admin", SecretStr("CameraPass1!"))
        cred1 = CameraCredential(
            serial=cam1.serial,
            username="admin",
            ciphertext=sealed1.ciphertext,
            nonce=sealed1.nonce,
            key_id=sealed1.key_id,
            enc_version=sealed1.enc_version,
            updated_at=now,
        )
        sealed2 = vault.seal(cam2.serial, "admin", SecretStr("CameraPass2!"))
        cred2 = CameraCredential(
            serial=cam2.serial,
            username="admin",
            ciphertext=sealed2.ciphertext,
            nonce=sealed2.nonce,
            key_id=sealed2.key_id,
            enc_version=sealed2.enc_version,
            updated_at=now,
        )
        session.add_all([cred1, cred2])

        # 4. Streams
        stream1 = CameraStream(
            serial=cam1.serial,
            role="main",
            profile_token="Profile_1",
            profile_name="MainStream",
            venc_token="VEC_Main",
            codec="H265",
            width=2560,
            height=1440,
            transport="tcp",
            scheme="rtsp",
            port=554,
            path="/stream1",
            source="onvif_fallback",
            sub_is_main=False,
            probed_at=now,
        )
        session.add(stream1)

        # 5. Events (for clock sync state)
        event1 = Event(
            camera_serial=cam1.serial,
            event_type="motion",
            start_time=now,
            clock_sync_state="synced",
        )
        session.add(event1)
        await session.commit()

        # Generate auth tokens
        owner_sess = await SessionManager.create_session(session, owner.id, "127.0.0.1", "pytest")
        operator_sess = await SessionManager.create_session(session, operator.id, "127.0.0.1", "pytest")
        viewer_sess = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "pytest")

    return {
        "app": app,
        "session_factory": session_factory,
        "owner_token": owner_sess.id,
        "operator_token": operator_sess.id,
        "viewer_token": viewer_sess.id,
        "cam1_serial": "CAM-SET-1",
        "cam2_serial": "CAM-SET-2",
    }


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_camera_settings_aggregated(app_fixture: dict) -> None:
    app = app_fixture["app"]
    token = app_fixture["operator_token"]
    serial = app_fixture["cam1_serial"]

    mock_profiles = [
        MediaProfile(
            token="Profile_1",
            name="MainStream",
            venc_token="VEC_Main",
            width=2560,
            height=1440,
            encoding="H265",
        )
    ]
    mock_enc_cfg = VideoEncoderConfiguration(
        token="VEC_Main",
        name="MainStream",
        encoding="H265",
        width=2560,
        height=1440,
        quality=60.0,
        frame_rate_limit=30.0,
        bitrate_limit_kbps=4096,
        gov_length=60,
    )
    mock_enc_opts = VideoEncoderConfigurationOptions(
        token="VEC_Main",
        encodings=("H264", "H265"),
        resolutions=(VideoResolution(2560, 1440), VideoResolution(1920, 1080)),
        quality_range=(1.0, 100.0),
        frame_rate_range=(1.0, 30.0),
        bitrate_range_kbps=(256, 8192),
    )
    mock_imaging_settings = ImagingSettings(
        brightness=55.0,
        contrast=50.0,
        color_saturation=50.0,
        sharpness=45.0,
        ir_cut_filter="AUTO",
        wdr_mode="OFF",
        wdr_level=0.0,
    )
    mock_imaging_opts = ImagingOptions(
        brightness_range=(0.0, 100.0),
        contrast_range=(0.0, 100.0),
        color_saturation_range=(0.0, 100.0),
        sharpness_range=(0.0, 100.0),
        ir_cut_filter_modes=("AUTO", "ON", "OFF"),
        wdr_supported=True,
        wdr_level_range=(0.0, 100.0),
    )
    mock_nv_status = NightVisionStatus(current_type="smart", color_capable=True, smart_capable=True)
    mock_osds = [
        OsdConfig(
            token="OSD_1",
            video_source_token="VideoSource_1",
            osd_type="DateAndTime",
            position="UpperLeft",
        ),
        OsdConfig(
            token="OSD_2",
            video_source_token="VideoSource_1",
            osd_type="Plain",
            position="BottomRight",
            plain_text="Front Porch",
        ),
    ]

    with (
        patch(f"{M2_CLIENT}.get_profiles", new_callable=AsyncMock) as m_prof,
        patch(f"{M2_CLIENT}.get_video_encoder_configuration", new_callable=AsyncMock) as m_venc,
        patch(f"{M2_CLIENT}.get_video_encoder_configuration_options", new_callable=AsyncMock) as m_vopts,
        patch(f"{IMG_CLIENT}.get_imaging_settings", new_callable=AsyncMock) as m_img,
        patch(f"{IMG_CLIENT}.get_imaging_options", new_callable=AsyncMock) as m_iopts,
        patch(f"{NE_CLIENT}.get_night_vision_type", new_callable=AsyncMock) as m_nv,
        patch(f"{NE_CLIENT}.get_mirror_flip", new_callable=AsyncMock) as m_mf,
        patch(f"{NE_CLIENT}.get_anti_flicker", new_callable=AsyncMock) as m_af,
        patch(f"{M2_CLIENT}.get_osds", new_callable=AsyncMock) as m_osd,
        patch(f"{M2_CLIENT}.get_osd_options", new_callable=AsyncMock) as m_osd_opts,
        patch(f"{DEV_CLIENT}.get_system_timezone", new_callable=AsyncMock) as m_tz,
        patch(f"{DEV_CLIENT}.get_device_identity", new_callable=AsyncMock) as m_ident,
        patch(
            "vizenlink_nvr.services.camera_settings.NuraeyeClient.request", new_callable=AsyncMock
        ) as m_video_mode,
    ):
        m_video_mode.return_value = Success({"configured_mode": "Auto", "effective_state": "night"})
        m_ident.return_value = Failure(FailureKind.UNREACHABLE, "identity not mocked")
        m_osd_opts.return_value = Success({})
        m_tz.return_value = Success("UTC")
        m_prof.return_value = Success(mock_profiles)
        m_venc.return_value = Success(mock_enc_cfg)
        m_vopts.return_value = Success(mock_enc_opts)
        m_img.return_value = Success(mock_imaging_settings)
        m_iopts.return_value = Success(mock_imaging_opts)
        m_nv.return_value = Success(mock_nv_status)
        m_mf.return_value = Success("off")
        m_af.return_value = Success("60Hz")
        m_osd.return_value = Success(mock_osds)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/cameras/{serial}/settings",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()

            # Verify Identity & Info
            assert data["identity"]["name"] == "Front Porch"
            assert data["identity"]["location"] == "Front Entrance"
            assert isinstance(data["identity"]["supported_timezones"], list)
            assert data["device_info"]["model"] == "VZ-4K-PRO"
            assert data["device_info"]["firmware_version"] == "v2.4.0"

            # Verify Encoders
            assert len(data["encoders"]) == 1
            enc = data["encoders"][0]
            assert enc["current"]["encoding"] == "H265"
            assert enc["current"]["width"] == 2560
            assert enc["current"]["height"] == 1440
            assert {"width": 2560, "height": 1440} in enc["options"]["resolutions"]

            # Verify Imaging
            img = data["imaging"]
            assert img["current"]["brightness"] == 55.0
            assert img["current"]["ir_cut_filter"] == "AUTO"
            assert img["current"]["night_vision_type"] == "smart"
            # Live day/night state from GetVideoMode (SETTINGS_API_GUIDE "Day/Night Mode").
            assert img["current"]["day_night_now"] == "night"
            m_video_mode.assert_any_await("GET", "/nuraeye/video/mode")
            assert img["current"]["anti_flicker"] == "60Hz"
            assert img["options"]["wdr_supported"] is True

            # Verify OSD
            assert len(data["osd"]) == 2
            assert data["osd"][1]["plain_text"] == "Front Porch"


@pytest.mark.asyncio
async def test_update_identity_and_audit(app_fixture: dict) -> None:
    app = app_fixture["app"]
    token = app_fixture["operator_token"]
    serial = app_fixture["cam1_serial"]
    session_factory = app_fixture["session_factory"]

    with (
        patch(f"{DEV_CLIENT}.set_device_name", new_callable=AsyncMock) as m_name,
        patch(f"{DEV_CLIENT}.set_device_location", new_callable=AsyncMock) as m_loc,
        patch(f"{DEV_CLIENT}.set_system_date_and_time", new_callable=AsyncMock) as m_tz,
    ):
        m_name.return_value = Success(None)
        m_loc.return_value = Success(None)
        m_tz.return_value = Success(True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/v1/cameras/{serial}/settings/identity",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "New Front Cam", "location": "Main Gate", "timezone": "America/New_York"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["updated"]["name"] == "New Front Cam"
            assert data["updated"]["location"] == "Main Gate"
            assert data["updated"]["timezone"] == "America/New_York"

    # Verify DB update and AuditLog entry
    async with session_factory() as session:
        cam = await session.get(Camera, serial)
        assert cam.name == "New Front Cam"
        assert cam.location == "Main Gate"

        audit_stmt = select(AuditLog).where(
            AuditLog.resource_id == serial,
            AuditLog.action == "camera.settings.update_identity",
        )
        audit = (await session.execute(audit_stmt)).scalar_one()
        assert audit.actor_username == "settings_operator"
        assert "New Front Cam" in audit.details_json


@pytest.mark.asyncio
async def test_update_encoder_validation(app_fixture: dict) -> None:
    app = app_fixture["app"]
    token = app_fixture["operator_token"]
    serial = app_fixture["cam1_serial"]

    mock_enc_opts = VideoEncoderConfigurationOptions(
        token="VEC_Main",
        encodings=("H264", "H265"),
        resolutions=(VideoResolution(2560, 1440), VideoResolution(1920, 1080)),
        quality_range=(1.0, 100.0),
        frame_rate_range=(5.0, 30.0),
        bitrate_range_kbps=(256, 8192),
    )
    mock_curr_cfg = VideoEncoderConfiguration(
        token="VEC_Main",
        name="MainStream",
        encoding="H265",
        width=2560,
        height=1440,
        quality=50.0,
        frame_rate_limit=25.0,
        bitrate_limit_kbps=2048,
    )

    with (
        patch(f"{M2_CLIENT}.get_video_encoder_configuration_options", new_callable=AsyncMock) as m_opts,
        patch(f"{M2_CLIENT}.get_video_encoder_configuration", new_callable=AsyncMock) as m_curr,
        patch(f"{M2_CLIENT}.set_video_encoder_configuration", new_callable=AsyncMock) as m_set,
    ):
        m_opts.return_value = Success(mock_enc_opts)
        m_curr.return_value = Success(mock_curr_cfg)
        m_set.return_value = Success(True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Invalid resolution (not in options)
            resp_bad_res = await client.put(
                f"/api/v1/cameras/{serial}/settings/encoder",
                headers={"Authorization": f"Bearer {token}"},
                json={"venc_token": "VEC_Main", "width": 3840, "height": 2160},
            )
            assert resp_bad_res.status_code == 400
            assert "Resolution 3840x2160 not supported" in resp_bad_res.json()["detail"]

            # 2. Invalid framerate (> 30.0)
            resp_bad_fps = await client.put(
                f"/api/v1/cameras/{serial}/settings/encoder",
                headers={"Authorization": f"Bearer {token}"},
                json={"venc_token": "VEC_Main", "frame_rate_limit": 60.0},
            )
            assert resp_bad_fps.status_code == 400
            assert "Frame rate 60.0 outside allowed range" in resp_bad_fps.json()["detail"]

            # 3. Valid update
            resp_ok = await client.put(
                f"/api/v1/cameras/{serial}/settings/encoder",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "venc_token": "VEC_Main",
                    "width": 1920,
                    "height": 1080,
                    "frame_rate_limit": 30.0,
                    "bitrate_limit_kbps": 4096,
                },
            )
            assert resp_ok.status_code == 200
            data = resp_ok.json()
            assert data["status"] == "ok"
            assert data["config"]["width"] == 1920
            assert data["config"]["height"] == 1080
            assert data["config"]["frame_rate_limit"] == 30.0
            assert data["config"]["bitrate_limit_kbps"] == 4096


@pytest.mark.asyncio
async def test_update_imaging_and_wdr_capability_gate(app_fixture: dict) -> None:
    app = app_fixture["app"]
    token = app_fixture["operator_token"]
    serial = app_fixture["cam1_serial"]

    mock_imaging_opts_no_wdr = ImagingOptions(
        brightness_range=(0.0, 100.0),
        contrast_range=(0.0, 100.0),
        color_saturation_range=(0.0, 100.0),
        sharpness_range=(0.0, 100.0),
        ir_cut_filter_modes=("AUTO", "ON", "OFF"),
        wdr_supported=False,  # Camera build without WDR!
    )
    mock_nv_status = NightVisionStatus(current_type="grey", color_capable=True, smart_capable=True)

    with (
        patch(f"{IMG_CLIENT}.get_imaging_options", new_callable=AsyncMock) as m_opts,
        patch(f"{IMG_CLIENT}.set_imaging_settings", new_callable=AsyncMock) as m_set_img,
        patch(f"{NE_CLIENT}.get_night_vision_type", new_callable=AsyncMock) as m_nv,
        patch(f"{NE_CLIENT}.set_night_vision_type", new_callable=AsyncMock) as m_set_nv,
        patch(f"{NE_CLIENT}.set_mirror_flip", new_callable=AsyncMock) as m_mf,
    ):
        m_opts.return_value = Success(mock_imaging_opts_no_wdr)
        m_set_img.return_value = Success(True)
        m_nv.return_value = Success(mock_nv_status)
        m_set_nv.return_value = Success(True)
        m_mf.return_value = Success(True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Reject WDR when not supported by hardware/firmware
            resp_wdr = await client.put(
                f"/api/v1/cameras/{serial}/settings/imaging",
                headers={"Authorization": f"Bearer {token}"},
                json={"wdr_mode": "ON"},
            )
            assert resp_wdr.status_code == 400
            assert "WDR is not supported on this camera" in resp_wdr.json()["detail"]

            # 2. Reject out-of-range slider
            resp_bad_b = await client.put(
                f"/api/v1/cameras/{serial}/settings/imaging",
                headers={"Authorization": f"Bearer {token}"},
                json={"brightness": 120.0},
            )
            assert resp_bad_b.status_code == 400
            assert "Brightness 120.0 outside allowed range" in resp_bad_b.json()["detail"]

            # 3. Valid ISP + night vision + mirror_flip update
            resp_ok = await client.put(
                f"/api/v1/cameras/{serial}/settings/imaging",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "brightness": 65.0,
                    "contrast": 55.0,
                    "night_vision_type": "color",
                    "mirror_flip": "flip",
                },
            )
            assert resp_ok.status_code == 200
            data = resp_ok.json()
            assert data["status"] == "ok"
            assert data["updated"]["brightness"] == 65.0
            assert data["updated"]["night_vision_type"] == "color"
            assert data["updated"]["mirror_flip"] == "flip"


@pytest.mark.asyncio
async def test_reboot_and_factory_reset_endpoints(app_fixture: dict) -> None:
    app = app_fixture["app"]
    token = app_fixture["operator_token"]
    serial = app_fixture["cam1_serial"]
    session_factory = app_fixture["session_factory"]

    with (
        patch(f"{DEV_CLIENT}.system_reboot", new_callable=AsyncMock) as m_reboot,
        patch(f"{DEV_CLIENT}.set_system_factory_default", new_callable=AsyncMock) as m_reset,
    ):
        m_reboot.return_value = Success("Rebooting in 5 seconds")
        m_reset.return_value = Success(True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Reboot
            resp_rb = await client.post(
                f"/api/v1/cameras/{serial}/reboot",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp_rb.status_code == 200
            assert resp_rb.json()["message"] == "Rebooting in 5 seconds"

            # 2. Factory reset without confirmation fails
            resp_no_conf = await client.post(
                f"/api/v1/cameras/{serial}/factory-reset",
                headers={"Authorization": f"Bearer {token}"},
                json={"mode": "Soft", "confirmation": "NO"},
            )
            assert resp_no_conf.status_code == 400
            assert "Confirmation keyword required" in resp_no_conf.json()["detail"]

            # 3. Factory reset Soft succeeds
            resp_soft = await client.post(
                f"/api/v1/cameras/{serial}/factory-reset",
                headers={"Authorization": f"Bearer {token}"},
                json={"mode": "Soft", "confirmation": "RESET"},
            )
            assert resp_soft.status_code == 200
            assert "Soft factory reset initiated" in resp_soft.json()["message"]

            # 4. Factory reset Hard succeeds
            resp_hard = await client.post(
                f"/api/v1/cameras/{serial}/factory-reset",
                headers={"Authorization": f"Bearer {token}"},
                json={"mode": "Hard", "confirmation": "CONFIRM"},
            )
            assert resp_hard.status_code == 200
            assert "Hard factory reset initiated" in resp_hard.json()["message"]

    # Verify audit logs recorded for reboot and reset
    async with session_factory() as session:
        rb_stmt = select(AuditLog).where(AuditLog.resource_id == serial, AuditLog.action == "camera.reboot")
        rb_audit = (await session.execute(rb_stmt)).scalar_one()
        assert rb_audit.actor_username == "settings_operator"

        reset_stmt = select(AuditLog).where(
            AuditLog.resource_id == serial, AuditLog.action == "camera.factory_reset"
        )
        reset_audits = (await session.execute(reset_stmt)).scalars().all()
        assert len(reset_audits) == 2


@pytest.mark.asyncio
async def test_health_endpoint_and_rbac(app_fixture: dict) -> None:
    app = app_fixture["app"]
    viewer_token = app_fixture["viewer_token"]
    cam1 = app_fixture["cam1_serial"]
    cam2 = app_fixture["cam2_serial"]

    transport = httpx.ASGITransport(app=app)
    with patch(
        "vizenlink_nvr.services.camera_settings.NuraeyeClient.request", new_callable=AsyncMock
    ) as health_request:
        health_request.return_value = Success(
            {
                "uptime_seconds": 120,
                "reboot_reason": "watchdog",
                "clock_sync_state": "synced",
                "firmware_version": "v2.4.0",
            }
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Viewer can read health for permitted camera (CAM-SET-1)
            resp_h1 = await client.get(
                f"/api/v1/cameras/{cam1}/health",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert resp_h1.status_code == 200
            data_h1 = resp_h1.json()
            assert data_h1["serial"] == cam1
            assert data_h1["online"] is True
            assert data_h1["clock_sync_status"] == "synced"
            assert data_h1["firmware_version"] == "v2.4.0"

            # 2. Viewer cannot access health or settings for non-permitted camera (CAM-SET-2) -> 403
            resp_h2 = await client.get(
                f"/api/v1/cameras/{cam2}/health",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert resp_h2.status_code == 403

            resp_s2 = await client.get(
                f"/api/v1/cameras/{cam2}/settings",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert resp_s2.status_code == 403

            # 3. Viewer cannot modify settings (RequireOperator required) -> 403
            resp_mut = await client.put(
                f"/api/v1/cameras/{cam1}/settings/identity",
                headers={"Authorization": f"Bearer {viewer_token}"},
                json={"name": "Hacked Cam"},
            )
            assert resp_mut.status_code == 403

            # 4. Viewer cannot reboot camera -> 403
            resp_rb = await client.post(
                f"/api/v1/cameras/{cam1}/reboot",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert resp_rb.status_code == 403
