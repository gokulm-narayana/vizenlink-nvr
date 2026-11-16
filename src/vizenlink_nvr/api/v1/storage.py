"""Storage configuration and disk telemetry REST API endpoints."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
    RequireOwner,
)
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.indexer import scan_and_reconcile
from vizenlink_nvr.services.storage import (
    DEFAULT_RESERVE_BYTES,
    StorageHealthState,
    evaluate_storage_health,
    get_storage_config,
    set_storage_path,
)
from vizenlink_nvr.timeutil import utc_now

storage_router = APIRouter(prefix="/storage", tags=["storage"])


class StorageTelemetryResponse(BaseModel):
    """Disk space metrics."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    reserve_bytes: int


class StorageStatusResponse(BaseModel):
    """Storage volume status and health configuration."""

    storage_path: str
    allow_system_disk: bool
    reserve_bytes: int
    health_state: str
    health_reason: str | None = None
    telemetry: StorageTelemetryResponse | None = None
    estimated_retention_days: float | None = None


class StoragePathUpdateRequest(BaseModel):
    """Input payload to update the active storage path."""

    storage_path: str = Field(..., min_length=1)
    allow_system_disk: bool = False
    reserve_bytes: int = DEFAULT_RESERVE_BYTES


def _get_default_storage_path(request: Request) -> Path:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and getattr(runtime, "settings", None) is not None:
        return Path(runtime.settings.data_dir) / "recordings"
    return Path("/var/lib/vizenlink-nvr/recordings")


@storage_router.get("/status", response_model=StorageStatusResponse)
async def get_storage_status_endpoint(
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> StorageStatusResponse:
    """Retrieve recording storage configuration and live disk space metrics."""
    default_path = _get_default_storage_path(request)
    cfg = await get_storage_config(db, default_path=default_path)
    telemetry_view = None
    if cfg.telemetry is not None:
        telemetry_view = StorageTelemetryResponse(
            total_bytes=cfg.telemetry.total_bytes,
            used_bytes=cfg.telemetry.used_bytes,
            free_bytes=cfg.telemetry.free_bytes,
            reserve_bytes=cfg.telemetry.reserve_bytes,
        )

    return StorageStatusResponse(
        storage_path=str(cfg.storage_path),
        allow_system_disk=cfg.allow_system_disk,
        reserve_bytes=cfg.reserve_bytes,
        health_state=cfg.health_state.value if hasattr(cfg.health_state, "value") else str(cfg.health_state),
        health_reason=cfg.health_reason,
        telemetry=telemetry_view,
        estimated_retention_days=cfg.estimated_retention_days,
    )


@storage_router.post("/set-path", response_model=StorageStatusResponse)
async def set_storage_path_endpoint(
    payload: StoragePathUpdateRequest,
    user: RequireOwner,
    db: DbSession,
) -> StorageStatusResponse:
    """Update active recording storage volume (Owner only)."""
    target = Path(payload.storage_path)
    if not target.is_absolute():
        raise HTTPException(
            status_code=422,
            detail="Storage path must be an absolute path.",
        )

    # Validate before saving: a refused request must leave the working storage
    # settings untouched, otherwise recording stops on a path the API rejected.
    health_state, health_reason = evaluate_storage_health(
        target,
        allow_system_disk=payload.allow_system_disk,
        reserve_bytes=payload.reserve_bytes,
    )
    if health_state == StorageHealthState.SYSTEM_DISK_REFUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=health_reason or "Recording to system root disk is refused without allow_system_disk",
        )
    if health_state in (StorageHealthState.UNMOUNTED, StorageHealthState.READ_ONLY):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=health_reason or "Storage path is not usable.",
        )

    cfg = await set_storage_path(
        session=db,
        target_path=target,
        allow_system_disk=payload.allow_system_disk,
        reserve_bytes=payload.reserve_bytes,
    )

    await AuditService.record_event(
        session=db,
        action="storage.update_path",
        resource_type="storage",
        resource_id=str(cfg.storage_path),
        actor_id=user.id,
        actor_username=user.username,
        details={"allow_system_disk": payload.allow_system_disk, "reserve_bytes": payload.reserve_bytes},
        commit=True,
    )

    telemetry_view = None
    if cfg.telemetry is not None:
        telemetry_view = StorageTelemetryResponse(
            total_bytes=cfg.telemetry.total_bytes,
            used_bytes=cfg.telemetry.used_bytes,
            free_bytes=cfg.telemetry.free_bytes,
            reserve_bytes=cfg.telemetry.reserve_bytes,
        )

    return StorageStatusResponse(
        storage_path=str(cfg.storage_path),
        allow_system_disk=cfg.allow_system_disk,
        reserve_bytes=cfg.reserve_bytes,
        health_state=cfg.health_state.value if hasattr(cfg.health_state, "value") else str(cfg.health_state),
        health_reason=cfg.health_reason,
        telemetry=telemetry_view,
        estimated_retention_days=cfg.estimated_retention_days,
    )


@storage_router.post("/scan")
async def trigger_storage_scan_endpoint(
    request: Request,
    user: RequireOperator,
    db: DbSession,
) -> dict[str, Any]:
    """Reconcile the configured recording directory and return actual scan counts."""
    config = await get_storage_config(db, default_path=_get_default_storage_path(request))
    if not config.storage_path.is_dir():
        raise HTTPException(409, "Recording folder is unavailable.")
    report = await scan_and_reconcile(db, config.storage_path)
    return {
        "status": "completed",
        **asdict(report),
        "timestamp": utc_now().isoformat(),
    }
