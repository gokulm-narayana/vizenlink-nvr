"""Gallery media items management service (GAL-01, GAL-02, PLAY-06, PLAY-07, LIVE-07)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import GalleryItem
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

GalleryItemType = Literal["snapshot", "manual_clip", "export_clip"]
VALID_GALLERY_ITEM_TYPES = {"snapshot", "manual_clip", "export_clip"}


class GalleryService:
    """Service managing snapshot and clip gallery storage and metadata."""

    @staticmethod
    def generate_relative_path(
        camera_serial: str,
        item_type: GalleryItemType,
        captured_at: datetime,
        filename: str,
    ) -> str:
        """Construct secure relative path under storage root."""
        safe_serial = camera_serial.lower().replace("/", "_").replace("\\", "_")
        year_str = captured_at.strftime("%Y")
        month_str = captured_at.strftime("%m")
        day_str = captured_at.strftime("%d")

        folder = "snapshots" if item_type == "snapshot" else "clips"
        return f"gallery/{folder}/{safe_serial}/{year_str}/{month_str}/{day_str}/{filename}"

    @staticmethod
    def resolve_file_path(storage_root: Path, rel_path: str) -> Path | None:
        """Resolve storage-relative path ensuring no directory traversal."""
        root = storage_root.resolve()
        candidate = (root / rel_path).resolve()
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            logger.warning("Directory traversal attempt detected for gallery path: %s", rel_path)
            return None

    @staticmethod
    async def create_item(
        session: AsyncSession,
        camera_serial: str,
        item_type: str,
        title: str,
        file_path: str,
        file_size_bytes: int,
        captured_at: datetime,
        duration_seconds: float | None = None,
        user_id: int | None = None,
        commit: bool = True,
    ) -> GalleryItem:
        """Create a new gallery record in database."""
        if item_type not in VALID_GALLERY_ITEM_TYPES:
            raise ValueError(
                f"Invalid item_type '{item_type}'. Must be one of: {VALID_GALLERY_ITEM_TYPES}"
            )

        item = GalleryItem(
            camera_serial=camera_serial,
            item_type=item_type,
            title=title,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            duration_seconds=duration_seconds,
            captured_at=captured_at,
            user_id=user_id,
            created_at=utc_now(),
        )
        session.add(item)
        if commit:
            await session.commit()
            await session.refresh(item)
        return item

    @staticmethod
    async def get_item(
        session: AsyncSession,
        item_id: int,
    ) -> GalleryItem | None:
        """Retrieve gallery item by ID."""
        return await session.get(GalleryItem, item_id)

    @staticmethod
    async def delete_item(
        session: AsyncSession,
        item_id: int,
        storage_root: Path,
        commit: bool = True,
    ) -> GalleryItem | None:
        """Delete gallery item and remove its underlying file from disk."""
        item = await session.get(GalleryItem, item_id)
        if item is None:
            return None

        # Delete file from disk if present
        resolved = GalleryService.resolve_file_path(storage_root, item.file_path)
        if resolved is not None and resolved.exists():
            try:
                resolved.unlink(missing_ok=True)
            except Exception as exc:
                logger.error("Failed to delete gallery file %s: %s", resolved, exc)

        await session.delete(item)
        if commit:
            await session.commit()
        return item

    @staticmethod
    async def query_items(
        session: AsyncSession,
        camera_serials: set[str] | list[str] | None = None,
        item_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        user_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GalleryItem], int]:
        """Query gallery items with filtering and pagination."""
        stmt = select(GalleryItem).order_by(GalleryItem.captured_at.desc())
        count_stmt = select(func.count(GalleryItem.id))

        if camera_serials is not None:
            stmt = stmt.where(GalleryItem.camera_serial.in_(camera_serials))
            count_stmt = count_stmt.where(GalleryItem.camera_serial.in_(camera_serials))

        if item_type:
            stmt = stmt.where(GalleryItem.item_type == item_type)
            count_stmt = count_stmt.where(GalleryItem.item_type == item_type)

        if start_time:
            stmt = stmt.where(GalleryItem.captured_at >= start_time)
            count_stmt = count_stmt.where(GalleryItem.captured_at >= start_time)

        if end_time:
            stmt = stmt.where(GalleryItem.captured_at <= end_time)
            count_stmt = count_stmt.where(GalleryItem.captured_at <= end_time)

        if user_id is not None:
            stmt = stmt.where(GalleryItem.user_id == user_id)
            count_stmt = count_stmt.where(GalleryItem.user_id == user_id)

        total_count = (await session.execute(count_stmt)).scalar_one()
        paged_stmt = stmt.limit(limit).offset(offset)
        res = await session.execute(paged_stmt)
        items = list(res.scalars().all())

        return items, total_count
