"""End-to-end integration pipeline tracer for Phase 06: Camera Settings (SET-01..SET-08).

Validates:
- SET-01: Device identity (name, location, timezone, password) & read-only device info.
- SET-02: Video encoder settings per stream profile within camera-allowed ranges.
- SET-03: Imaging & ISP settings (Day/Night, Night Vision type, WDR, anti-flicker, mirror/flip).
- SET-04: OSD text and timestamp overlays.
- SET-05: Camera reboot with audit verification.
- SET-06: Factory reset (Soft and Hard) with double-confirmation requirement.
- SET-07: Camera health monitoring (uptime, clock sync status, firmware version).
- SET-08: Dynamic capability gating and options boundaries.
- AUTH-05: RBAC viewer scoping and operator/owner mutation enforcement.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.camera.nuraeye.settings import NightVisionStatus
from vizenlink_nvr.camera.onvif.device import DeviceIdentity
from vizenlink_nvr.camera.onvif.imaging import ImagingOptions, ImagingSettings
from vizenlink_nvr.camera.onvif.media2 import (
    MediaProfile,
    OsdConfig,
    VideoEncoderConfiguration,
    VideoEncoderConfigurationOptions,
    VideoResolution,
)
from vizenlink_nvr.camera.result import Success
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import (
    AuditLog,
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

M2_CLIENT = "vizenlink_nvr.camera.onvif.media2.OnvifMedia2Client"
IMG_CLIENT = "vizenlink_nvr.camera.onvif.imaging.OnvifImagingClient"
NE_CLIENT = "vizenlink_nvr.camera.nuraeye.settings.NuraeyeSettingsClient"
DEV_CLIENT = "vizenlink_nvr.camera.onvif.device.OnvifDeviceClient"


@pytest.mark.asyncio
async def test_phase6_complete_e2e_tracer(tmp_path: Path) -> None:
    """Execute complete end-to-end lifecycle tracer for Phase 06."""
    # -------------------------------------------------------------------------
    # Step 1: Database Setup via Alembic Migrations to Head
    # -------------------------------------------------------------------------
    db_file = tmp_path / "tracer_phase6.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app(session_factory=session_factory)
    vault = Vault(b"0" * 32, "test-vault-phase6", "memory")
    app.state.vault = vault

    t_base = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)

    # -------------------------------------------------------------------------
    # Step 2: Seed Users, Cameras, Credentials, Streams, and Permissions
    # -------------------------------------------------------------------------
    async with session_factory() as session:
        owner = User(
            username="p6_owner",
            password_hash=hash_password("OwnerSecurePass123!"),
            role="owner",
            is_active=True,
            created_at=t_base,
            updated_at=t_base,
        )
        operator = User(
            username="p6_operator",
            password_hash=hash_password("OperatorSecurePass123!"),
            role="operator",
            is_active=True,
            created_at=t_base,
            updated_at=t_base,
        )
        viewer = User(
            username="p6_viewer",
            password_hash=hash_password("ViewerSecurePass123!"),
            role="viewer",
            is_active=True,
            created_at=t_base,
            updated_at=t_base,
        )
        session.add_all([owner, operator, viewer])
        await session.flush()

        # Viewer only has access to CAM-P6-1
        perm = UserCameraPermission(
            user_id=viewer.id,
            camera_serial="CAM-P6-1",
            created_at=t_base,
        )
        session.add(perm)

        cam1 = Camera(
            serial="CAM-P6-1",
            host="192.168.1.120",
            https_port=443,
            mac="AA:BB:CC:11:22:99",
            name="Main Gate Entrance",
            location="Perimeter North",
            group_tag="perimeter",
            manufacturer="VizenLink",
            model="VZ-4K-AI",
            firmware_version="v3.1.2",
            hardware_id="rev4",
            tls_fingerprint_sha256="aa" * 32,
            added_at=t_base,
            host_updated_at=t_base,
        )
        cam2 = Camera(
            serial="CAM-P6-2",
            host="192.168.1.121",
            https_port=443,
            mac="AA:BB:CC:33:44:99",
            name="Warehouse Bay",
            location="Storage Hall",
            group_tag="warehouse",
            manufacturer="VizenLink",
            model="VZ-2K-PRO",
            firmware_version="v2.0.1",
            hardware_id="rev2",
            tls_fingerprint_sha256="bb" * 32,
            added_at=t_base,
            host_updated_at=t_base,
        )
        session.add_all([cam1, cam2])
        await session.flush()

        sealed1 = vault.seal(cam1.serial, "admin", SecretStr("OriginalCamPass1!"))
        cred1 = CameraCredential(
            serial=cam1.serial,
            username="admin",
            ciphertext=sealed1.ciphertext,
            nonce=sealed1.nonce,
            key_id=sealed1.key_id,
            enc_version=sealed1.enc_version,
            updated_at=t_base,
        )
        sealed2 = vault.seal(cam2.serial, "admin", SecretStr("OriginalCamPass2!"))
        cred2 = CameraCredential(
            serial=cam2.serial,
            username="admin",
            ciphertext=sealed2.ciphertext,
            nonce=sealed2.nonce,
            key_id=sealed2.key_id,
            enc_version=sealed2.enc_version,
            updated_at=t_base,
        )
        session.add_all([cred1, cred2])

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
            probed_at=t_base,
        )
        session.add(stream1)

        event1 = Event(
            camera_serial=cam1.serial,
            event_type="motion",
            start_time=t_base,
            clock_sync_state="synced",
        )
        session.add(event1)
        await session.commit()

        # Create session tokens
        owner_session = await SessionManager.create_session(session, owner.id, "127.0.0.1", "pytest")
        operator_session = await SessionManager.create_session(session, operator.id, "127.0.0.1", "pytest")
        viewer_session = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "pytest")

    owner_token = owner_session.id
    operator_token = operator_session.id
    viewer_token = viewer_session.id

    # -------------------------------------------------------------------------
    # Step 3: Mock Protocol Payloads
    # -------------------------------------------------------------------------
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
        quality=50.0,
        frame_rate_limit=25.0,
        bitrate_limit_kbps=2048,
        gov_length=50,
    )
    mock_enc_opts = VideoEncoderConfigurationOptions(
        token="VEC_Main",
        encodings=("H264", "H265"),
        resolutions=(VideoResolution(2560, 1440), VideoResolution(1920, 1080)),
        quality_range=(1.0, 100.0),
        frame_rate_range=(5.0, 30.0),
        bitrate_range_kbps=(256, 8192),
    )
    mock_img_settings = ImagingSettings(
        brightness=50.0,
        contrast=50.0,
        color_saturation=50.0,
        sharpness=50.0,
        ir_cut_filter="AUTO",
        wdr_mode="OFF",
        wdr_level=0.0,
    )
    mock_img_opts = ImagingOptions(
        brightness_range=(0.0, 100.0),
        contrast_range=(0.0, 100.0),
        color_saturation_range=(0.0, 100.0),
        sharpness_range=(0.0, 100.0),
        ir_cut_filter_modes=("AUTO", "ON", "OFF"),
        wdr_supported=True,
        wdr_level_range=(0.0, 100.0),
    )
    mock_nv_status = NightVisionStatus(current_type="grey", color_capable=True, smart_capable=True)
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
            plain_text="Main Gate Entrance",
        ),
    ]

    with ExitStack() as stack:
        m_get_id = stack.enter_context(patch(f"{DEV_CLIENT}.get_device_identity", new_callable=AsyncMock))
        m_set_name = stack.enter_context(patch(f"{DEV_CLIENT}.set_device_name", new_callable=AsyncMock))
        m_set_loc = stack.enter_context(patch(f"{DEV_CLIENT}.set_device_location", new_callable=AsyncMock))
        m_set_tz = stack.enter_context(
            patch(f"{DEV_CLIENT}.set_system_date_and_time", new_callable=AsyncMock)
        )
        m_set_pw = stack.enter_context(patch(f"{DEV_CLIENT}.set_user_password", new_callable=AsyncMock))
        m_reboot = stack.enter_context(patch(f"{DEV_CLIENT}.system_reboot", new_callable=AsyncMock))
        m_reset = stack.enter_context(
            patch(f"{DEV_CLIENT}.set_system_factory_default", new_callable=AsyncMock)
        )
        m_prof = stack.enter_context(patch(f"{M2_CLIENT}.get_profiles", new_callable=AsyncMock))
        m_venc = stack.enter_context(
            patch(f"{M2_CLIENT}.get_video_encoder_configuration", new_callable=AsyncMock)
        )
        m_vopts = stack.enter_context(
            patch(f"{M2_CLIENT}.get_video_encoder_configuration_options", new_callable=AsyncMock)
        )
        m_set_venc = stack.enter_context(
            patch(f"{M2_CLIENT}.set_video_encoder_configuration", new_callable=AsyncMock)
        )
        m_get_osd = stack.enter_context(patch(f"{M2_CLIENT}.get_osds", new_callable=AsyncMock))
        m_get_osd_opts = stack.enter_context(patch(f"{M2_CLIENT}.get_osd_options", new_callable=AsyncMock))
        m_get_tz = stack.enter_context(patch(f"{DEV_CLIENT}.get_system_timezone", new_callable=AsyncMock))
        m_video_mode = stack.enter_context(
            patch("vizenlink_nvr.services.camera_settings.NuraeyeClient.request", new_callable=AsyncMock)
        )
        m_set_osd = stack.enter_context(patch(f"{M2_CLIENT}.set_osd", new_callable=AsyncMock))
        m_get_img = stack.enter_context(patch(f"{IMG_CLIENT}.get_imaging_settings", new_callable=AsyncMock))
        m_get_iopts = stack.enter_context(patch(f"{IMG_CLIENT}.get_imaging_options", new_callable=AsyncMock))
        m_set_img = stack.enter_context(patch(f"{IMG_CLIENT}.set_imaging_settings", new_callable=AsyncMock))
        m_get_nv = stack.enter_context(patch(f"{NE_CLIENT}.get_night_vision_type", new_callable=AsyncMock))
        m_set_nv = stack.enter_context(patch(f"{NE_CLIENT}.set_night_vision_type", new_callable=AsyncMock))
        m_get_mf = stack.enter_context(patch(f"{NE_CLIENT}.get_mirror_flip", new_callable=AsyncMock))
        m_set_mf = stack.enter_context(patch(f"{NE_CLIENT}.set_mirror_flip", new_callable=AsyncMock))
        m_get_af = stack.enter_context(patch(f"{NE_CLIENT}.get_anti_flicker", new_callable=AsyncMock))
        m_set_af = stack.enter_context(patch(f"{NE_CLIENT}.set_anti_flicker", new_callable=AsyncMock))

        m_get_id.return_value = Success(DeviceIdentity(name="Main Gate Entrance", location="Perimeter North"))
        m_set_name.return_value = Success(None)
        m_set_loc.return_value = Success(None)
        m_set_tz.return_value = Success(True)
        m_set_pw.return_value = Success(None)
        m_reboot.return_value = Success("Rebooting in 5 seconds")
        m_reset.return_value = Success(True)
        m_prof.return_value = Success(mock_profiles)
        m_venc.return_value = Success(mock_enc_cfg)
        m_vopts.return_value = Success(mock_enc_opts)
        m_set_venc.return_value = Success(True)
        m_get_osd.return_value = Success(mock_osds)
        m_get_osd_opts.return_value = Success({})
        m_get_tz.return_value = Success("UTC")
        m_video_mode.return_value = Success({"configured_mode": "Auto", "effective_state": "day"})
        m_set_osd.return_value = Success(True)
        m_get_img.return_value = Success(mock_img_settings)
        m_get_iopts.return_value = Success(mock_img_opts)
        m_set_img.return_value = Success(True)
        m_get_nv.return_value = Success(mock_nv_status)
        m_set_nv.return_value = Success(True)
        m_get_mf.return_value = Success("off")
        m_set_mf.return_value = Success(True)
        m_get_af.return_value = Success("Auto")
        m_set_af.return_value = Success(True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # -----------------------------------------------------------------
            # Step 4: Full Aggregated Settings Query (SET-01..SET-08)
            # -----------------------------------------------------------------
            res_settings = await client.get(
                "/api/v1/cameras/CAM-P6-1/settings",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            assert res_settings.status_code == 200
            s_data = res_settings.json()

            # Verify identity and device metadata (SET-01)
            assert s_data["identity"]["name"] == "Main Gate Entrance"
            assert s_data["identity"]["location"] == "Perimeter North"
            assert s_data["device_info"]["model"] == "VZ-4K-AI"
            assert s_data["device_info"]["firmware_version"] == "v3.1.2"
            assert s_data["device_info"]["hardware_id"] == "rev4"

            # Verify video encoders (SET-02, SET-08)
            assert len(s_data["encoders"]) == 1
            enc = s_data["encoders"][0]
            assert enc["current"]["width"] == 2560
            assert enc["current"]["height"] == 1440
            assert enc["options"]["frame_rate_range"] == [5.0, 30.0]

            # Verify imaging (SET-03, SET-08)
            assert s_data["imaging"]["current"]["ir_cut_filter"] == "AUTO"
            assert s_data["imaging"]["options"]["wdr_supported"] is True

            # Verify OSD (SET-04)
            assert len(s_data["osd"]) == 2
            assert s_data["osd"][1]["plain_text"] == "Main Gate Entrance"

            # -----------------------------------------------------------------
            # Step 5: Update Identity, Location, Timezone, Password (SET-01)
            # -----------------------------------------------------------------
            res_id = await client.put(
                "/api/v1/cameras/CAM-P6-1/settings/identity",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "name": "North Gate Entry",
                    "location": "Sector 7",
                    "timezone": "America/New_York",
                    "password": "NewSecretCamPassword99!",
                },
            )
            assert res_id.status_code == 200
            assert res_id.json()["updated"]["name"] == "North Gate Entry"
            assert res_id.json()["updated"]["password_changed"] is True

            # -----------------------------------------------------------------
            # Step 6: Video Encoder Bounds Validation & Mutation (SET-02, SET-08)
            # -----------------------------------------------------------------
            # 6a. Out-of-bounds rejection
            res_bad_fps = await client.put(
                "/api/v1/cameras/CAM-P6-1/settings/encoder",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"venc_token": "VEC_Main", "frame_rate_limit": 60.0},
            )
            assert res_bad_fps.status_code == 400

            # 6b. Valid configuration update
            res_enc_ok = await client.put(
                "/api/v1/cameras/CAM-P6-1/settings/encoder",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "venc_token": "VEC_Main",
                    "width": 1920,
                    "height": 1080,
                    "frame_rate_limit": 30.0,
                    "bitrate_limit_kbps": 4096,
                },
            )
            assert res_enc_ok.status_code == 200
            assert res_enc_ok.json()["config"]["width"] == 1920

            # -----------------------------------------------------------------
            # Step 7: Imaging, WDR Gating, and Sensor Controls (SET-03, SET-08)
            # -----------------------------------------------------------------
            res_img = await client.put(
                "/api/v1/cameras/CAM-P6-1/settings/imaging",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "brightness": 65.0,
                    "contrast": 55.0,
                    "ir_cut_filter": "ON",
                    "wdr_mode": "ON",
                    "wdr_level": 15.0,
                    "night_vision_type": "smart",
                    "mirror_flip": "both",
                    "anti_flicker": "50Hz",
                },
            )
            assert res_img.status_code == 200
            assert res_img.json()["updated"]["ir_cut_filter"] == "ON"
            assert res_img.json()["updated"]["wdr_mode"] == "ON"
            assert res_img.json()["updated"]["anti_flicker"] == "50Hz"

            # -----------------------------------------------------------------
            # Step 8: OSD Overlays Update (SET-04)
            # -----------------------------------------------------------------
            res_osd = await client.put(
                "/api/v1/cameras/CAM-P6-1/settings/osd",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "token": "OSD_2",
                    "osd_type": "Plain",
                    "position": "BottomLeft",
                    "plain_text": "Sector 7 North Gate",
                },
            )
            assert res_osd.status_code == 200
            assert res_osd.json()["osd"]["plain_text"] == "Sector 7 North Gate"
            assert res_osd.json()["osd"]["position"] == "BottomLeft"

            # -----------------------------------------------------------------
            # Step 9: Camera Reboot (SET-05)
            # -----------------------------------------------------------------
            res_rb = await client.post(
                "/api/v1/cameras/CAM-P6-1/reboot",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            assert res_rb.status_code == 200
            assert res_rb.json()["status"] == "ok"
            assert "Rebooting in 5 seconds" in res_rb.json()["message"]

            # -----------------------------------------------------------------
            # Step 10: Factory Reset Soft & Hard (SET-06)
            # -----------------------------------------------------------------
            # 10a. Missing confirmation rejected
            res_no_conf = await client.post(
                "/api/v1/cameras/CAM-P6-1/factory-reset",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"mode": "Soft", "confirmation": "INVALID"},
            )
            assert res_no_conf.status_code == 400

            # 10b. Soft Reset
            res_soft = await client.post(
                "/api/v1/cameras/CAM-P6-1/factory-reset",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"mode": "Soft", "confirmation": "CONFIRM"},
            )
            assert res_soft.status_code == 200
            assert "Soft factory reset initiated" in res_soft.json()["message"]

            # 10c. Hard Reset
            res_hard = await client.post(
                "/api/v1/cameras/CAM-P6-1/factory-reset",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"mode": "Hard", "confirmation": "RESET"},
            )
            assert res_hard.status_code == 200
            assert "Hard factory reset initiated" in res_hard.json()["message"]

            # -----------------------------------------------------------------
            # Step 11: Camera Health Monitoring (SET-07)
            # -----------------------------------------------------------------
            with patch(
                "vizenlink_nvr.services.camera_settings.NuraeyeClient.request", new_callable=AsyncMock
            ) as m_health:
                m_health.return_value = Success(
                    {"uptime_seconds": 120, "clock_sync_state": "synced", "firmware_version": "v3.1.2"}
                )
                res_health = await client.get(
                    "/api/v1/cameras/CAM-P6-1/health",
                    headers={"Authorization": f"Bearer {viewer_token}"},
                )
            assert res_health.status_code == 200
            h_data = res_health.json()
            assert h_data["serial"] == "CAM-P6-1"
            assert h_data["online"] is True
            assert h_data["clock_sync_status"] == "synced"
            assert h_data["firmware_version"] == "v3.1.2"

            # -----------------------------------------------------------------
            # Step 12: RBAC Viewer Scoping and Permission Isolation (AUTH-05)
            # -----------------------------------------------------------------
            # Viewer can read allowed camera
            res_v_ok = await client.get(
                "/api/v1/cameras/CAM-P6-1/settings",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert res_v_ok.status_code == 200

            # Viewer forbidden from accessing unpermitted camera
            res_v_forbidden = await client.get(
                "/api/v1/cameras/CAM-P6-2/settings",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert res_v_forbidden.status_code == 403

            # Viewer cannot execute mutations or maintenance actions
            res_v_mut = await client.put(
                "/api/v1/cameras/CAM-P6-1/settings/identity",
                headers={"Authorization": f"Bearer {viewer_token}"},
                json={"name": "Hacked Name"},
            )
            assert res_v_mut.status_code == 403

            res_v_rb = await client.post(
                "/api/v1/cameras/CAM-P6-1/reboot",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert res_v_rb.status_code == 403

    # -------------------------------------------------------------------------
    # Step 13: Database & Audit Trail Verification
    # -------------------------------------------------------------------------
    async with session_factory() as session:
        # Check DB camera updated
        cam = await session.get(Camera, "CAM-P6-1")
        assert cam.name == "North Gate Entry"
        assert cam.location == "Sector 7"

        # Check DB stream updated
        stream = (
            await session.execute(
                select(CameraStream).where(
                    CameraStream.serial == "CAM-P6-1", CameraStream.venc_token == "VEC_Main"
                )
            )
        ).scalar_one()
        assert stream.width == 1920
        assert stream.height == 1080

        # Check audit trail records for all operations
        audit_events = (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.resource_id == "CAM-P6-1")
                .order_by(AuditLog.id.asc())
            )
        ).scalars().all()

        action_names = [a.action for a in audit_events]
        assert "camera.settings.update_identity" in action_names
        assert "camera.settings.update_encoder" in action_names
        assert "camera.settings.update_imaging" in action_names
        assert "camera.settings.update_osd" in action_names
        assert "camera.reboot" in action_names
        assert "camera.factory_reset" in action_names
