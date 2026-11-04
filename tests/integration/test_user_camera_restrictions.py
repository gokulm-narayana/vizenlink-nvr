"""Integration tests for per-user camera restriction rules (AUTH-05)."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.services.setup import SetupService
from vizenlink_nvr.timeutil import utc_now


@pytest.mark.asyncio
async def test_camera_whitelist_restriction_lifecycle(tmp_path: Path) -> None:
    """Test camera access restriction enforcement and dynamic updates via user management."""
    db_file = tmp_path / "test_cam_restrict.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_dir = tmp_path / "rec"
    storage_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()

    # 1. Initialize Owner and 2 cameras
    async with session_factory() as session:
        owner = await SetupService.initialize_nvr(
            db=session,
            owner_username="nvr_admin",
            owner_password="AdminPassword123!",
            timezone="UTC",
            storage_path=storage_dir,
            allow_system_disk=True,
        )
        cam_a = Camera(
            serial="CAM-AAA",
            host="192.168.1.10",
            tls_fingerprint_sha256="fake_sha_a",
            added_at=now,
            host_updated_at=now,
        )
        cam_b = Camera(
            serial="CAM-BBB",
            host="192.168.1.11",
            tls_fingerprint_sha256="fake_sha_b",
            added_at=now,
            host_updated_at=now,
        )
        session.add_all([cam_a, cam_b])
        await session.commit()

        sess_owner = await SessionManager.create_session(session, owner.id)
        owner_token = sess_owner.id

    app = create_app(session_factory=session_factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as admin_client:
        admin_client.cookies.set("session_id", owner_token)

        # 2. Create Viewer 1 restricted to CAM-AAA
        res_v1 = await admin_client.post(
            "/api/v1/users",
            json={
                "username": "guard_alpha",
                "password": "GuardPassword123!",
                "role": "viewer",
                "permissions": ["CAM-AAA"],
            },
        )
        assert res_v1.status_code == 201
        guard_alpha_id = res_v1.json()["id"]

    # 3. Authenticate as guard_alpha and verify permissions in /auth/me
    async with AsyncClient(transport=transport, base_url="http://test") as viewer_client:
        res_login = await viewer_client.post(
            "/api/v1/auth/login",
            json={"username": "guard_alpha", "password": "GuardPassword123!"},
        )
        assert res_login.status_code == 200

        res_me = await viewer_client.get("/api/v1/auth/me")
        assert res_me.status_code == 200
        assert res_me.json()["permissions"] == ["CAM-AAA"]

    # 4. Admin updates guard_alpha permissions to grant CAM-BBB as well
    async with AsyncClient(transport=transport, base_url="http://test") as admin_client:
        admin_client.cookies.set("session_id", owner_token)
        res_update = await admin_client.patch(
            f"/api/v1/users/{guard_alpha_id}",
            json={"permissions": ["CAM-AAA", "CAM-BBB"]},
        )
        assert res_update.status_code == 200
        assert set(res_update.json()["permissions"]) == {"CAM-AAA", "CAM-BBB"}

    # 5. guard_alpha checks /auth/me and immediately reflects new permissions
    async with AsyncClient(transport=transport, base_url="http://test") as viewer_client:
        await viewer_client.post(
            "/api/v1/auth/login",
            json={"username": "guard_alpha", "password": "GuardPassword123!"},
        )
        res_me_updated = await viewer_client.get("/api/v1/auth/me")
        assert res_me_updated.status_code == 200
        assert set(res_me_updated.json()["permissions"]) == {"CAM-AAA", "CAM-BBB"}

    await engine.dispose()
