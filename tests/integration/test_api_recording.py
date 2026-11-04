"""Integration tests for /api/v1/recording endpoints and RBAC."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, Camera, User, UserCameraPermission
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_api_recording.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    async with session_factory() as session:
        # Create cameras
        cam1 = Camera(
            serial="CAM-REC-1",
            host="192.168.1.50",
            https_port=443,
            mac="aa:bb:cc:dd:ee:01",
            name="Hallway",
            location="Indoor",
            group_tag="hall",
            manufacturer="Generic",
            model="Cam1",
            firmware_version="1.0",
            hardware_id="h1",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )
        cam2 = Camera(
            serial="CAM-REC-2",
            host="192.168.1.51",
            https_port=443,
            mac="aa:bb:cc:dd:ee:02",
            name="Backyard",
            location="Outdoor",
            group_tag="perimeter",
            manufacturer="Generic",
            model="Cam2",
            firmware_version="1.0",
            hardware_id="h2",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )

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
        viewer.permissions.append(
            UserCameraPermission(camera_serial="CAM-REC-1", created_at=utc_now())
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
        yield client, owner_session, viewer_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_recording_status_and_update(app_fixture) -> None:
    """Test recording status listing and patch updates with RBAC."""
    client, owner_session, viewer_session = app_fixture

    # 1. Owner gets recording status for all cameras
    client.cookies.set("session_id", owner_session)
    res_status = await client.get("/api/v1/recording/status")
    assert res_status.status_code == 200
    items = res_status.json()
    assert len(items) == 2
    assert {i["camera_serial"] for i in items} == {"CAM-REC-1", "CAM-REC-2"}

    # 2. Viewer gets recording status -> only permitted camera
    client.cookies.set("session_id", viewer_session)
    res_v_status = await client.get("/api/v1/recording/status")
    assert res_v_status.status_code == 200
    v_items = res_v_status.json()
    assert len(v_items) == 1
    assert v_items[0]["camera_serial"] == "CAM-REC-1"

    # 3. Viewer attempts to update recording settings -> 403 Forbidden
    res_v_patch = await client.patch(
        "/api/v1/recording/CAM-REC-1",
        json={"mode": "continuous"},
    )
    assert res_v_patch.status_code == 403

    # 4. Owner updates CAM-REC-1 mode and retention
    client.cookies.set("session_id", owner_session)
    res_patch = await client.patch(
        "/api/v1/recording/CAM-REC-1",
        json={
            "mode": "continuous",
            "retention_days": 14,
            "retention_max_gb": 500,
        },
    )
    assert res_patch.status_code == 200
    data = res_patch.json()
    assert data["camera_serial"] == "CAM-REC-1"
    assert data["mode"] == "continuous"
    assert data["retention_days"] == 14
    assert data["retention_max_gb"] == 500

    # 5. Invalid mode rejected with 400
    res_bad = await client.patch(
        "/api/v1/recording/CAM-REC-1",
        json={"mode": "non_existent_mode"},
    )
    assert res_bad.status_code == 400

