"""Integration tests verifying full media token issue and MediaMTX HTTP auth handshake."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, User, UserCameraPermission
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.session_manager import SessionManager
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def app_and_users(tmp_path: Path):
    db_path = tmp_path / "test_handshake.db"
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
        viewer.permissions.append(
            UserCameraPermission(camera_serial="CAM-LOBBY", created_at=utc_now())
        )

        session.add_all([owner, viewer])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(viewer)

        # Create active sessions
        s_owner = await SessionManager.create_session(session, owner.id, "127.0.0.1", "test")
        s_viewer = await SessionManager.create_session(session, viewer.id, "127.0.0.1", "test")

        owner_token = s_owner.id
        viewer_token = s_viewer.id

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, owner_token, viewer_token

    await engine.dispose()


@pytest.mark.asyncio
async def test_full_media_token_issuance_and_auth_handshake(app_and_users) -> None:
    """Verify flow: client requests media token, receives signed token, and MediaMTX webhook validates it."""
    client, owner_token, viewer_token = app_and_users

    # 1. Anonymous request for media token fails with 401
    res_anon = await client.post("/api/v1/cameras/CAM-LOBBY/media-token")
    assert res_anon.status_code == 401

    # 2. Viewer requests token for whitelisted camera CAM-LOBBY
    client.cookies.set("session_id", viewer_token)
    res_token = await client.post("/api/v1/cameras/CAM-LOBBY/media-token?stream=sub")
    assert res_token.status_code == 200
    data = res_token.json()
    assert "token" in data
    assert data["expires_in"] == 900
    assert data["stream"] == "sub"
    assert data["path"] == "cam/CAM-LOBBY/sub"

    media_token = data["token"]

    # 3. Viewer requests token for restricted camera CAM-VAULT -> 403
    res_restricted = await client.post("/api/v1/cameras/CAM-VAULT/media-token?stream=sub")
    assert res_restricted.status_code == 403

    # 4. MediaMTX receives viewer stream request and validates against webhook
    res_webhook = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.42",
            "path": "cam/CAM-LOBBY/sub",
            "protocol": "webrtc",
            "action": "read",
            "query": f"token={media_token}",
        },
    )
    assert res_webhook.status_code == 200
    assert res_webhook.json() == {"status": "ok"}

    # 5. Owner requests token for CAM-VAULT (allowed for owner)
    client.cookies.set("session_id", owner_token)
    res_owner_token = await client.post("/api/v1/cameras/CAM-VAULT/media-token?stream=main")
    assert res_owner_token.status_code == 200
    owner_media_token = res_owner_token.json()["token"]

    res_owner_webhook = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.42",
            "path": "cam/CAM-VAULT/main",
            "protocol": "webrtc",
            "action": "read",
            "query": f"token={owner_media_token}",
        },
    )
    assert res_owner_webhook.status_code == 200
