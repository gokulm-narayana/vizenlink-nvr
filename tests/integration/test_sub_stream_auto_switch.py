"""Integration tests for sub-stream default and main-stream auto-switch (LIVE-03)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, Camera, User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.live_view import TileControlsModel
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_fixture(tmp_path: Path):
    db_path = tmp_path / "test_stream_switch.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)

    async with session_factory() as session:
        cam = Camera(
            serial="CAM-STREAM-TEST",
            host="192.168.1.80",
            https_port=443,
            mac="12:34:56:78:9a:bc",
            name="Main Yard",
            location="Outside",
            group_tag="perimeter",
            manufacturer="Generic",
            model="ProCam",
            firmware_version="2.0",
            hardware_id="h2",
            tls_fingerprint_sha256="",
            camera_id_check=True,
            state="active",
            added_at=utc_now(),
            host_updated_at=utc_now(),
        )
        owner = User(
            username="owner_stream",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add_all([cam, owner])
        await session.commit()
        await session.refresh(owner)

        sess = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        session_token = sess.id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_token

    await engine.dispose()


@pytest.mark.asyncio
async def test_sub_stream_default_and_main_stream_switch(app_fixture) -> None:
    """Tiles use sub-stream by default and dynamically request main-stream on zoom/maximize."""
    client, session_token = app_fixture
    client.cookies.set("session_id", session_token)

    tile = TileControlsModel(
        camera_serial="CAM-STREAM-TEST",
        camera_name="Main Yard",
    )

    # 1. Default active stream is sub
    assert tile.active_stream == "sub"
    assert tile.is_maximized is False

    # 2. In grid mode, tile requests sub-stream token from API
    res_sub = await client.post(
        f"/api/v1/cameras/{tile.camera_serial}/media-token?stream={tile.active_stream}"
    )
    assert res_sub.status_code == 200
    sub_data = res_sub.json()
    assert sub_data["stream"] == "sub"
    assert sub_data["path"] == f"cam/{tile.camera_serial}/sub"

    # 3. User clicks maximize -> tile switches to main-stream
    new_stream = tile.toggle_maximize()
    assert new_stream == "main"
    assert tile.is_maximized is True
    assert tile.active_stream == "main"

    # 4. Maximized tile requests main-stream token from API
    res_main = await client.post(
        f"/api/v1/cameras/{tile.camera_serial}/media-token?stream={tile.active_stream}"
    )
    assert res_main.status_code == 200
    main_data = res_main.json()
    assert main_data["stream"] == "main"
    assert main_data["path"] == f"cam/{tile.camera_serial}/main"

    # 5. User restores tile (un-maximizes) -> tile returns to sub-stream
    restored_stream = tile.toggle_maximize()
    assert restored_stream == "sub"
    assert tile.is_maximized is False
    assert tile.active_stream == "sub"
