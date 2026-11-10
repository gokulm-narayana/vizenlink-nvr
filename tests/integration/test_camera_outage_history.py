"""Integration tests for camera outage history and alerts API (HLTH-07, HLTH-08)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, Camera, User, UserCameraPermission
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.outage_tracker import OutageTracker
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_outage_history.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    async with session_factory() as session:
        cam1 = Camera(
            serial="CAM-OUT-01",
            host="192.168.1.70",
            https_port=443,
            mac="11:22:33:44:55:66",
            name="Loading Dock",
            location="Warehouse",
            group_tag="dock",
            manufacturer="Generic",
            model="C1",
            firmware_version="1.0",
            hardware_id="h1",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )
        cam2 = Camera(
            serial="CAM-OUT-02",
            host="192.168.1.71",
            https_port=443,
            mac="11:22:33:44:55:77",
            name="Server Room",
            location="IT",
            group_tag="secure",
            manufacturer="Generic",
            model="C2",
            firmware_version="1.0",
            hardware_id="h2",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )

        owner = User(
            username="owner_outage",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer = User(
            username="viewer_outage",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer.permissions.append(
            UserCameraPermission(camera_serial="CAM-OUT-01", created_at=utc_now())
        )

        session.add_all([cam1, cam2, owner, viewer])
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
        yield client, owner_session, viewer_session, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_outage_tracker_lifecycle_and_api(app_fixture) -> None:
    """Test offline/online lifecycle, duration calculation, and outage history API."""
    client, owner_session, viewer_session, session_factory = app_fixture
    now = utc_now()

    async with session_factory() as session:
        # 1. Record offline event for CAM-OUT-01 at T-10m
        t_start = now - timedelta(minutes=10)
        outage1 = await OutageTracker.record_offline(
            session=session,
            camera_serial="CAM-OUT-01",
            reason="Cable disconnected",
            at=t_start,
        )
        assert outage1.ended_at is None
        assert outage1.duration_seconds is None

        # 2. Record second offline event for CAM-OUT-01 (should reuse existing open outage)
        outage1_reuse = await OutageTracker.record_offline(
            session=session,
            camera_serial="CAM-OUT-01",
            reason="Still disconnected",
            at=now - timedelta(minutes=8),
        )
        assert outage1_reuse.id == outage1.id
        assert outage1_reuse.started_at == t_start

        # 3. Record online event at T-4m (duration = 6 minutes = 360s)
        t_end = now - timedelta(minutes=4)
        closed_outage = await OutageTracker.record_online(
            session=session,
            camera_serial="CAM-OUT-01",
            at=t_end,
        )
        assert closed_outage is not None
        assert closed_outage.ended_at == t_end
        assert abs(closed_outage.duration_seconds - 360.0) < 1.0

        # 4. Open ongoing outage for CAM-OUT-02
        await OutageTracker.record_offline(
            session=session,
            camera_serial="CAM-OUT-02",
            reason="Power loss",
            at=now - timedelta(minutes=7),
        )

    # 5. Owner queries outage history
    client.cookies.set("session_id", owner_session)
    res_outages = await client.get("/api/v1/health/outages")
    assert res_outages.status_code == 200
    all_outages = res_outages.json()
    assert len(all_outages) == 2
    serials = {o["camera_serial"] for o in all_outages}
    assert serials == {"CAM-OUT-01", "CAM-OUT-02"}

    # 6. Viewer queries outages -> only CAM-OUT-01 allowed
    client.cookies.set("session_id", viewer_session)
    res_viewer_outages = await client.get("/api/v1/health/outages")
    assert res_viewer_outages.status_code == 200
    v_outages = res_viewer_outages.json()
    assert len(v_outages) == 1
    assert v_outages[0]["camera_serial"] == "CAM-OUT-01"

    # 7. Viewer queries specific restricted camera -> 403 Forbidden
    res_forbidden = await client.get("/api/v1/health/outages?camera_serial=CAM-OUT-02")
    assert res_forbidden.status_code == 403

    # 8. Active alerts API
    res_alerts = await client.get("/api/v1/health/alerts")
    assert res_alerts.status_code == 200
    # CAM-OUT-02 is offline 7 min, but viewer cannot see it, only allowed camera alerts
    v_alerts = res_alerts.json()
    assert not any(a["source"] == "camera:CAM-OUT-02" for a in v_alerts)

    # Owner can see CAM-OUT-02 offline alert
    client.cookies.set("session_id", owner_session)
    res_owner_alerts = await client.get("/api/v1/health/alerts")
    assert res_owner_alerts.status_code == 200
    owner_alerts = res_owner_alerts.json()
    # Titles use the camera name (or serial when unnamed); the serial is always in source.
    assert any(a["source"] == "camera:CAM-OUT-02" and a["title"].endswith("is offline") for a in owner_alerts)

