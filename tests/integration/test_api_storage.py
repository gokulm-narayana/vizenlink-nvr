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
    assert res_scan.json()["status"] == "completed"
    assert res_scan.json()["adopted"] == 0

    # 6. Overall system health endpoint
    res_health = await client.get("/api/v1/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert "status" in h_data
    assert h_data["db_ok"] is True


@pytest.mark.asyncio
async def test_refused_storage_path_leaves_settings_unchanged(
    app_fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected set-path request must not overwrite the working storage settings."""
    client, owner_session, _, tmp_path = app_fixture
    client.cookies.set("session_id", owner_session)

    good_dir = tmp_path / "good_recordings"
    res_good = await client.post(
        "/api/v1/storage/set-path",
        json={"storage_path": str(good_dir), "allow_system_disk": True},
    )
    assert res_good.status_code == 200
    saved = (await client.get("/api/v1/storage/status")).json()
    assert saved["allow_system_disk"] is True

    async def assert_unchanged() -> None:
        now = (await client.get("/api/v1/storage/status")).json()
        assert now["storage_path"] == saved["storage_path"]
        assert now["allow_system_disk"] is True
        assert now["health_state"] == saved["health_state"]

    # 1. System disk without the override: refused, nothing saved, no folder created.
    monkeypatch.setattr("vizenlink_nvr.services.storage.is_system_drive", lambda p: True)
    refused_dir = tmp_path / "refused_recordings"
    res_refused = await client.post(
        "/api/v1/storage/set-path",
        json={"storage_path": str(refused_dir), "allow_system_disk": False},
    )
    assert res_refused.status_code == 400
    assert not refused_dir.exists()
    await assert_unchanged()

    # 2. Relative path: rejected before any filesystem or database change.
    monkeypatch.chdir(tmp_path)
    res_relative = await client.post(
        "/api/v1/storage/set-path",
        json={"storage_path": "relative/dir", "allow_system_disk": True},
    )
    assert res_relative.status_code == 422
    assert not (tmp_path / "relative").exists()
    await assert_unchanged()

    # 3. A path that cannot be created (its parent is a file): refused, nothing saved.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    res_bad = await client.post(
        "/api/v1/storage/set-path",
        json={"storage_path": str(blocker / "recordings"), "allow_system_disk": True},
    )
    assert res_bad.status_code == 400
    await assert_unchanged()

    # None of the refused attempts is recorded as a storage change.
    logs = (await client.get("/api/v1/audit-logs", params={"action": "storage.update_path"})).json()
    items = logs if isinstance(logs, list) else logs.get("items", logs.get("logs", []))
    assert len(items) == 1


@pytest.mark.asyncio
async def test_recorder_settings_and_account_isolation(app_fixture) -> None:
    client, owner, viewer, _ = app_fixture
    client.cookies.set("session_id", viewer)
    system = {"recorder_name": "Front office", "site_timezone": "Asia/Kolkata"}
    assert (await client.put("/api/v1/system", json=system)).status_code == 403
    assert (await client.patch("/api/v1/auth/preferences", json={"theme": "dark"})).is_success
    assert (await client.patch("/api/v1/auth/preferences", json={"theme": "invalid"})).status_code == 422
    client.cookies.set("session_id", owner)
    assert (await client.get("/api/v1/auth/me")).json()["theme"] == "light"
    assert (await client.put("/api/v1/system", json=system)).json()["version"]
    assert (
        await client.put("/api/v1/system", json={**system, "site_timezone": "invalid"})
    ).status_code == 422
    client.cookies.clear()
    login = await client.post(
        "/api/v1/auth/login", json={"username": "owner_user", "password": "OwnerPassword123!"}
    )
    assert login.is_success
    assert (await client.post("/api/v1/auth/sessions/sign-out-others")).json() == {"revoked": 1}
    assert (await client.get("/api/v1/auth/me")).is_success
    client.cookies.clear()
    client.cookies.set("session_id", owner)
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    client.cookies.set("session_id", viewer)
    status = (await client.get("/api/v1/auth/status")).json()
    assert status["site_timezone"] == "Asia/Kolkata" and status["user"]["theme"] == "dark"
    assert (await client.get("/api/v1/system")).json()["recorder_name"] == "Front office"
