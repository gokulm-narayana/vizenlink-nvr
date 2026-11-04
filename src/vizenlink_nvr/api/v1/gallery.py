"""Gallery REST API endpoints (GAL-01, GAL-02, LIVE-07, AUTH-05)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.api.dependencies import (
    CurrentUser,
    DbSession,
    RequireOperator,
)
from vizenlink_nvr.db.models import StorageSettings
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.gallery import GalleryService

logger = logging.getLogger(__name__)

gallery_router = APIRouter(prefix="/gallery", tags=["gallery"])


class GalleryItemResponse(BaseModel):
    id: int
    camera_serial: str
    item_type: str
    title: str
    file_path: str
    file_size_bytes: int
    duration_seconds: float | None = None
    captured_at: datetime
    created_at: datetime
    user_id: int | None = None


class GalleryListResponse(BaseModel):
    items: list[GalleryItemResponse]
    total: int
    limit: int
    offset: int


class GalleryDeleteResponse(BaseModel):
    status: str
    id: int


async def _resolve_storage_root(request: Request, db: AsyncSession) -> Path:
    """Resolve configured storage root path."""
    stmt = select(StorageSettings.storage_path).where(StorageSettings.id == 1)
    res = await db.execute(stmt)
    path_str = res.scalar_one_or_none()
    if path_str:
        return Path(path_str)
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and getattr(runtime, "settings", None) is not None:
        return Path(runtime.settings.data_dir / "recordings")
    return Path("/var/lib/vizenlink-nvr/recordings")


@gallery_router.get("", response_model=GalleryListResponse)
async def list_gallery_items(
    user: CurrentUser,
    db: DbSession,
    camera_serial: str | None = None,
    item_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GalleryListResponse:
    """List gallery snapshots and video clips with pagination and filters (GAL-01)."""
    # Enforce viewer camera permissions (AUTH-05)
    allowed_serials: set[str] | list[str] | None = None
    if user.role not in ("owner", "operator"):
        permitted = {p.camera_serial for p in user.permissions}
        if camera_serial:
            if camera_serial not in permitted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied to camera '{camera_serial}'",
                )
            allowed_serials = [camera_serial]
        else:
            allowed_serials = permitted
    else:
        if camera_serial:
            allowed_serials = [camera_serial]

    items, total = await GalleryService.query_items(
        session=db,
        camera_serials=allowed_serials,
        item_type=item_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    return GalleryListResponse(
        items=[
            GalleryItemResponse(
                id=item.id,
                camera_serial=item.camera_serial,
                item_type=item.item_type,
                title=item.title,
                file_path=item.file_path,
                file_size_bytes=item.file_size_bytes,
                duration_seconds=item.duration_seconds,
                captured_at=item.captured_at,
                created_at=item.created_at,
                user_id=item.user_id,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@gallery_router.get("/{item_id}", response_model=GalleryItemResponse)
async def get_gallery_item(
    item_id: int,
    user: CurrentUser,
    db: DbSession,
) -> GalleryItemResponse:
    """Retrieve metadata for a specific gallery item."""
    item = await GalleryService.get_item(db, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gallery item {item_id} not found",
        )

    if user.role not in ("owner", "operator"):
        permitted = {p.camera_serial for p in user.permissions}
        if item.camera_serial not in permitted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{item.camera_serial}'",
            )

    return GalleryItemResponse(
        id=item.id,
        camera_serial=item.camera_serial,
        item_type=item.item_type,
        title=item.title,
        file_path=item.file_path,
        file_size_bytes=item.file_size_bytes,
        duration_seconds=item.duration_seconds,
        captured_at=item.captured_at,
        created_at=item.created_at,
        user_id=item.user_id,
    )


@gallery_router.get("/{item_id}/download")
async def download_gallery_item(
    item_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FileResponse:
    """Download the media file for a gallery item (GAL-02)."""
    item = await GalleryService.get_item(db, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gallery item {item_id} not found",
        )

    if user.role not in ("owner", "operator"):
        permitted = {p.camera_serial for p in user.permissions}
        if item.camera_serial not in permitted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to camera '{item.camera_serial}'",
            )

    storage_root = await _resolve_storage_root(request, db)
    resolved_path = GalleryService.resolve_file_path(storage_root, item.file_path)

    if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media file not found on disk: {item.file_path}",
        )

    media_type = "image/jpeg" if item.item_type == "snapshot" else "video/mp4"
    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=Path(item.file_path).name,
    )


@gallery_router.delete("/{item_id}", response_model=GalleryDeleteResponse)
async def delete_gallery_item(
    item_id: int,
    request: Request,
    user: RequireOperator,
    db: DbSession,
) -> GalleryDeleteResponse:
    """Delete a gallery item and remove its underlying file from storage (GAL-02)."""
    storage_root = await _resolve_storage_root(request, db)
    deleted_item = await GalleryService.delete_item(
        session=db,
        item_id=item_id,
        storage_root=storage_root,
        commit=True,
    )

    if deleted_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gallery item {item_id} not found",
        )

    await AuditService.record_event(
        session=db,
        action="gallery.delete_item",
        resource_type="gallery_item",
        resource_id=str(item_id),
        actor_id=user.id,
        actor_username=user.username,
        details={
            "camera_serial": deleted_item.camera_serial,
            "item_type": deleted_item.item_type,
            "file_path": deleted_item.file_path,
        },
        commit=True,
    )

    return GalleryDeleteResponse(
        status="deleted",
        id=item_id,
    )
