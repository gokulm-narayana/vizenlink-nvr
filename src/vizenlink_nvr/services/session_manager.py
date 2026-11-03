"""Session lifecycle and cookie management service."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vizenlink_nvr.db.models import Session, User
from vizenlink_nvr.timeutil import utc_now

SESSION_COOKIE_NAME = "session_id"
DEFAULT_SESSION_TTL = timedelta(days=7)
SLIDING_WINDOW_UPDATE_INTERVAL = timedelta(minutes=5)


class SessionManager:
    """Manages creation, verification, sliding activity renewal, and invalidation of user sessions."""

    @staticmethod
    async def create_session(
        db: AsyncSession,
        user_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
        ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> Session:
        """Create a new session with a 256-bit cryptographic token."""
        token = secrets.token_hex(32)
        now = utc_now()
        expires_at = now + ttl

        sess = Session(
            id=token,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            last_active_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
        return sess

    @staticmethod
    async def validate_session(
        db: AsyncSession,
        token: str,
    ) -> tuple[Session, User] | None:
        """Validate a session token. Returns (Session, User) or None if invalid/expired."""
        if not token:
            return None

        stmt = (
            select(Session)
            .where(Session.id == token)
            .options(
                selectinload(Session.user).selectinload(User.permissions),
            )
        )
        sess = (await db.execute(stmt)).scalar_one_or_none()
        if sess is None:
            return None

        now = utc_now()
        if now > sess.expires_at:
            # Expired session
            await db.execute(delete(Session).where(Session.id == token))
            await db.commit()
            return None

        user = sess.user
        if user is None or not user.is_active:
            return None

        # Sliding activity update
        if now - sess.last_active_at > SLIDING_WINDOW_UPDATE_INTERVAL:
            sess.last_active_at = now
            await db.commit()

        return sess, user

    @staticmethod
    async def invalidate_session(
        db: AsyncSession,
        token: str,
    ) -> bool:
        """Invalidate a single session by token."""
        if not token:
            return False
        res = await db.execute(delete(Session).where(Session.id == token))
        await db.commit()
        rowcount = getattr(res, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    @staticmethod
    async def invalidate_user_sessions(
        db: AsyncSession,
        user_id: int,
    ) -> int:
        """Invalidate all active sessions for a user."""
        res = await db.execute(delete(Session).where(Session.user_id == user_id))
        await db.commit()
        rowcount = getattr(res, "rowcount", 0)
        return int(rowcount or 0)

    @staticmethod
    def set_cookie(
        response: Response,
        token: str,
        max_age: int = 7 * 86400,
        secure: bool = False,
    ) -> None:
        """Set HTTP-only SameSite=Lax session cookie on the response."""
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=secure,
            path="/",
        )

    @staticmethod
    def clear_cookie(response: Response) -> None:
        """Clear session cookie on the response."""
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            httponly=True,
            samesite="lax",
        )
