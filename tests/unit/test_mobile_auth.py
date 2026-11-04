"""Unit tests for MobileAuthService and paired devices (MOB-03)."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vizenlink_nvr.db.models import Base, User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.mobile_auth import MobileAuthService
from vizenlink_nvr.timeutil import utc_now


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh in-memory SQLite async database."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        engine = create_async_engine(f"sqlite+aiosqlite:///{f.name}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            yield session

        await engine.dispose()


@pytest_asyncio.fixture
async def sample_users(async_db: AsyncSession) -> tuple[User, User]:
    """Create an owner and a viewer user."""
    owner = User(
        username="owner_user",
        password_hash=hash_password("OwnerPassword123!"),
        role="owner",
        is_active=True,
        updated_at=utc_now(),
    )
    viewer = User(
        username="viewer_user",
        password_hash=hash_password("ViewerPassword123!"),
        role="viewer",
        is_active=True,
        updated_at=utc_now(),
    )
    async_db.add_all([owner, viewer])
    await async_db.commit()
    await async_db.refresh(owner)
    await async_db.refresh(viewer)
    return owner, viewer


@pytest.mark.asyncio
async def test_qr_pairing_flow(async_db: AsyncSession, sample_users: tuple[User, User]) -> None:
    """Test generating a QR pairing session and claiming it on a mobile device."""
    owner, _ = sample_users

    # 1. Create QR pairing session
    qr_sess, qr_payload = await MobileAuthService.create_qr_pairing_session(async_db, owner.id)
    assert len(qr_sess.pairing_code) == 32
    assert qr_sess.claimed is False
    assert f"code={qr_sess.pairing_code}" in qr_payload

    # 2. Claim via mobile device
    device, access_token, refresh_token = await MobileAuthService.pair_via_qr(
        db=async_db,
        pairing_code=qr_sess.pairing_code,
        device_id="iphone-15-pro-uuid",
        device_name="John's iPhone",
        platform="ios",
    )

    assert device.user_id == owner.id
    assert device.device_name == "John's iPhone"
    assert device.platform == "ios"
    assert device.is_revoked is False
    assert len(access_token) == 64
    assert len(refresh_token) == 64

    # 3. Double-claim should be rejected
    with pytest.raises(ValueError, match="already been claimed"):
        await MobileAuthService.pair_via_qr(
            db=async_db,
            pairing_code=qr_sess.pairing_code,
            device_id="another-device-uuid",
            device_name="Another Phone",
        )


@pytest.mark.asyncio
async def test_qr_pairing_expired(async_db: AsyncSession, sample_users: tuple[User, User]) -> None:
    """Expired QR pairing sessions are rejected."""
    owner, _ = sample_users

    # Expired TTL (-10 seconds)
    qr_sess, _ = await MobileAuthService.create_qr_pairing_session(
        async_db, owner.id, ttl=timedelta(seconds=-10)
    )

    with pytest.raises(ValueError, match="expired"):
        await MobileAuthService.pair_via_qr(
            db=async_db,
            pairing_code=qr_sess.pairing_code,
            device_id="dev-1",
            device_name="Dev 1",
        )


@pytest.mark.asyncio
async def test_credential_pairing_flow(async_db: AsyncSession, sample_users: tuple[User, User]) -> None:
    """Test direct username/password mobile pairing."""
    _, viewer = sample_users

    # Valid credentials
    dev, acc, ref = await MobileAuthService.pair_via_credentials(
        db=async_db,
        username="viewer_user",
        password="ViewerPassword123!",
        device_id="pixel-8-uuid",
        device_name="Viewer's Pixel",
        platform="android",
    )
    assert dev.user_id == viewer.id
    assert dev.platform == "android"

    # Validate token
    val_res = await MobileAuthService.validate_mobile_token(async_db, acc)
    assert val_res is not None
    v_dev, v_user = val_res
    assert v_dev.id == dev.id
    assert v_user.username == "viewer_user"

    # Invalid credentials
    with pytest.raises(ValueError, match="Invalid username or password"):
        await MobileAuthService.pair_via_credentials(
            db=async_db,
            username="viewer_user",
            password="WrongPassword!",
            device_id="pixel-8-uuid",
            device_name="Viewer's Pixel",
        )


@pytest.mark.asyncio
async def test_token_refresh_and_revocation(async_db: AsyncSession, sample_users: tuple[User, User]) -> None:
    """Test token refresh and immediate invalidation upon revocation."""
    owner, viewer = sample_users

    dev, acc, ref = await MobileAuthService.pair_via_credentials(
        db=async_db,
        username="viewer_user",
        password="ViewerPassword123!",
        device_id="dev-rev-uuid",
        device_name="Test Device",
    )

    # Refresh works
    new_acc, exp = await MobileAuthService.refresh_token(async_db, ref)
    assert new_acc != acc
    assert exp > utc_now()

    # Valid with new access token
    assert await MobileAuthService.validate_mobile_token(async_db, new_acc) is not None

    # Viewer cannot revoke other devices (mocked scenario if device was owner's)
    with pytest.raises(PermissionError, match="Forbidden"):
        # Create an owner device
        owner_dev, _, _ = await MobileAuthService.pair_via_credentials(
            db=async_db,
            username="owner_user",
            password="OwnerPassword123!",
            device_id="owner-phone",
            device_name="Owner Phone",
        )
        await MobileAuthService.revoke_device(async_db, owner_dev.id, actor=viewer)

    # Owner revokes viewer device
    revoked = await MobileAuthService.revoke_device(async_db, dev.id, actor=owner)
    assert revoked is True

    # Tokens immediately invalid
    assert await MobileAuthService.validate_mobile_token(async_db, new_acc) is None

    # Refresh also rejected
    with pytest.raises(ValueError, match="Device has been revoked"):
        await MobileAuthService.refresh_token(async_db, ref)


@pytest.mark.asyncio
async def test_list_devices(async_db: AsyncSession, sample_users: tuple[User, User]) -> None:
    """Test listing paired devices across users."""
    owner, viewer = sample_users

    await MobileAuthService.pair_via_credentials(
        async_db, "owner_user", "OwnerPassword123!", "owner-dev-1", "Owner Tablet"
    )
    await MobileAuthService.pair_via_credentials(
        async_db, "viewer_user", "ViewerPassword123!", "viewer-dev-1", "Viewer Phone"
    )

    # Owner lists all
    all_devs = await MobileAuthService.list_devices(async_db)
    assert len(all_devs) == 2

    # Scoped to viewer
    viewer_devs = await MobileAuthService.list_devices(async_db, user_id=viewer.id)
    assert len(viewer_devs) == 1
    assert viewer_devs[0].device_name == "Viewer Phone"
