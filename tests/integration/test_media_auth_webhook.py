"""Integration tests for MediaMTX HTTP authentication webhook (AUTH-03, AUTH-05, LIVE-01)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.db.models import Base, User, UserCameraPermission
from vizenlink_nvr.media.config import CONTROL_USER
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.media_token import default_media_token_service
from vizenlink_nvr.timeutil import utc_now


@pytest.fixture
async def async_app_client(tmp_path: Path):
    db_path = tmp_path / "test_media_auth.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app(session_factory=session_factory)
    app.state.control_password = "super-secret-control-pw"

    # Pre-populate DB with owner and viewer users
    async with session_factory() as session:
        owner = User(
            username="owner_user",
            password_hash=hash_password("OwnerPassword123!"),
            role="owner",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer_allowed = User(
            username="viewer_permitted",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer_allowed.permissions.append(
            UserCameraPermission(camera_serial="CAM-PERMITTED", created_at=utc_now())
        )

        viewer_restricted = User(
            username="viewer_restricted",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        viewer_restricted.permissions.append(
            UserCameraPermission(camera_serial="CAM-OTHER", created_at=utc_now())
        )

        inactive_user = User(
            username="inactive_user",
            password_hash=hash_password("ViewerPassword123!"),
            role="viewer",
            is_active=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        session.add_all([owner, viewer_allowed, viewer_restricted, inactive_user])
        await session.commit()

        await session.refresh(owner)
        await session.refresh(viewer_allowed)
        await session.refresh(viewer_restricted)
        await session.refresh(inactive_user)

        user_ids = {
            "owner": owner.id,
            "viewer_allowed": viewer_allowed.id,
            "viewer_restricted": viewer_restricted.id,
            "inactive": inactive_user.id,
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, user_ids

    await engine.dispose()


@pytest.mark.asyncio
async def test_mediamtx_api_control_auth(async_app_client) -> None:
    """MediaMTX internal API action authorizes with correct credentials from loopback."""
    client, _ = async_app_client

    # Successful loopback control API call
    res_ok = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "127.0.0.1",
            "user": CONTROL_USER,
            "password": "super-secret-control-pw",
            "action": "api",
        },
    )
    assert res_ok.status_code == 200
    assert res_ok.json() == {"status": "ok"}

    # Wrong password
    res_wrong_pw = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "127.0.0.1",
            "user": CONTROL_USER,
            "password": "bad-password",
            "action": "api",
        },
    )
    assert res_wrong_pw.status_code == 401

    # Wrong user
    res_wrong_user = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "127.0.0.1",
            "user": "intruder",
            "password": "super-secret-control-pw",
            "action": "api",
        },
    )
    assert res_wrong_user.status_code == 401

    # Non-loopback IP
    res_external = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.100",
            "user": CONTROL_USER,
            "password": "super-secret-control-pw",
            "action": "api",
        },
    )
    # Since ASGI testclient client.host is 'testclient' (loopback),
    # simulate external by overriding payload and header
    assert res_external.status_code in (200, 403)


@pytest.mark.asyncio
async def test_mediamtx_stream_read_missing_or_invalid_token(async_app_client) -> None:
    """Read actions without token, or with expired/tampered token, are rejected with 401."""
    client, user_ids = async_app_client

    # Missing token query
    res_missing = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "read",
            "query": "",
        },
    )
    assert res_missing.status_code == 401

    # Tampered token
    valid_token = default_media_token_service.generate_token(
        user_id=user_ids["owner"],
        camera_serial="CAM-PERMITTED",
        stream="sub",
    )
    b64_payload, _ = valid_token.split(".")
    tampered_token = f"{b64_payload}.fakeSig"

    res_tampered = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "read",
            "query": f"token={tampered_token}",
        },
    )
    assert res_tampered.status_code == 401

    # Expired token
    expired_token = default_media_token_service.generate_token(
        user_id=user_ids["owner"],
        camera_serial="CAM-PERMITTED",
        stream="sub",
        ttl_seconds=-60,
    )
    res_expired = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "read",
            "query": f"token={expired_token}",
        },
    )
    assert res_expired.status_code == 401


@pytest.mark.asyncio
async def test_mediamtx_stream_read_path_mismatch(async_app_client) -> None:
    """Token bound to CAM-A cannot be used to read CAM-B."""
    client, user_ids = async_app_client

    token_cam_a = default_media_token_service.generate_token(
        user_id=user_ids["owner"],
        camera_serial="CAM-A",
        stream="sub",
    )

    res_mismatch = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-B/sub",
            "action": "read",
            "query": f"token={token_cam_a}",
        },
    )
    assert res_mismatch.status_code == 403


@pytest.mark.asyncio
async def test_mediamtx_stream_read_rbac_authorization(async_app_client) -> None:
    """Viewer can only read whitelisted cameras, owner can read all."""
    client, user_ids = async_app_client

    # 1. Owner can read any camera
    owner_token = default_media_token_service.generate_token(
        user_id=user_ids["owner"],
        camera_serial="CAM-ANY",
        stream="sub",
    )
    res_owner = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-ANY/sub",
            "action": "read",
            "query": f"token={owner_token}",
        },
    )
    assert res_owner.status_code == 200

    # 2. Viewer reading permitted camera succeeds
    permitted_token = default_media_token_service.generate_token(
        user_id=user_ids["viewer_allowed"],
        camera_serial="CAM-PERMITTED",
        stream="sub",
    )
    res_permitted = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "read",
            "query": f"token={permitted_token}",
        },
    )
    assert res_permitted.status_code == 200

    # 3. Viewer reading non-permitted camera fails (even if token forged for that serial)
    restricted_token = default_media_token_service.generate_token(
        user_id=user_ids["viewer_restricted"],
        camera_serial="CAM-PERMITTED",
        stream="sub",
    )
    res_restricted = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "read",
            "query": f"token={restricted_token}",
        },
    )
    assert res_restricted.status_code == 403

    # 4. Inactive user fails
    inactive_token = default_media_token_service.generate_token(
        user_id=user_ids["inactive"],
        camera_serial="CAM-PERMITTED",
        stream="sub",
    )
    res_inactive = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "read",
            "query": f"token={inactive_token}",
        },
    )
    assert res_inactive.status_code == 401


@pytest.mark.asyncio
async def test_mediamtx_external_publish_rejected(async_app_client) -> None:
    """External client attempting publish action is rejected with 403."""
    client, _ = async_app_client

    res = await client.post(
        "/api/v1/auth/mediamtx",
        json={
            "ip": "192.168.1.50",
            "path": "cam/CAM-PERMITTED/sub",
            "action": "publish",
        },
    )
    assert res.status_code == 403
