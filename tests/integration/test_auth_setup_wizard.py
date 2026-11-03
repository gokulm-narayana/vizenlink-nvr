"""Integration tests for the First-Run Setup Wizard (AUTH-01)."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head


@pytest.mark.asyncio
async def test_setup_wizard_flow(tmp_path: Path) -> None:
    """Test first-run wizard: uninitialized check, validation, initialization, and lock."""
    db_file = tmp_path / "test_setup.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app(session_factory=session_factory)
    transport = ASGITransport(app=app)

    storage_dir = tmp_path / "recordings"
    storage_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initial status: uninitialized
        res = await client.get("/api/v1/auth/status")
        assert res.status_code == 200
        data = res.json()
        assert data["initialized"] is False
        assert data["authenticated"] is False
        assert data["user"] is None

        # 2. Reject password < 8 characters
        bad_payload = {
            "owner_username": "admin",
            "owner_password": "short",  # 5 chars
            "timezone": "UTC",
            "storage_path": str(storage_dir),
            "allow_system_disk": True,
        }
        res_bad = await client.post("/api/v1/auth/setup", json=bad_payload)
        assert res_bad.status_code == 422 or res_bad.status_code == 400

        # 3. Successful setup
        good_payload = {
            "owner_username": "owner_admin",
            "owner_password": "securePassword123!",
            "timezone": "UTC",
            "storage_path": str(storage_dir),
            "allow_system_disk": True,
        }
        res_setup = await client.post("/api/v1/auth/setup", json=good_payload)
        assert res_setup.status_code == 200
        setup_data = res_setup.json()
        assert setup_data["success"] is True
        assert setup_data["user"]["username"] == "owner_admin"
        assert setup_data["user"]["role"] == "owner"

        # Cookie was set
        assert "session_id" in client.cookies

        # 4. Status is now initialized and authenticated
        res_status2 = await client.get("/api/v1/auth/status")
        assert res_status2.status_code == 200
        data2 = res_status2.json()
        assert data2["initialized"] is True
        assert data2["authenticated"] is True
        assert data2["user"]["username"] == "owner_admin"
        assert data2["user"]["role"] == "owner"

        # 5. Subsequent setup attempt is locked out (HTTP 400)
        res_repeat = await client.post("/api/v1/auth/setup", json=good_payload)
        assert res_repeat.status_code == 400
        assert "already initialized" in res_repeat.json()["detail"]

    await engine.dispose()
