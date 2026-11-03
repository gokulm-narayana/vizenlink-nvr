"""Integration tests for session lifecycle, authentication, and password updates (AUTH-02)."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.services.setup import SetupService


@pytest.mark.asyncio
async def test_auth_login_me_password_logout_flow(tmp_path: Path) -> None:
    """Test full login, me, password change, and logout session flow."""
    db_file = tmp_path / "test_sessions.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_dir = tmp_path / "rec"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Owner via service
    async with session_factory() as session:
        await SetupService.initialize_nvr(
            db=session,
            owner_username="john_owner",
            owner_password="InitialPassword123!",
            timezone="UTC",
            storage_path=storage_dir,
            allow_system_disk=True,
        )

    app = create_app(session_factory=session_factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request to /me fails with 401
        res_unauth = await client.get("/api/v1/auth/me")
        assert res_unauth.status_code == 401

        # 2. Login with bad password fails with 401
        res_bad = await client.post(
            "/api/v1/auth/login",
            json={"username": "john_owner", "password": "WrongPassword!"},
        )
        assert res_bad.status_code == 401

        # 3. Login with correct password succeeds
        res_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "john_owner", "password": "InitialPassword123!"},
        )
        assert res_login.status_code == 200
        assert "session_id" in client.cookies

        # 4. Request /me with session cookie succeeds
        res_me = await client.get("/api/v1/auth/me")
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["username"] == "john_owner"
        assert me_data["role"] == "owner"
        assert me_data["is_active"] is True

        # 5. Change password
        res_pw = await client.post(
            "/api/v1/auth/password",
            json={
                "current_password": "InitialPassword123!",
                "new_password": "BrandNewPassword456!",
            },
        )
        assert res_pw.status_code == 200
        assert res_pw.json()["success"] is True

        # 6. Still logged in with new session cookie
        res_me2 = await client.get("/api/v1/auth/me")
        assert res_me2.status_code == 200

        # 7. Old password no longer works
        async with AsyncClient(transport=transport, base_url="http://test") as client2:
            res_old = await client2.post(
                "/api/v1/auth/login",
                json={"username": "john_owner", "password": "InitialPassword123!"},
            )
            assert res_old.status_code == 401

            # New password works
            res_new = await client2.post(
                "/api/v1/auth/login",
                json={"username": "john_owner", "password": "BrandNewPassword456!"},
            )
            assert res_new.status_code == 200

        # 8. Logout invalidates session
        res_logout = await client.post("/api/v1/auth/logout")
        assert res_logout.status_code == 200

        # 9. Request /me after logout fails with 401
        res_me_logged_out = await client.get("/api/v1/auth/me")
        assert res_me_logged_out.status_code == 401

    await engine.dispose()
