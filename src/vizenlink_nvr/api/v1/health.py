"""System health and telemetry REST API endpoints (HLTH-02, HLTH-06)."""

from __future__ import annotations

import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from vizenlink_nvr import __version__

from vizenlink_nvr.api.dependencies import CurrentUser, DbSession
from vizenlink_nvr.services.alert_service import AlertService
from vizenlink_nvr.services.health import RecorderHealthService
from vizenlink_nvr.services.outage_tracker import OutageTracker
from vizenlink_nvr.services.registry import camera_counts
from vizenlink_nvr.services.storage import get_storage_config

health_router = APIRouter(prefix="/health", tags=["health"])


def _default_storage_path(request: Request) -> Path:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and getattr(runtime, "settings", None) is not None:
        return Path(runtime.settings.data_dir) / "recordings"
    return Path("/var/lib/vizenlink-nvr/recordings")


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


class SystemMetricsResponse(BaseModel):
    """Host resource metrics for the dashboard System zone."""

    cpu_percent: float
    cpu_count: int
    memory_total_bytes: int
    memory_used_bytes: int
    memory_percent: float
    nvr_uptime_seconds: float
    host_uptime_seconds: float
    load_average: list[float] | None = None
    platform: str
    version: str


@health_router.get("/system", response_model=SystemMetricsResponse)
async def get_system_metrics(user: CurrentUser) -> SystemMetricsResponse:
    """CPU, memory and uptime of the recorder host (old VMS dashboard parity)."""
    now = time.time()
    mem = psutil.virtual_memory()
    try:
        load = [round(v, 2) for v in os.getloadavg()]
    except (AttributeError, OSError):
        load = None
    return SystemMetricsResponse(
        # interval=None is non-blocking: usage since the previous call.
        cpu_percent=psutil.cpu_percent(interval=None),
        cpu_count=psutil.cpu_count() or 1,
        memory_total_bytes=mem.total,
        memory_used_bytes=mem.total - mem.available,
        memory_percent=mem.percent,
        nvr_uptime_seconds=max(0.0, now - psutil.Process().create_time()),
        host_uptime_seconds=max(0.0, now - psutil.boot_time()),
        load_average=load,
        platform=f"{platform.system()} {platform.machine()}",
        version=__version__,
    )


@health_router.get("", response_model=SystemHealthResponse)
async def get_system_health(
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> SystemHealthResponse:
    """Retrieve overall system health and subsystem statuses."""
    storage_cfg = await get_storage_config(db, default_path=_default_storage_path(request))
    status_rec = await RecorderHealthService.get_recorder_status(
        db, storage_status=storage_cfg.health_state
    )
    counts = await camera_counts(db)

    return SystemHealthResponse(
        status=status_rec.status.value if hasattr(status_rec.status, "value") else str(status_rec.status),
        db_ok=status_rec.db_ok,
        mediamtx_ok=status_rec.mediamtx_ok,
        storage_ok=status_rec.storage_ok,
        total_cameras=counts["total"],
        active_cameras=counts["active"],
        details={
            **status_rec.details,
            "storage_state": str(storage_cfg.health_state.value),
            "storage_reason": storage_cfg.health_reason,
        },
    )


@health_router.get("/alerts", response_model=list[AlertItemResponse])
async def get_active_alerts(
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> list[AlertItemResponse]:
    """Retrieve active system health alerts."""
    alerts = await AlertService.evaluate_active_alerts(
        db, default_storage_path=_default_storage_path(request)
    )
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

