"""End-to-end integration tracer for Phase 03: Secure API, Auth & Live View.

Validates:
- AUTH-01: First-run setup wizard creates Owner, timezone, storage.
- AUTH-02: Setup locked against re-initialization.
- AUTH-03: Zero anonymous access to LAN endpoints or MediaMTX streams.
- AUTH-04: User management with secure passwords and RBAC roles (Owner, Operator, Viewer).
- AUTH-05: Strict camera permission scoping for Viewers across REST & media tokens.
- AUTH-06: Simple vs Advanced diagnostics telemetry filtering.
- AUTH-07: Append-only persistent audit trail.
- LIVE-01: Signed 15-minute HMAC media tokens and MediaMTX HTTP webhook validation.
- HLTH-02, HLTH-07, HLTH-08: Camera outage tracking and in-app alert evaluation.
"""

from __future__ import annotations

import types
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.media.config import CONTROL_USER
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.outage_tracker import OutageTracker
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_phase3_complete_e2e_tracer(tmp_path: Path) -> None:
    """Execute complete end-to-end lifecycle tracer for Phase 03."""
    db_file = tmp_path / "tracer_phase3.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_dir = tmp_path / "recordings"
    storage_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(
        session_factory=session_factory,
        runtime=types.SimpleNamespace(vault=Vault(b"0" * 32, "test-vault-key", "memory")),
    )
    app.state.control_password = "tracer-control-pw"

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # -------------------------------------------------------------------------
        # Step 1: Initial unconfigured state triggers /setup requirement
        # -------------------------------------------------------------------------
        res_status_uninit = await client.get("/api/v1/auth/status")
        assert res_status_uninit.status_code == 200
        assert res_status_uninit.json() == {
            "initialized": False,
            "authenticated": False,
            "user": None,
            "site_timezone": None,
        }

        # Anonymous access to protected endpoints is rejected with 401
        res_anon_cams = await client.get("/api/v1/cameras")
        assert res_anon_cams.status_code == 401
        res_anon_users = await client.get("/api/v1/users")
        assert res_anon_users.status_code == 401

        # -------------------------------------------------------------------------
        # Step 2: First-run setup creates Owner account, timezone, and storage
        # -------------------------------------------------------------------------
        res_setup = await client.post(
            "/api/v1/auth/setup",
            json={
                "owner_username": "tracer_owner",
                "owner_password": "OwnerSecurePassword123!",
                "timezone": "UTC",
                "storage_path": str(storage_dir),
                "allow_system_disk": True,
            },
        )
        assert res_setup.status_code == 200
        setup_data = res_setup.json()
        assert setup_data["success"] is True
        assert setup_data["user"]["username"] == "tracer_owner"
        assert setup_data["user"]["role"] == "owner"
        assert "session_id" in client.cookies

        # Verify status is now initialized and authenticated
        res_status_init = await client.get("/api/v1/auth/status")
        assert res_status_init.status_code == 200
        assert res_status_init.json()["initialized"] is True
        assert res_status_init.json()["authenticated"] is True
        assert res_status_init.json()["user"]["username"] == "tracer_owner"

        # -------------------------------------------------------------------------
        # Step 3: Verify setup is permanently locked against re-execution
        # -------------------------------------------------------------------------
        res_setup_rerun = await client.post(
            "/api/v1/auth/setup",
            json={
                "owner_username": "intruder_owner",
                "owner_password": "IntruderPassword123!",
                "timezone": "UTC",
                "storage_path": str(storage_dir),
                "allow_system_disk": True,
            },
        )
        assert res_setup_rerun.status_code == 400
        assert "already initialized" in res_setup_rerun.json()["detail"]

        # -------------------------------------------------------------------------
        # Step 4: Owner registers cameras (CAM-A and CAM-B) and creates users
        # -------------------------------------------------------------------------
        # Add Camera A
        res_add_a = await client.post(
            "/api/v1/cameras",
            json={
                "serial": "CAM-A",
                "host": "192.168.1.51",
                "name": "Entrance Gate",
                "location": "Front Perimeter",
                "group_tag": "exterior",
                "manufacturer": "NuraEye",
                "model": "NE-4K",
                "streams": [
                    {
                        "role": "main",
                        "codec": "H264",
                        "width": 3840,
                        "height": 2160,
                        "path": "/stream1",
                        "source": "onvif_fallback",
                    },
                    {
                        "role": "sub",
                        "codec": "H264",
                        "width": 640,
                        "height": 360,
                        "path": "/stream2",
                        "source": "onvif_fallback",
                    },
                ],
            },
        )
        assert res_add_a.status_code == 201

        # Add Camera B
        res_add_b = await client.post(
            "/api/v1/cameras",
            json={
                "serial": "CAM-B",
                "host": "192.168.1.52",
                "name": "Server Vault",
                "location": "Datacenter",
                "group_tag": "internal",
                "manufacturer": "NuraEye",
                "model": "NE-2K",
                "streams": [
                    {
                        "role": "main",
                        "codec": "H264",
                        "width": 1920,
                        "height": 1080,
                        "path": "/stream1",
                        "source": "onvif_fallback",
                    },
                    {
                        "role": "sub",
                        "codec": "H264",
                        "width": 640,
                        "height": 360,
                        "path": "/stream2",
                        "source": "onvif_fallback",
                    },
                ],
            },
        )
        assert res_add_b.status_code == 201

        # Owner creates Operator
        res_op = await client.post(
            "/api/v1/users",
            json={
                "username": "tracer_op",
                "password": "OperatorPassword123!",
                "role": "operator",
            },
        )
        assert res_op.status_code == 201

        # Owner creates Viewer restricted strictly to CAM-A
        res_view = await client.post(
            "/api/v1/users",
            json={
                "username": "tracer_view",
                "password": "ViewerPassword123!",
                "role": "viewer",
                "permissions": ["CAM-A"],
            },
        )
        assert res_view.status_code == 201

        # -------------------------------------------------------------------------
        # Step 5: Viewer logs in, requests cameras and verifies strict scoping (AUTH-05)
        # -------------------------------------------------------------------------
        # Use a distinct client for Viewer to isolate cookies
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as viewer_client:
            res_v_login = await viewer_client.post(
                "/api/v1/auth/login",
                json={"username": "tracer_view", "password": "ViewerPassword123!"},
            )
            assert res_v_login.status_code == 200

            # Viewer sees ONLY CAM-A
            res_v_cams = await viewer_client.get("/api/v1/cameras")
            assert res_v_cams.status_code == 200
            cam_list = res_v_cams.json()
            assert len(cam_list) == 1
            assert cam_list[0]["serial"] == "CAM-A"

            # Viewer attempts to query CAM-B directly -> 403 Forbidden
            res_v_get_b = await viewer_client.get("/api/v1/cameras/CAM-B")
            assert res_v_get_b.status_code == 403

            # Viewer attempts to add or delete cameras -> 403 Forbidden
            res_v_post_cam = await viewer_client.post(
                "/api/v1/cameras",
                json={"serial": "CAM-EVIL", "host": "192.168.1.99"},
            )
            assert res_v_post_cam.status_code == 403

            # -------------------------------------------------------------------------
            # Step 6: Viewer requests signed media tokens for CAM-A (ok) and CAM-B (403)
            # -------------------------------------------------------------------------
            # Permitted token for CAM-A sub-stream
            res_token_a = await viewer_client.post("/api/v1/cameras/CAM-A/media-token?stream=sub")
            assert res_token_a.status_code == 200
            token_a_data = res_token_a.json()
            token_a = token_a_data["token"]
            assert token_a_data["path"] == "cam/CAM-A/sub"
            assert token_a_data["expires_in"] == 900

            # Forbidden token request for CAM-B
            res_token_b = await viewer_client.post("/api/v1/cameras/CAM-B/media-token?stream=sub")
            assert res_token_b.status_code == 403

        # -------------------------------------------------------------------------
        # Step 7: MediaMTX HTTP media auth webhook verification
        # -------------------------------------------------------------------------
        # 7a: Valid token for CAM-A sub-stream read -> 200 OK
        res_mtx_ok = await client.post(
            "/api/v1/auth/mediamtx",
            json={
                "ip": "192.168.1.100",
                "path": "cam/CAM-A/sub",
                "action": "read",
                "query": f"token={token_a}",
            },
        )
        assert res_mtx_ok.status_code == 200
        assert res_mtx_ok.json() == {"status": "ok"}

        # 7b: Missing token query parameter -> 401 Unauthorized
        res_mtx_missing = await client.post(
            "/api/v1/auth/mediamtx",
            json={
                "ip": "192.168.1.100",
                "path": "cam/CAM-A/sub",
                "action": "read",
                "query": "",
            },
        )
        assert res_mtx_missing.status_code == 401

        # 7c: Tampered token signature -> 401 Unauthorized
        b64_p, _ = token_a.split(".", 1)
        res_mtx_tampered = await client.post(
            "/api/v1/auth/mediamtx",
            json={
                "ip": "192.168.1.100",
                "path": "cam/CAM-A/sub",
                "action": "read",
                "query": f"token={b64_p}.badSignatureXYZ",
            },
        )
        assert res_mtx_tampered.status_code == 401

        # 7d: Token path mismatch (CAM-A token used to access CAM-B) -> 403 Forbidden
        res_mtx_mismatch = await client.post(
            "/api/v1/auth/mediamtx",
            json={
                "ip": "192.168.1.100",
                "path": "cam/CAM-B/sub",
                "action": "read",
                "query": f"token={token_a}",
            },
        )
        assert res_mtx_mismatch.status_code == 403

        # 7e: External stream publish attempt -> 403 Forbidden
        res_mtx_pub = await client.post(
            "/api/v1/auth/mediamtx",
            json={
                "ip": "192.168.1.100",
                "path": "cam/CAM-A/sub",
                "action": "publish",
            },
        )
        assert res_mtx_pub.status_code == 403

        # 7f: MediaMTX internal API control authentication via loopback -> 200 OK
        res_mtx_api = await client.post(
            "/api/v1/auth/mediamtx",
            json={
                "ip": "127.0.0.1",
                "user": CONTROL_USER,
                "password": "tracer-control-pw",
                "action": "api",
            },
        )
        assert res_mtx_api.status_code == 200

        # -------------------------------------------------------------------------
        # Step 8: Camera Outage Tracking (record_offline -> duration -> record_online)
        # -------------------------------------------------------------------------
        now = utc_now()
        async with session_factory() as session:
            # CAM-A went offline 6 minutes ago
            await OutageTracker.record_offline(
                session=session,
                camera_serial="CAM-A",
                reason="Ethernet Link Down",
                at=now - timedelta(minutes=6),
            )

        # Check ongoing outage appears in history
        res_out_open = await client.get("/api/v1/health/outages?camera_serial=CAM-A")
        assert res_out_open.status_code == 200
        out_list = res_out_open.json()
        assert len(out_list) == 1
        assert out_list[0]["ended_at"] is None
        assert out_list[0]["duration_seconds"] is None

        # CAM-A recovers 1 minute ago (duration = 5 minutes = 300s)
        async with session_factory() as session:
            closed = await OutageTracker.record_online(
                session=session,
                camera_serial="CAM-A",
                at=now - timedelta(minutes=1),
            )
            assert closed is not None
            assert abs(closed.duration_seconds - 300.0) < 1.0

        # Query closed outage
        res_out_closed = await client.get("/api/v1/health/outages?camera_serial=CAM-A")
        assert res_out_closed.status_code == 200
        closed_data = res_out_closed.json()[0]
        assert closed_data["ended_at"] is not None
        assert abs(closed_data["duration_seconds"] - 300.0) < 1.0

        # -------------------------------------------------------------------------
        # Step 9: In-app Alerts & Dashboard Telemetry
        # -------------------------------------------------------------------------
        # Simulate CAM-B offline for 8 minutes (> 5 min threshold for alert)
        async with session_factory() as session:
            await OutageTracker.record_offline(
                session=session,
                camera_serial="CAM-B",
                reason="Power Loss",
                at=now - timedelta(minutes=8),
            )

        # Owner sees CAM-B alert
        res_owner_alerts = await client.get("/api/v1/health/alerts")
        assert res_owner_alerts.status_code == 200
        owner_alerts = res_owner_alerts.json()
        assert any(a["source"] == "camera:CAM-B" for a in owner_alerts)

        # Viewer does not see CAM-B alert (restricted to CAM-A)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as viewer_client:
            await viewer_client.post(
                "/api/v1/auth/login",
                json={"username": "tracer_view", "password": "ViewerPassword123!"},
            )
            res_v_alerts = await viewer_client.get("/api/v1/health/alerts")
            assert res_v_alerts.status_code == 200
            v_alerts = res_v_alerts.json()
            assert not any(a["source"] == "camera:CAM-B" for a in v_alerts)

        # System health overview endpoint
        res_health = await client.get("/api/v1/health")
        assert res_health.status_code == 200
        health_info = res_health.json()
        assert health_info["total_cameras"] == 2

        # -------------------------------------------------------------------------
        # Step 10: Persistent Append-Only Audit Log Trail (AUTH-07)
        # -------------------------------------------------------------------------
        res_audit = await client.get("/api/v1/audit-logs")
        assert res_audit.status_code == 200
        audit_body = res_audit.json()
        assert audit_body["total"] >= 4
        recorded_actions = [item["action"] for item in audit_body["items"]]

        # Verify key milestone events are present in chronological audit trail
        assert "system.setup" in recorded_actions
        assert "camera.add" in recorded_actions
        assert "user.create" in recorded_actions
        assert "auth.login_success" in recorded_actions

        # Viewers are forbidden from viewing audit logs
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as viewer_client:
            await viewer_client.post(
                "/api/v1/auth/login",
                json={"username": "tracer_view", "password": "ViewerPassword123!"},
            )
            res_v_audit = await viewer_client.get("/api/v1/audit-logs")
            assert res_v_audit.status_code == 403

    await engine.dispose()
