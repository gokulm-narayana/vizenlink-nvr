"""Integration test pinning POST /api/v1/cameras contract with main and sub streams (D-18, Plan 09-20)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.db.models import User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.registry import load_connection
from vizenlink_nvr.services.runtime import open_runtime
from vizenlink_nvr.services.session_manager import SESSION_COOKIE_NAME, SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_api_cameras_create_main_and_sub_streams(tmp_path: Path) -> None:
    """POST /api/v1/cameras with main and sub streams returns 201 and seals credentials in vault."""
    settings = load_settings(data_dir=tmp_path)
    async with open_runtime(settings) as rt:
        app = create_app(session_factory=rt.sessions, runtime=rt)

        now = utc_now()
        async with rt.sessions() as session:
            # Create operator
            operator = User(
                username="op_user",
                password_hash=hash_password("OperatorPass123!"),
                role="operator",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(operator)

            # Create viewer
            viewer = User(
                username="view_user",
                password_hash=hash_password("ViewerPass123!"),
                role="viewer",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(viewer)
            await session.commit()
            await session.refresh(operator)
            await session.refresh(viewer)

            op_sess = await SessionManager.create_session(session, operator.id, "127.0.0.1", "test")
            op_token = op_sess.id

            view_sess = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "test")
            view_token = view_sess.id

        transport = ASGITransport(app=app)

        # 1. Operator posts camera with main and sub streams
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: op_token},
        ) as op_client:
            payload = {
                "serial": "CAM-MAIN-SUB-1",
                "host": "192.168.1.150",
                "https_port": 443,
                "username": "admin",
                "password": "CameraSecurePass1!",
                "name": "Gate Camera",
                "location": "North Gate",
                "group_tag": "perimeter",
                "streams": [
                    {
                        "role": "main",
                        "profile_token": "Profile_1",
                        "profile_name": "MainStream",
                        "venc_token": "VideoEncoder_1",
                        "codec": "H264",
                        "width": 1920,
                        "height": 1080,
                        "transport": "tcp",
                        "scheme": "rtsp",
                        "port": 554,
                        "path": "/stream1",
                    },
                    {
                        "role": "sub",
                        "profile_token": "Profile_2",
                        "profile_name": "SubStream",
                        "venc_token": "VideoEncoder_2",
                        "codec": "H264",
                        "width": 1920,
                        "height": 1080,
                        "transport": "tcp",
                        "scheme": "rtsp",
                        "port": 554,
                        "path": "/stream2",
                    },
                ],
            }

            res = await op_client.post("/api/v1/cameras", json=payload)
            assert res.status_code == 201, f"Expected 201 Created, got {res.status_code}: {res.text}"
            data = res.json()
            assert data["serial"] == "CAM-MAIN-SUB-1"
            assert data["name"] == "Gate Camera"
            assert len(data["streams"]) == 2
            roles = [s["role"] for s in data["streams"]]
            assert "main" in roles
            assert "sub" in roles

            # Verify credential was sealed and can be opened with runtime vault
            async with rt.sessions() as session:
                conn = await load_connection(session, rt.vault, "CAM-MAIN-SUB-1")
                assert conn.password.get_secret_value() == "CameraSecurePass1!"

            # 2. Duplicate serial returns 409
            dup_res = await op_client.post("/api/v1/cameras", json=payload)
            assert dup_res.status_code == 409
            assert "already exists" in dup_res.json()["detail"]

        # 3. Viewer attempting to add camera gets 403 Forbidden
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: view_token},
        ) as view_client:
            viewer_res = await view_client.post("/api/v1/cameras", json=payload)
            assert viewer_res.status_code == 403
