"""System health and telemetry REST API endpoints (HLTH-02, HLTH-06)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from vizenlink_nvr.api.dependencies import CurrentUser, DbSession
from vizenlink_nvr.services.alert_service import AlertService
from vizenlink_nvr.services.health import RecorderHealthService
from vizenlink_nvr.services.outage_tracker import OutageTracker
from vizenlink_nvr.services.registry import camera_counts

health_router = APIRouter(prefix="/health", tags=["health"])


class SystemHealthResponse(BaseModel):
    """Recorder health response schema."""

    status: str
    db_ok: bool
    mediamtx_ok: bool
    storage_ok: bool
    total_cameras: int = 0
    active_cameras: int = 0
    details: dict[str, Any] = {}


class AlertItemResponse(BaseModel):
    """Active in-app alert notification schema."""

    id: str
    severity: str
    title: str
    message: str
    timestamp: datetime
    source: str


class CameraOutageResponse(BaseModel):
    """Camera outage history item."""

    id: int
    camera_serial: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    reason: str | None = None


@health_router.get("", response_model=SystemHealthResponse)
async def get_system_health(
    user: CurrentUser,
    db: DbSession,
) -> SystemHealthResponse:
    """Retrieve overall system health and subsystem statuses."""
    status_rec = await RecorderHealthService.get_recorder_status(db)
    counts = await camera_counts(db)

    return SystemHealthResponse(
        status=status_rec.status.value if hasattr(status_rec.status, "value") else str(status_rec.status),
        db_ok=status_rec.db_ok,
        mediamtx_ok=status_rec.mediamtx_ok,
        storage_ok=status_rec.storage_ok,
        total_cameras=counts["total"],
        active_cameras=counts["active"],
        details=status_rec.details,
    )


@health_router.get("/alerts", response_model=list[AlertItemResponse])
async def get_active_alerts(
    user: CurrentUser,
    db: DbSession,
) -> list[AlertItemResponse]:
    """Retrieve active system health alerts."""
    alerts = await AlertService.evaluate_active_alerts(db)
    if user.role in ("owner", "operator"):
        return [
            AlertItemResponse(
                id=a.id,
                severity=a.severity,
                title=a.title,
                message=a.message,
                timestamp=a.timestamp,
                source=a.source,
            )
            for a in alerts
        ]

    allowed = {p.camera_serial for p in user.permissions}
    filtered: list[AlertItemResponse] = []
    for a in alerts:
        if a.source.startswith("camera:") or a.source.startswith("watchdog:"):
            serial = a.source.split(":", 1)[1]
            if serial not in allowed:
                continue
        filtered.append(
            AlertItemResponse(
                id=a.id,
                severity=a.severity,
                title=a.title,
                message=a.message,
                timestamp=a.timestamp,
                source=a.source,
            )
        )
    return filtered


@health_router.get("/outages", response_model=list[CameraOutageResponse])
async def get_camera_outages(
    user: CurrentUser,
    db: DbSession,
    camera_serial: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CameraOutageResponse]:
    """Retrieve historical camera outages."""
    if user.role not in ("owner", "operator"):
        allowed = {p.camera_serial for p in user.permissions}
        if camera_serial and camera_serial not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{camera_serial}'",
            )
        outages = await OutageTracker.get_outage_history(
            db, camera_serial=camera_serial, limit=limit, offset=offset
        )
        return [
            CameraOutageResponse(
                id=o.id,
                camera_serial=o.camera_serial,
                started_at=o.started_at,
                ended_at=o.ended_at,
                duration_seconds=o.duration_seconds,
                reason=o.reason,
            )
            for o in outages
            if o.camera_serial in allowed
        ]

    outages = await OutageTracker.get_outage_history(
        db, camera_serial=camera_serial, limit=limit, offset=offset
    )
    return [
        CameraOutageResponse(
            id=o.id,
            camera_serial=o.camera_serial,
            started_at=o.started_at,
            ended_at=o.ended_at,
            duration_seconds=o.duration_seconds,
            reason=o.reason,
        )
        for o in outages
    ]

