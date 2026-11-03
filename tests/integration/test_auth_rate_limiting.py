"""Integration tests for brute-force rate-limiting on login (AUTH-02)."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.services.rate_limiter import login_rate_limiter
from vizenlink_nvr.services.setup import SetupService


@pytest.mark.asyncio
async def test_brute_force_login_lockout(tmp_path: Path) -> None:
    """Verify that 5 failed login attempts trigger HTTP 429 lockout."""
    db_file = tmp_path / "test_rate_limit.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage_dir = tmp_path / "rec"
    storage_dir.mkdir(parents=True, exist_ok=True)

    username = "target_account"
    correct_pw = "ValidPassword123!"

    # Initialize Owner account
    async with session_factory() as session:
        await SetupService.initialize_nvr(
            db=session,
            owner_username=username,
            owner_password=correct_pw,
            timezone="UTC",
            storage_path=storage_dir,
            allow_system_disk=True,
        )

    # Ensure rate limiter is clean for this test
    login_rate_limiter.reset(username)
    login_rate_limiter.reset("127.0.0.1")

    app = create_app(session_factory=session_factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1-4 failures return 401
        for i in range(4):
            res = await client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": f"wrong_{i}"},
            )
            assert res.status_code == 401

        # 5th failure triggers lockout, returns 401
        res5 = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "wrong_5"},
        )
        assert res5.status_code == 401

        # 6th attempt (even with CORRECT password) is rejected with 429 Too Many Requests
        res6 = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": correct_pw},
        )
        assert res6.status_code == 429
        assert "temporarily locked" in res6.json()["detail"]

        # Reset rate limiter
        login_rate_limiter.reset(username)
        login_rate_limiter.reset("127.0.0.1")

        # Now correct password succeeds
        res_ok = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": correct_pw},
        )
        assert res_ok.status_code == 200

    await engine.dispose()
