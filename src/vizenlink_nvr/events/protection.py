"""Event-mode pre-roll and post-roll segment protection service (REC-04, REC-12)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import Segment

logger = logging.getLogger(__name__)


class SegmentProtectionService:
    """Calculates event pre-roll/post-roll windows and protects underlying footage segments."""

    @staticmethod
    async def protect_event_segments(
        session: AsyncSession,
        camera_serial: str,
        event_id: int,
        start_time: datetime,
        end_time: datetime | None,
        pre_roll_seconds: int = 10,
        post_roll_seconds: int = 10,
    ) -> list[int]:
        """Tag all segments overlapping [start_time - pre_roll, end_time + post_roll] as protected.
        
        Returns the list of protected segment IDs.
        """
        window_start = start_time - timedelta(seconds=pre_roll_seconds)
        effective_end = end_time if end_time is not None else start_time
        window_end = effective_end + timedelta(seconds=post_roll_seconds)

        # Query overlapping segments for this camera
        # Overlap condition: segment.start_time < window_end AND segment.end_time > window_start
        stmt = (
            select(Segment)
            .where(
                Segment.camera_serial == camera_serial,
                Segment.start_time < window_end,
                Segment.end_time > window_start,
            )
        )
        res = await session.execute(stmt)
        overlapping_segments = list(res.scalars().all())

        reason_tag = f"event:{event_id}"
        protected_ids: list[int] = []

        for seg in overlapping_segments:
            seg.is_protected = True
            if seg.protection_reason:
                if reason_tag not in seg.protection_reason.split(","):
                    seg.protection_reason = f"{seg.protection_reason},{reason_tag}"
            else:
                seg.protection_reason = reason_tag
            protected_ids.append(seg.id)

        if overlapping_segments:
            await session.commit()
            logger.info(
                "Protected %d segments for event %d on %s (window %s to %s)",
                len(overlapping_segments),
                event_id,
                camera_serial,
                window_start.isoformat(),
                window_end.isoformat(),
            )

        return protected_ids

    @staticmethod
    async def release_event_segments(
        session: AsyncSession,
        event_id: int,
    ) -> list[int]:
        """Remove event protection tag; unprotect segment if no other protections remain."""
        reason_tag = f"event:{event_id}"
        stmt = select(Segment).where(Segment.protection_reason.contains(reason_tag))
        res = await session.execute(stmt)
        segments = list(res.scalars().all())

        released_ids: list[int] = []
        for seg in segments:
            if not seg.protection_reason:
                continue
            reasons = [r.strip() for r in seg.protection_reason.split(",") if r.strip() != reason_tag]
            if reasons:
                seg.protection_reason = ",".join(reasons)
            else:
                seg.protection_reason = None
                seg.is_protected = False
                released_ids.append(seg.id)

        if segments:
            await session.commit()

        return released_ids

