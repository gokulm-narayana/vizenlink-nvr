"""First-run setup wizard service for VizenLink NVR."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import User
from vizenlink_nvr.services.auth_hasher import hash_password
from vizenlink_nvr.services.settings import SITE_TIMEZONE_KEY, put_setting
from vizenlink_nvr.services.storage import set_storage_path
from vizenlink_nvr.timeutil import utc_now, validate_zone

MIN_PASSWORD_LENGTH = 8


class SetupService:
    """Service handling NVR first-run initialization status and owner account creation."""

    @staticmethod
    async def is_initialized(db: AsyncSession) -> bool:
        """Check whether the NVR has already completed first-run setup (any user exists)."""
        stmt = select(func.count(User.id))
        count = (await db.execute(stmt)).scalar_one()
        return bool(count and count > 0)

    @staticmethod
    async def initialize_nvr(
        db: AsyncSession,
        owner_username: str,
        owner_password: str,
        timezone: str,
        storage_path: Path,
        allow_system_disk: bool = False,
    ) -> User:
        """Complete first-run setup: create owner account, configure timezone, and set storage path.
        
        Raises:
            RuntimeError: if NVR is already initialized.
            ValueError: if credentials, timezone, or storage configuration are invalid.
        """
        if await SetupService.is_initialized(db):
            raise RuntimeError("NVR is already initialized; setup cannot be rerun")

        username = owner_username.strip()
        if not username:
            raise ValueError("Owner username cannot be empty")

        if len(owner_password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Owner password must be at least {MIN_PASSWORD_LENGTH} characters long")

        # Validate timezone name
        try:
            validate_zone(timezone)
        except Exception as exc:
            raise ValueError(f"Invalid timezone '{timezone}': {exc}") from exc

        # Persist site timezone setting
        now = utc_now()
        await put_setting(db, SITE_TIMEZONE_KEY, timezone, now)

        # Set storage path with safeguards
        await set_storage_path(
            session=db,
            target_path=storage_path,
            allow_system_disk=allow_system_disk,
        )

        # Create Owner user
        hashed_pw = hash_password(owner_password)
        owner_user = User(
            username=username,
            password_hash=hashed_pw,
            role="owner",
            is_active=True,
            cognito_sub=None,
            created_at=now,
            updated_at=now,
        )
        db.add(owner_user)
        await db.commit()
        await db.refresh(owner_user)

        return owner_user
