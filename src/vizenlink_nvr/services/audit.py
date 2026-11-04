"""Persistent append-only audit logging service (AUTH-07)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import AuditLog
from vizenlink_nvr.timeutil import utc_now


class AuditService:
    """Records and queries persistent audit trail events."""

    @staticmethod
    async def record_event(
        session: AsyncSession,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> AuditLog:
        """Record an append-only audit event in the database."""
        details_str = json.dumps(details, separators=(",", ":")) if details is not None else None
        event = AuditLog(
            timestamp=utc_now(),
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=details_str,
        )
        session.add(event)
        if commit:
            await session.commit()
            await session.refresh(event)
        return event

    @staticmethod
    async def query_events(
        session: AsyncSession,
        action: str | None = None,
        actor: str | None = None,
        resource: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Query audit log entries with optional filters and descending time ordering."""
        stmt = select(AuditLog)

        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor:
            stmt = stmt.where(AuditLog.actor_username == actor)
        if resource:
            stmt = stmt.where(AuditLog.resource_id == resource)
        if start_time:
            stmt = stmt.where(AuditLog.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(AuditLog.timestamp <= end_time)

        stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_events(
        session: AsyncSession,
        action: str | None = None,
        actor: str | None = None,
        resource: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Count matching audit log entries."""
        stmt = select(func.count(AuditLog.id))

        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor:
            stmt = stmt.where(AuditLog.actor_username == actor)
        if resource:
            stmt = stmt.where(AuditLog.resource_id == resource)
        if start_time:
            stmt = stmt.where(AuditLog.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(AuditLog.timestamp <= end_time)

        res = await session.execute(stmt)
        return int(res.scalar() or 0)

