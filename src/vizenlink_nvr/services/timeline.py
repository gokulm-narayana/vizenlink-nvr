"""Timeline query service aggregating segments, outages, and event markers (PLAY-01, PLAY-02, PLAY-08)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import CameraOutage, Event, Segment
from vizenlink_nvr.timeutil import UTC, validate_zone


@dataclass(frozen=True)
class TimelineSegmentItem:
    id: int
    camera_serial: str
    stream_type: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    file_size_bytes: int
    is_protected: bool
    protection_reason: str | None


@dataclass(frozen=True)
class TimelineOutageItem:
    id: int
    camera_serial: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    reason: str | None


@dataclass(frozen=True)
class TimelineEventItem:
    id: int
    camera_serial: str
    event_type: str
    start_time: datetime
    end_time: datetime | None
    is_locked: bool
    snapshot_path: str | None


@dataclass(frozen=True)
class TimelineData:
    camera_serial: str
    start_time: datetime
    end_time: datetime
    segments: list[TimelineSegmentItem]
    outages: list[TimelineOutageItem]
    events: list[TimelineEventItem]


class TimelineService:
    """Service providing timeline intervals and calendar date queries."""

    @staticmethod
    async def get_timeline(
        session: AsyncSession,
        camera_serial: str,
        start_time: datetime,
        end_time: datetime,
    ) -> TimelineData:
        """Fetch segments, outages, and events overlapping [start_time, end_time]."""
        # 1. Query recorded segments
        seg_stmt = (
            select(Segment)
            .where(
                Segment.camera_serial == camera_serial,
                Segment.start_time < end_time,
                Segment.end_time > start_time,
                Segment.status != "missing",
            )
            .order_by(Segment.start_time.asc())
        )
        seg_rows = (await session.execute(seg_stmt)).scalars().all()
        segments = [
            TimelineSegmentItem(
                id=s.id,
                camera_serial=s.camera_serial,
                stream_type=s.stream_type,
                start_time=s.start_time,
                end_time=s.end_time,
                duration_seconds=s.duration_seconds,
                file_size_bytes=s.file_size_bytes,
                is_protected=s.is_protected,
                protection_reason=s.protection_reason,
            )
            for s in seg_rows
        ]

        # 2. Query camera outages (PLAY-08)
        outage_stmt = (
            select(CameraOutage)
            .where(
                CameraOutage.camera_serial == camera_serial,
                CameraOutage.started_at < end_time,
                or_(
                    CameraOutage.ended_at.is_(None),
                    CameraOutage.ended_at > start_time,
                ),
            )
            .order_by(CameraOutage.started_at.asc())
        )
        outage_rows = (await session.execute(outage_stmt)).scalars().all()
        outages = [
            TimelineOutageItem(
                id=o.id,
                camera_serial=o.camera_serial,
                started_at=o.started_at,
                ended_at=o.ended_at,
                duration_seconds=o.duration_seconds,
                reason=o.reason,
            )
            for o in outage_rows
        ]

        # 3. Query camera events
        evt_stmt = (
            select(Event)
            .where(
                Event.camera_serial == camera_serial,
                Event.start_time <= end_time,
                or_(
                    Event.end_time.is_(None),
                    Event.end_time >= start_time,
                ),
            )
            .order_by(Event.start_time.asc())
        )
        evt_rows = (await session.execute(evt_stmt)).scalars().all()
        events = [
            TimelineEventItem(
                id=e.id,
                camera_serial=e.camera_serial,
                event_type=e.event_type,
                start_time=e.start_time,
                end_time=e.end_time,
                is_locked=e.is_locked,
                snapshot_path=e.snapshot_path,
            )
            for e in evt_rows
        ]

        return TimelineData(
            camera_serial=camera_serial,
            start_time=start_time,
            end_time=end_time,
            segments=segments,
            outages=outages,
            events=events,
        )

    @staticmethod
    async def get_recorded_days(
        session: AsyncSession,
        camera_serial: str,
        year: int,
        month: int,
        tz_name: str = "UTC",
    ) -> list[str]:
        """Return sorted YYYY-MM-DD local dates in *tz_name* with recorded segments (PLAY-02)."""
        zone = validate_zone(tz_name)
        month_start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=zone)
        next_month_local = (
            datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=zone)
            if month == 12
            else datetime(year, month + 1, 1, 0, 0, 0, tzinfo=zone)
        )
        month_start_utc = month_start_local.astimezone(UTC)
        month_end_utc = next_month_local.astimezone(UTC)

        stmt = (
            select(Segment.start_time, Segment.end_time)
            .where(
                Segment.camera_serial == camera_serial,
                Segment.end_time > month_start_utc,
                Segment.start_time < month_end_utc,
                Segment.status != "missing",
            )
            .order_by(Segment.start_time.asc())
        )
        rows = (await session.execute(stmt)).all()

        seen_dates: set[str] = set()
        for start_dt, end_dt in rows:
            start_utc = start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=UTC)
            end_utc = end_dt if end_dt.tzinfo else end_dt.replace(tzinfo=UTC)
            # Subtract 1 us from end_time so a segment ending cleanly at local midnight
            # doesn't mark the following empty day as having footage.
            effective_end = end_utc - timedelta(microseconds=1)
            if effective_end < start_utc:
                effective_end = start_utc

            cur_date = start_utc.astimezone(zone).date()
            end_date = effective_end.astimezone(zone).date()
            while cur_date <= end_date:
                if cur_date.year == year and cur_date.month == month:
                    seen_dates.add(cur_date.isoformat())
                cur_date += timedelta(days=1)

        return sorted(seen_dates)

    @staticmethod
    async def search_recordings(
        session: AsyncSession,
        camera_serial: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search recordings by event occurrences and time windows (GAL-03)."""
        stmt = (
            select(Event)
            .where(Event.camera_serial == camera_serial)
            .order_by(Event.start_time.desc())
        )
        if start_time:
            stmt = stmt.where(Event.start_time >= start_time)
        if end_time:
            stmt = stmt.where(Event.start_time <= end_time)
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)

        res = await session.execute(stmt)
        events = res.scalars().all()

        results = []
        for evt in events:
            results.append(
                {
                    "event_id": evt.id,
                    "camera_serial": evt.camera_serial,
                    "event_type": evt.event_type,
                    "timestamp": evt.start_time,
                    "snapshot_path": evt.snapshot_path,
                    "is_locked": evt.is_locked,
                }
            )
        return results

