"""Integration tests for /api/v1/cameras endpoints and RBAC filtering."""

from __future__ import annotations

import types
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, User, UserCameraPermission
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_api_cameras.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(
        session_factory=session_factory,
        runtime=types.SimpleNamespace(vault=Vault(b"0" * 32, "test-vault-key", "memory")),
    )

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
        viewer.permissions.append(UserCameraPermission(camera_serial="CAM-PERMITTED", created_at=utc_now()))

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
        yield client, owner_session, viewer_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_camera_crud_and_rbac_filtering(app_fixture) -> None:
    """Test camera onboarding, listing filtered by permissions, and deletion."""
    client, owner_session, viewer_session = app_fixture

    # 1. Owner onboards CAM-PERMITTED
    client.cookies.set("session_id", owner_session)
    res_add1 = await client.post(
        "/api/v1/cameras",
        json={
            "serial": "CAM-PERMITTED",
            "host": "192.168.1.10",
            "https_port": 443,
            "mac": "00:11:22:33:44:55",
            "name": "Front Door",
            "location": "Entrance",
            "group_tag": "exterior",
            "manufacturer": "Axis",
            "model": "M3005",
            "firmware_version": "9.80",
            "hardware_id": "revA",
            "streams": [
                {
                    "role": "main",
                    "profile_token": "prof_main",
                    "profile_name": "Main",
                    "venc_token": "venc_1",
                    "codec": "H264",
                    "width": 1920,
                    "height": 1080,
                    "path": "/stream1",
                }
            ],
        },
    )
    assert res_add1.status_code == 201
    assert res_add1.json()["serial"] == "CAM-PERMITTED"

    # 2. Owner onboards CAM-SECRET
    res_add2 = await client.post(
        "/api/v1/cameras",
        json={
            "serial": "CAM-SECRET",
            "host": "192.168.1.11",
            "https_port": 443,
            "mac": "00:11:22:33:44:66",
            "name": "Vault",
            "location": "Basement",
            "group_tag": "secure",
            "manufacturer": "Hanwha",
            "model": "XNV-6080",
            "firmware_version": "1.20",
            "hardware_id": "revB",
            "streams": [],
        },
    )
    assert res_add2.status_code == 201

    # 3. Owner list shows both cameras
    res_owner_list = await client.get("/api/v1/cameras")
    assert res_owner_list.status_code == 200
    serials = [c["serial"] for c in res_owner_list.json()]
    assert set(serials) == {"CAM-PERMITTED", "CAM-SECRET"}

    # 4. Viewer list shows ONLY CAM-PERMITTED (AUTH-05)
    client.cookies.set("session_id", viewer_session)
    res_viewer_list = await client.get("/api/v1/cameras")
    assert res_viewer_list.status_code == 200
    viewer_serials = [c["serial"] for c in res_viewer_list.json()]
    assert viewer_serials == ["CAM-PERMITTED"]

    # 5. Viewer gets CAM-PERMITTED -> 200
    res_v_get1 = await client.get("/api/v1/cameras/CAM-PERMITTED")
    assert res_v_get1.status_code == 200
    assert res_v_get1.json()["name"] == "Front Door"

    # 6. Viewer gets CAM-SECRET -> 403 Forbidden
    res_v_get2 = await client.get("/api/v1/cameras/CAM-SECRET")
    assert res_v_get2.status_code == 403

    # 7. Viewer attempts onboarding -> 403 Forbidden
    res_v_add = await client.post(
        "/api/v1/cameras",
        json={"serial": "CAM-FAIL", "host": "192.168.1.12"},
    )
    assert res_v_add.status_code == 403

    # 8. Viewer attempts delete -> 403 Forbidden
    res_v_del = await client.delete("/api/v1/cameras/CAM-PERMITTED")
    assert res_v_del.status_code == 403

    # 9. Owner reprobes camera -> 200 OK
    client.cookies.set("session_id", owner_session)
    res_reprobe = await client.post("/api/v1/cameras/CAM-PERMITTED/reprobe")
    assert res_reprobe.status_code == 200
    # Phase 10: the endpoint now really probes the camera. Without a live runtime (this test
    # app has none) it must say it did NOT probe, instead of the old stub's "reprobed": true.
    assert res_reprobe.json()["reprobed"] is False
    assert res_reprobe.json()["status"] == "active"

    # 10. Owner deletes CAM-SECRET
    res_del = await client.delete("/api/v1/cameras/CAM-SECRET?keep_recordings=true")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # 11. Verify CAM-SECRET is gone
    res_after = await client.get("/api/v1/cameras/CAM-SECRET")
    assert res_after.status_code == 404
