"""Integration tests for User Management REST API (AUTH-04)."""

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
async def test_user_management_crud_and_guards(tmp_path: Path) -> None:
    """Test full CRUD operations on user accounts and administrative guards."""
    db_file = tmp_path / "test_user_mgmt.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_dir = tmp_path / "rec"
    storage_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()

    # 1. Initialize Owner and seed a camera
    async with session_factory() as session:
        owner = await SetupService.initialize_nvr(
            db=session,
            owner_username="super_owner",
            owner_password="SuperPassword123!",
            timezone="UTC",
            storage_path=storage_dir,
            allow_system_disk=True,
        )
        cam = Camera(
            serial="CAM-MGMT-01",
            host="192.168.1.100",
            tls_fingerprint_sha256="fake_sha",
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)
        await session.commit()

        sess_owner = await SessionManager.create_session(session, owner.id)
        owner_token = sess_owner.id
        owner_id = owner.id

    app = create_app(session_factory=session_factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated request fails with 401
        res_unauth = await client.get("/api/v1/users")
        assert res_unauth.status_code == 401

        # Authenticate as Owner
        client.cookies.set("session_id", owner_token)

        # 2. List users: should contain only the owner initially
        res_list = await client.get("/api/v1/users")
        assert res_list.status_code == 200
        users_list = res_list.json()
        assert len(users_list) == 1
        assert users_list[0]["username"] == "super_owner"
        assert users_list[0]["role"] == "owner"

        # 3. Create Operator user
        res_create_op = await client.post(
            "/api/v1/users",
            json={
                "username": "alice_op",
                "password": "AlicePassword123!",
                "role": "operator",
            },
        )
        assert res_create_op.status_code == 201
        op_data = res_create_op.json()
        assert op_data["username"] == "alice_op"
        assert op_data["role"] == "operator"
        alice_id = op_data["id"]

        # 4. Create Viewer user with camera permission
        res_create_view = await client.post(
            "/api/v1/users",
            json={
                "username": "bob_viewer",
                "password": "BobPassword123!",
                "role": "viewer",
                "permissions": ["CAM-MGMT-01"],
            },
        )
        assert res_create_view.status_code == 201
        view_data = res_create_view.json()
        assert view_data["username"] == "bob_viewer"
        assert view_data["permissions"] == ["CAM-MGMT-01"]
        bob_id = view_data["id"]

        # 5. Reject duplicate username
        res_dup = await client.post(
            "/api/v1/users",
            json={
                "username": "alice_op",
                "password": "DuplicatePassword123!",
                "role": "operator",
            },
        )
        assert res_dup.status_code == 409

        # 6. Reject invalid role
        res_bad_role = await client.post(
            "/api/v1/users",
            json={
                "username": "charlie_bad",
                "password": "CharliePassword123!",
                "role": "superadmin",
            },
        )
        assert res_bad_role.status_code == 400

        # 7. Reject nonexistent camera serial in permissions
        res_bad_cam = await client.post(
            "/api/v1/users",
            json={
                "username": "charlie_cam",
                "password": "CharliePassword123!",
                "role": "viewer",
                "permissions": ["NONEXISTENT-CAM"],
            },
        )
        assert res_bad_cam.status_code == 400

        # 8. Get user detail
        res_get_bob = await client.get(f"/api/v1/users/{bob_id}")
        assert res_get_bob.status_code == 200
        assert res_get_bob.json()["username"] == "bob_viewer"

        # 9. Update user: disable alice_op
        res_patch_alice = await client.patch(
            f"/api/v1/users/{alice_id}",
            json={"is_active": False},
        )
        assert res_patch_alice.status_code == 200
        assert res_patch_alice.json()["is_active"] is False

        # 10. Owner self-modification protections:
        # Owner cannot disable self
        res_self_disable = await client.patch(
            f"/api/v1/users/{owner_id}",
            json={"is_active": False},
        )
        assert res_self_disable.status_code == 400
        assert "Owners cannot disable their own account" in res_self_disable.json()["detail"]

        # Owner cannot demote self
        res_self_demote = await client.patch(
            f"/api/v1/users/{owner_id}",
            json={"role": "viewer"},
        )
        assert res_self_demote.status_code == 400
        assert "Owners cannot demote their own account" in res_self_demote.json()["detail"]

        # 11. Admin password reset
        res_reset = await client.post(
            f"/api/v1/users/{bob_id}/reset-password",
            json={"new_password": "NewBobPassword456!"},
        )
        assert res_reset.status_code == 200
        assert res_reset.json()["success"] is True

        # Verify bob can login with new password
        async with AsyncClient(transport=transport, base_url="http://test") as bob_client:
            res_bob_login = await bob_client.post(
                "/api/v1/auth/login",
                json={"username": "bob_viewer", "password": "NewBobPassword456!"},
            )
            assert res_bob_login.status_code == 200

    await engine.dispose()
