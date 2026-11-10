"""Integration tests for site_timezone exposure on /api/v1/auth/status (D-15)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.engine import create_engine_for, upgrade_to_head
from vizenlink_nvr.services.settings import SITE_TIMEZONE_KEY, put_setting
from vizenlink_nvr.timeutil import default_site_zone_name


@pytest.fixture
def test_db_app(tmp_path: Path) -> tuple[Any, Any]:
    db_file = tmp_path / "test_auth_tz.db"
    upgrade_to_head(db_file)
    engine = create_engine_for(db_file)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(session_factory=session_factory)
    return app, session_factory


@pytest.mark.asyncio
async def test_auth_status_site_timezone_lifecycle(
    test_db_app: tuple[Any, Any],
    tmp_path: Path,
) -> None:
    app, session_factory = test_db_app
    transport = ASGITransport(app=app)
    storage_dir = tmp_path / "recordings"
    storage_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Signed out / uninitialized: site_timezone is null
        res_initial = await client.get("/api/v1/auth/status")
        assert res_initial.status_code == 200
        data_initial = res_initial.json()
        assert data_initial["authenticated"] is False
        assert data_initial.get("site_timezone") is None

        # 2. Setup with timezone "Asia/Kolkata"
        setup_payload = {
            "owner_username": "site_owner",
            "owner_password": "superPassword123!",
            "timezone": "Asia/Kolkata",
            "storage_path": str(storage_dir),
            "allow_system_disk": True,
        }
        res_setup = await client.post("/api/v1/auth/setup", json=setup_payload)
        assert res_setup.status_code == 200

        # Signed in as owner: site_timezone is "Asia/Kolkata"
        res_auth = await client.get("/api/v1/auth/status")
        assert res_auth.status_code == 200
        data_auth = res_auth.json()
        assert data_auth["authenticated"] is True
        assert data_auth.get("site_timezone") == "Asia/Kolkata"

        # 3. Signed out check: second unauthenticated client gets site_timezone is null
        async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
            res_anon = await anon_client.get("/api/v1/auth/status")
            assert res_anon.status_code == 200
            data_anon = res_anon.json()
            assert data_anon["authenticated"] is False
            assert data_anon.get("site_timezone") is None

        # 4. Corrupt stored timezone: fallback to default_site_zone_name()
        async with session_factory() as session:
            await put_setting(session, SITE_TIMEZONE_KEY, "Invalid/Not_A_Real_Zone")
            await session.commit()

        res_corrupt = await client.get("/api/v1/auth/status")
        assert res_corrupt.status_code == 200
        data_corrupt = res_corrupt.json()
        assert data_corrupt["authenticated"] is True
        expected_fallback = default_site_zone_name()
        assert data_corrupt.get("site_timezone") == expected_fallback
        assert data_corrupt.get("site_timezone") != "Invalid/Not_A_Real_Zone"