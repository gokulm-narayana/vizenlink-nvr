"""Integration tests validating health dashboard telemetry summary (HLTH-02, HLTH-06)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, Camera, User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_dashboard.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    async with session_factory() as session:
        # Camera 1: active
        cam1 = Camera(
            serial="CAM-DASH-01",
            host="192.168.1.101",
            https_port=443,
            mac="aa:00:00:00:00:01",
            name="Front Gate",
            location="Perimeter",
            group_tag="external",
            manufacturer="Generic",
            model="Pro1",
            firmware_version="1.0",
            hardware_id="h1",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )
        # Camera 2: unreachable
        cam2 = Camera(
            serial="CAM-DASH-02",
            host="192.168.1.102",
            https_port=443,
            mac="aa:00:00:00:00:02",
            name="Side Gate",
            location="Perimeter",
            group_tag="external",
            manufacturer="Generic",
            model="Pro2",
            firmware_version="1.0",
            hardware_id="h2",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="unreachable",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )

        owner = User(
            username="owner_dash",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        session.add_all([cam1, cam2, owner])
        await session.commit()
        await session.refresh(owner)

        sess = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        owner_session = sess.id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_summary_metrics(app_fixture) -> None:
    """Dashboard endpoint accurately reports system health and camera counts."""
    client, owner_session = app_fixture
    client.cookies.set("session_id", owner_session)

    # 1. Health summary
    res_health = await client.get("/api/v1/health")
    assert res_health.status_code == 200
    data = res_health.json()

    assert data["db_ok"] is True
    assert data["total_cameras"] == 2
    assert data["active_cameras"] == 1
    assert data["status"] in ("healthy", "degraded", "critical")

    # 2. Storage telemetry summary
    res_storage = await client.get("/api/v1/storage/status")
    assert res_storage.status_code == 200
    storage_data = res_storage.json()
    assert "storage_path" in storage_data
    assert "health_state" in storage_data

    # 3. Alerts endpoint
    res_alerts = await client.get("/api/v1/health/alerts")
    assert res_alerts.status_code == 200
    assert isinstance(res_alerts.json(), list)

