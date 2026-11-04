"""Mobile device pairing, token management, and revocation service (MOB-03)."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vizenlink_nvr.db.models import PairedDevice, QRPairingSession, User
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.auth_hasher import verify_password
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
QR_PAIRING_TTL = timedelta(minutes=5)
SLIDING_WINDOW_UPDATE = timedelta(minutes=5)


class MobileAuthService:
    """Manages mobile device enrollment, QR pairing codes, token rotation, and revocation."""

    @staticmethod
    async def create_qr_pairing_session(
        db: AsyncSession,
        user_id: int,
        ttl: timedelta = QR_PAIRING_TTL,
    ) -> tuple[QRPairingSession, str]:
        """Create an ephemeral QR pairing session and return (session, qr_payload)."""
        now = utc_now()
        pairing_code = secrets.token_hex(16)
        expires_at = now + ttl

        qr_session = QRPairingSession(
            pairing_code=pairing_code,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            claimed=False,
        )
        db.add(qr_session)
        await db.commit()
        await db.refresh(qr_session)

        # URI payload encoded in QR for mobile app scanner
        qr_payload = f"vizenlink://pair?code={pairing_code}&expires={int(expires_at.timestamp())}"
        return qr_session, qr_payload

    @staticmethod
    async def pair_via_qr(
        db: AsyncSession,
        pairing_code: str,
        device_id: str,
        device_name: str,
        platform: str = "unknown",
    ) -> tuple[PairedDevice, str, str]:
        """Redeem a QR pairing code and issue initial access and refresh tokens."""
        now = utc_now()
        stmt = (
            select(QRPairingSession)
            .where(QRPairingSession.pairing_code == pairing_code)
            .options(selectinload(QRPairingSession.user))
        )
        qr_session = (await db.execute(stmt)).scalar_one_or_none()

        if qr_session is None:
            raise ValueError("Invalid pairing code")
        if qr_session.claimed:
            raise ValueError("Pairing code has already been claimed")
        if now > qr_session.expires_at:
            raise ValueError("Pairing code has expired")

        user = qr_session.user
        if user is None or not user.is_active:
            raise ValueError("Account is inactive or disabled")

        qr_session.claimed = True
        qr_session.claimed_at = now

        device, access_token, refresh_token = await MobileAuthService._enroll_or_update_device(
            db=db,
            user=user,
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            action="mobile.pair_qr",
        )
        return device, access_token, refresh_token

    @staticmethod
    async def pair_via_credentials(
        db: AsyncSession,
        username: str,
        password: str,
        device_id: str,
        device_name: str,
        platform: str = "unknown",
    ) -> tuple[PairedDevice, str, str]:
        """Pair mobile device using direct user credentials."""
        stmt = (
            select(User)
            .where(User.username == username)
            .options(selectinload(User.permissions))
        )
        user = (await db.execute(stmt)).scalar_one_or_none()

        if user is None or not user.is_active or not verify_password(user.password_hash, password):
            await AuditService.record_event(
                session=db,
                action="mobile.pair_failed",
                resource_type="auth",
                resource_id=device_id,
                actor_username=username,
                details={"reason": "invalid_credentials", "device_name": device_name},
                commit=True,
            )
            raise ValueError("Invalid username or password")

        device, access_token, refresh_token = await MobileAuthService._enroll_or_update_device(
            db=db,
            user=user,
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            action="mobile.pair_credentials",
        )
        return device, access_token, refresh_token

    @staticmethod
    async def _enroll_or_update_device(
        db: AsyncSession,
        user: User,
        device_id: str,
        device_name: str,
        platform: str,
        action: str,
    ) -> tuple[PairedDevice, str, str]:
        """Internal helper to create or re-enroll a paired device record."""
        now = utc_now()
        access_token = secrets.token_hex(32)
        refresh_token = secrets.token_hex(32)
        access_exp = now + ACCESS_TOKEN_TTL
        refresh_exp = now + REFRESH_TOKEN_TTL

        # Look up existing device enrollment for same user and device_id
        stmt = (
            select(PairedDevice)
            .where(
                PairedDevice.user_id == user.id,
                PairedDevice.device_id == device_id,
            )
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            existing.device_name = device_name
            existing.platform = platform
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.access_token_expires_at = access_exp
            existing.refresh_token_expires_at = refresh_exp
            existing.last_seen_at = now
            existing.is_revoked = False
            existing.revoked_at = None
            device = existing
        else:
            pk = uuid.uuid4().hex
            device = PairedDevice(
                id=pk,
                device_id=device_id,
                device_name=device_name,
                platform=platform,
                user_id=user.id,
                access_token=access_token,
                refresh_token=refresh_token,
                paired_at=now,
                last_seen_at=now,
                access_token_expires_at=access_exp,
                refresh_token_expires_at=refresh_exp,
                is_revoked=False,
                revoked_at=None,
            )
            db.add(device)

        await db.commit()
        await db.refresh(device)

        await AuditService.record_event(
            session=db,
            action=action,
            resource_type="paired_device",
            resource_id=device.id,
            actor_id=user.id,
            actor_username=user.username,
            details={"device_id": device_id, "device_name": device_name, "platform": platform},
            commit=True,
        )

        return device, access_token, refresh_token

    @staticmethod
    async def refresh_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> tuple[str, datetime]:
        """Rotate access token given a valid, unrevoked refresh token."""
        if not refresh_token:
            raise ValueError("Refresh token is required")

        now = utc_now()
        stmt = (
            select(PairedDevice)
            .where(PairedDevice.refresh_token == refresh_token)
            .options(selectinload(PairedDevice.user))
        )
        device = (await db.execute(stmt)).scalar_one_or_none()

        if device is None:
            raise ValueError("Invalid refresh token")
        if device.is_revoked:
            raise ValueError("Device has been revoked")
        if now > device.refresh_token_expires_at:
            raise ValueError("Refresh token has expired")

        user = device.user
        if user is None or not user.is_active:
            raise ValueError("Account is inactive")

        new_access_token = secrets.token_hex(32)
        new_access_exp = now + ACCESS_TOKEN_TTL

        device.access_token = new_access_token
        device.access_token_expires_at = new_access_exp
        device.last_seen_at = now

        await db.commit()
        await db.refresh(device)

        return new_access_token, new_access_exp

    @staticmethod
    async def validate_mobile_token(
        db: AsyncSession,
        token: str,
    ) -> tuple[PairedDevice, User] | None:
        """Validate an active mobile access token. Returns (device, user) or None."""
        if not token:
            return None

        now = utc_now()
        stmt = (
            select(PairedDevice)
            .where(PairedDevice.access_token == token)
            .options(
                selectinload(PairedDevice.user).selectinload(User.permissions),
            )
        )
        device = (await db.execute(stmt)).scalar_one_or_none()

        if device is None or device.is_revoked:
            return None
        if now > device.access_token_expires_at:
            return None

        user = device.user
        if user is None or not user.is_active:
            return None

        # Sliding window update of last_seen_at
        if now - device.last_seen_at > SLIDING_WINDOW_UPDATE:
            device.last_seen_at = now
            await db.commit()

        return device, user

    @staticmethod
    async def revoke_device(
        db: AsyncSession,
        device_id_or_pk: str,
        actor: User,
    ) -> bool:
        """Revoke a paired device, immediately preventing subsequent access."""
        stmt = (
            select(PairedDevice)
            .where(
                (PairedDevice.id == device_id_or_pk) | (PairedDevice.device_id == device_id_or_pk)
            )
        )
        device = (await db.execute(stmt)).scalar_one_or_none()

        if device is None:
            return False

        if actor.role != "owner" and device.user_id != actor.id:
            raise PermissionError("Forbidden: only Owners can revoke devices of other users")

        device.is_revoked = True
        device.revoked_at = utc_now()
        await db.commit()

        await AuditService.record_event(
            session=db,
            action="mobile.device_revoked",
            resource_type="paired_device",
            resource_id=device.id,
            actor_id=actor.id,
            actor_username=actor.username,
            details={"device_name": device.device_name, "device_id": device.device_id},
            commit=True,
        )

        return True

    @staticmethod
    async def list_devices(
        db: AsyncSession,
        user_id: int | None = None,
    ) -> list[PairedDevice]:
        """List paired mobile devices, optionally scoped to a user."""
        stmt = (
            select(PairedDevice)
            .options(selectinload(PairedDevice.user))
            .order_by(PairedDevice.paired_at.desc())
        )
        if user_id is not None:
            stmt = stmt.where(PairedDevice.user_id == user_id)

        res = await db.execute(stmt)
        return list(res.scalars().all())
