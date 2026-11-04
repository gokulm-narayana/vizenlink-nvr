"""System health and telemetry REST API endpoints (HLTH-02, HLTH-06)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from vizenlink_nvr.api.dependencies import CurrentUser, DbSession
from vizenlink_nvr.services.health import RecorderHealthService
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
