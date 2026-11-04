"""Integration tests for /api/v1/storage and /api/v1/health endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_api_storage.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    async with session_factory() as session:
        owner = User(
            username="owner_user",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer = User(
            username="viewer_user",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        session.add_all([owner, viewer])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(viewer)

        s_owner = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        s_viewer = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "test")

        owner_session = s_owner.id
        viewer_session = s_viewer.id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_session, viewer_session, tmp_path

    await engine.dispose()


@pytest.mark.asyncio
async def test_storage_status_and_path_configuration(app_fixture) -> None:
    """Test storage telemetry, path configuration with system drive guard, and health."""
    client, owner_session, viewer_session, tmp_path = app_fixture

    # 1. Anonymous storage status fails
    res_anon = await client.get("/api/v1/storage/status")
    assert res_anon.status_code == 401

    # 2. Viewer gets storage status -> 200
    client.cookies.set("session_id", viewer_session)
    res_status = await client.get("/api/v1/storage/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert "storage_path" in data
    assert "health_state" in data

    # 3. Viewer attempts to change storage path -> 403 Forbidden
    custom_dir = tmp_path / "nvr_recordings"
    custom_dir.mkdir(parents=True, exist_ok=True)
    res_v_set = await client.post(
        "/api/v1/storage/set-path",
        json={"storage_path": str(custom_dir), "allow_system_disk": True},
    )
    assert res_v_set.status_code == 403

    # 4. Owner changes storage path
    client.cookies.set("session_id", owner_session)
    res_set = await client.post(
        "/api/v1/storage/set-path",
        json={"storage_path": str(custom_dir), "allow_system_disk": True},
    )
    assert res_set.status_code == 200
    assert str(custom_dir) in res_set.json()["storage_path"]

    # 5. Owner triggers storage scan
    res_scan = await client.post("/api/v1/storage/scan")
    assert res_scan.status_code == 200
    assert res_scan.json()["status"] == "scan_started"

    # 6. Overall system health endpoint
    res_health = await client.get("/api/v1/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert "status" in h_data
    assert h_data["db_ok"] is True

