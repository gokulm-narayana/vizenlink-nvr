"""Gallery REST API endpoints (GAL-01, GAL-02, LIVE-07, AUTH-05)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
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
from vizenlink_nvr.network.mdns import get_local_ip
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.gallery import GalleryService
from vizenlink_nvr.services.media_token import default_media_token_service
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

gallery_router = APIRouter(prefix="/gallery", tags=["gallery"])


def _detect_clip_media_type(path: Path) -> str:
    """Detect whether a video clip is WebM (EBML header) or MP4."""
    try:
        with path.open("rb") as fh:
            header = fh.read(4)
    except OSError:
        return "video/mp4"
    return "video/webm" if header.startswith(b"\x1a\x45\xdf\xa3") else "video/mp4"


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


class GalleryShareResponse(BaseModel):
    item_id: int
    share_url: str
    qr_payload: str
    expires_at: datetime


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
    download: bool = Query(default=False),
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

    media_type = (
        "image/jpeg" if item.item_type == "snapshot" else _detect_clip_media_type(resolved_path)
    )
    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=Path(item.file_path).name,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "no-cache"},
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


@gallery_router.post("/{item_id}/share", response_model=GalleryShareResponse)
async def share_gallery_item(
    item_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    expires_in_seconds: int = Query(3600, ge=60, le=86400),
) -> GalleryShareResponse:
    """Generate a signed LAN-accessible share URL and QR payload for a gallery item."""
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

    token = default_media_token_service.generate_token(
        user_id=user.id,
        camera_serial=item.camera_serial,
        stream=f"gallery:{item.id}",
        ttl_seconds=expires_in_seconds,
    )

    req_host = request.url.hostname or "127.0.0.1"
    loopback_hosts = ("localhost", "127.0.0.1", "::1", "0.0.0.0")  # noqa: S104
    host = get_local_ip() if req_host in loopback_hosts else req_host
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = request.url.port
    host_part = f"{host}:{port}" if port and port not in (80, 443) else host
    share_url = f"{request.url.scheme}://{host_part}/api/v1/gallery/{item.id}/shared?token={token}"
    expires_at = utc_now() + timedelta(seconds=expires_in_seconds)

    await AuditService.record_event(
        session=db,
        action="gallery.share_item",
        resource_type="gallery_item",
        resource_id=str(item.id),
        actor_id=user.id,
        actor_username=user.username,
        details={
            "camera_serial": item.camera_serial,
            "item_type": item.item_type,
            "expires_in_seconds": expires_in_seconds,
        },
        commit=True,
    )

    return GalleryShareResponse(
        item_id=item.id,
        share_url=share_url,
        qr_payload=share_url,
        expires_at=expires_at,
    )


@gallery_router.get("/{item_id}/shared")
async def download_shared_gallery_item(
    item_id: int,
    request: Request,
    db: DbSession,
    token: str = Query(..., min_length=1),
    download: bool = Query(default=False),
) -> FileResponse:
    """Download or open a gallery item using a signed QR share token."""
    payload = default_media_token_service.verify_token(token)
    if payload is None or payload.get("stream") != f"gallery:{item_id}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired share token",
        )

    item = await GalleryService.get_item(db, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gallery item {item_id} not found",
        )

    if payload.get("serial") != item.camera_serial:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Share token does not match item camera",
        )

    storage_root = await _resolve_storage_root(request, db)
    resolved_path = GalleryService.resolve_file_path(storage_root, item.file_path)

    if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media file not found on disk: {item.file_path}",
        )

    media_type = (
        "image/jpeg" if item.item_type == "snapshot" else _detect_clip_media_type(resolved_path)
    )
    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=Path(item.file_path).name,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "no-cache"},
    )
