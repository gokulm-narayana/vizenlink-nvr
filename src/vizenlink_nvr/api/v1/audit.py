"""Audit trail query REST API endpoint (AUTH-07)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from vizenlink_nvr.api.dependencies import DbSession, RequireOwner
from vizenlink_nvr.services.audit import AuditService

audit_router = APIRouter(prefix="/audit-logs", tags=["audit"])


class AuditLogResponse(BaseModel):
    """Schema for individual audit log entry."""

    id: int
    timestamp: datetime
    actor_id: int | None
    actor_username: str | None
    ip_address: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any] | None = None


class AuditLogQueryResponse(BaseModel):
    """Paginated response for audit logs."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


@audit_router.get("", response_model=AuditLogQueryResponse)
async def query_audit_logs(
    user: RequireOwner,
    db: DbSession,
    action: str | None = None,
    actor: str | None = None,
    resource: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditLogQueryResponse:
    """Retrieve system audit logs with filtering and pagination (Owner only)."""
    records = await AuditService.query_events(
        session=db,
        action=action,
        actor=actor,
        resource=resource,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    total = await AuditService.count_events(
        session=db,
        action=action,
        actor=actor,
        resource=resource,
        start_time=start_time,
        end_time=end_time,
    )

    items: list[AuditLogResponse] = []
    for r in records:
        details_dict: dict[str, Any] | None = None
        if r.details_json:
            try:
                details_dict = json.loads(r.details_json)
            except Exception:
                details_dict = None

        items.append(
            AuditLogResponse(
                id=r.id,
                timestamp=r.timestamp,
                actor_id=r.actor_id,
                actor_username=r.actor_username,
                ip_address=r.ip_address,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                details=details_dict,
            )
        )

    return AuditLogQueryResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
