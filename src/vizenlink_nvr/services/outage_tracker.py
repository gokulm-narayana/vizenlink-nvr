"""Camera outage lifecycle and history tracker (HLTH-07)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import CameraOutage
from vizenlink_nvr.timeutil import utc_now


class OutageTracker:
    """Tracks camera disconnections, re-connections, and computes outage durations."""

    @staticmethod
    async def record_offline(
        session: AsyncSession,
        camera_serial: str,
        reason: str | None = None,
        at: datetime | None = None,
        commit: bool = True,
    ) -> CameraOutage:
        """Record a camera disconnect event. Reuses any existing unclosed outage."""
        now = at or utc_now()

        stmt = (
            select(CameraOutage)
            .where(
                CameraOutage.camera_serial == camera_serial,
                CameraOutage.ended_at.is_(None),
            )
            .order_by(CameraOutage.started_at.desc())
        )
        existing = (await session.execute(stmt)).scalars().first()
        if existing is not None:
            if reason:
                existing.reason = reason
            if commit:
                await session.commit()
            return existing

        outage = CameraOutage(
            camera_serial=camera_serial,
            started_at=now,
            ended_at=None,
            duration_seconds=None,
            reason=reason,
        )
        session.add(outage)
        if commit:
            await session.commit()
            await session.refresh(outage)
        return outage

    @staticmethod
    async def record_online(
        session: AsyncSession,
        camera_serial: str,
        at: datetime | None = None,
        commit: bool = True,
    ) -> CameraOutage | None:
        """Close open outage for camera_serial, calculating total duration in seconds."""
        now = at or utc_now()

        stmt = (
            select(CameraOutage)
            .where(
                CameraOutage.camera_serial == camera_serial,
                CameraOutage.ended_at.is_(None),
            )
            .order_by(CameraOutage.started_at.desc())
        )
        open_outage = (await session.execute(stmt)).scalars().first()
        if open_outage is None:
            return None

        open_outage.ended_at = now
        duration = (now - open_outage.started_at).total_seconds()
        open_outage.duration_seconds = max(0.0, duration)
        if commit:
            await session.commit()
            await session.refresh(open_outage)
        return open_outage

    @staticmethod
    async def get_outage_history(
        session: AsyncSession,
        camera_serial: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CameraOutage]:
        """Fetch historical camera outages, newest first."""
        stmt = select(CameraOutage)
        if camera_serial:
            stmt = stmt.where(CameraOutage.camera_serial == camera_serial)
        stmt = stmt.order_by(CameraOutage.started_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())
