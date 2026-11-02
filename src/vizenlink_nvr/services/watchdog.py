"""Recording gap watchdog and exponential backoff stream reconnect coordinator (REC-10, HLTH-03)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, overload

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from vizenlink_nvr.db.models import Camera, Segment
from vizenlink_nvr.services.health import CameraHealth, OnlineState, RecordingState
from vizenlink_nvr.timeutil import UTC, utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_SEGMENT_DURATION_SECONDS = 60.0
DEFAULT_GAP_TOLERANCE_SECONDS = 30.0
# 2 * segment_duration + 30s = 150s (D-39)
DEFAULT_EXPECTED_WINDOW_SECONDS = (2 * DEFAULT_SEGMENT_DURATION_SECONDS) + DEFAULT_GAP_TOLERANCE_SECONDS
MIN_RECONNECT_BACKOFF = 1.0
MAX_RECONNECT_BACKOFF = 60.0


def get_reconnect_backoff(
    failure_count: int,
    min_backoff: float = MIN_RECONNECT_BACKOFF,
    max_backoff: float = MAX_RECONNECT_BACKOFF,
) -> float:
    """Calculate binary exponential backoff with a maximum cap (REC-10).

    Sequence: 1s, 2s, 4s, 8s, 16s, 32s, capped at 60s.
    """
    if failure_count <= 0:
        return float(min_backoff)
    backoff = min_backoff * (2.0 ** failure_count)
    return float(min(max_backoff, backoff))


@overload
def _ensure_tz_aware(dt: None) -> None: ...


@overload
def _ensure_tz_aware(dt: datetime) -> datetime: ...


def _ensure_tz_aware(dt: datetime | None) -> datetime | None:
    """Ensure datetime has UTC timezone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def check_camera_gaps(
    session: AsyncSession,
    now: datetime | None = None,
    expected_window_seconds: float = DEFAULT_EXPECTED_WINDOW_SECONDS,
) -> dict[str, CameraHealth]:
    """Inspect recent segments per camera and identify recording gaps (>150s) (HLTH-03)."""
    current_time = _ensure_tz_aware(now) if now is not None else utc_now()
    if current_time is None:
        current_time = utc_now()

    # Load all registered cameras with their recording settings
    cam_stmt = select(Camera).options(selectinload(Camera.recording_settings))
    cam_res = await session.execute(cam_stmt)
    cameras = cam_res.scalars().all()

    # Query latest segment end_time per camera
    seg_stmt = (
        select(Segment.camera_serial, func.max(Segment.end_time))
        .where(Segment.status != "missing")
        .group_by(Segment.camera_serial)
    )
    seg_res = await session.execute(seg_stmt)
    last_segments: dict[str, datetime] = {
        row[0]: _ensure_tz_aware(row[1]) for row in seg_res.all() if row[1] is not None
    }

    results: dict[str, CameraHealth] = {}

    for cam in cameras:
        # 1. Determine online reachability state
        if cam.state == "active":
            online = OnlineState.ONLINE
        elif cam.state == "auth_failed":
            online = OnlineState.AUTH_FAILED
        else:
            online = OnlineState.OFFLINE

        # 2. Check recording configuration
        rec_mode = cam.recording_settings.mode if cam.recording_settings else "continuous"
        last_seg = last_segments.get(cam.serial)

        if rec_mode == "off":
            results[cam.serial] = CameraHealth(
                camera_serial=cam.serial,
                online_state=online,
                recording_state=RecordingState.DISABLED,
                last_segment_at=last_seg,
                gap_alarm=False,
                segment_age_seconds=max(0.0, (current_time - last_seg).total_seconds()) if last_seg else None,
                details="Recording disabled",
            )
            continue

        # 3. Active recording mode: evaluate elapsed window
        if last_seg is not None:
            age_sec = max(0.0, (current_time - last_seg).total_seconds())
            if age_sec > expected_window_seconds:
                # Gap exceeded: gap alarm raised, recording state is NOT_RECORDING (HLTH-03)
                results[cam.serial] = CameraHealth(
                    camera_serial=cam.serial,
                    online_state=online,
                    recording_state=RecordingState.NOT_RECORDING,
                    last_segment_at=last_seg,
                    gap_alarm=True,
                    segment_age_seconds=round(age_sec, 1),
                    details=f"No segments for {round(age_sec, 1)}s (threshold: {expected_window_seconds}s)",
                )
            else:
                # Healthy recording within window
                results[cam.serial] = CameraHealth(
                    camera_serial=cam.serial,
                    online_state=online,
                    recording_state=RecordingState.RECORDING,
                    last_segment_at=last_seg,
                    gap_alarm=False,
                    segment_age_seconds=round(age_sec, 1),
                    details="Recording active",
                )
        else:
            # No segments recorded yet: check elapsed time since camera was added
            cam_added = _ensure_tz_aware(cam.added_at) or current_time
            age_since_add = max(0.0, (current_time - cam_added).total_seconds())
            if age_since_add > expected_window_seconds:
                # Camera added a while ago but never produced a segment: gap alarm raised
                results[cam.serial] = CameraHealth(
                    camera_serial=cam.serial,
                    online_state=online,
                    recording_state=RecordingState.NOT_RECORDING,
                    last_segment_at=None,
                    gap_alarm=True,
                    segment_age_seconds=None,
                    details=f"No footage recorded since added ({round(age_since_add, 1)}s ago)",
                )
            else:
                # Recently added, within initial startup window
                results[cam.serial] = CameraHealth(
                    camera_serial=cam.serial,
                    online_state=online,
                    recording_state=RecordingState.NOT_RECORDING,
                    last_segment_at=None,
                    gap_alarm=False,
                    segment_age_seconds=None,
                    details="Starting recording initial segment",
                )

    return results


class WatchdogService:
    """Gap watchdog and stream reconnect coordinator."""

    @staticmethod
    async def check_camera_gaps(
        session: AsyncSession,
        now: datetime | None = None,
        expected_window_seconds: float = DEFAULT_EXPECTED_WINDOW_SECONDS,
    ) -> dict[str, CameraHealth]:
        return await check_camera_gaps(session, now=now, expected_window_seconds=expected_window_seconds)

    @staticmethod
    def get_reconnect_backoff(
        failure_count: int,
        min_backoff: float = MIN_RECONNECT_BACKOFF,
        max_backoff: float = MAX_RECONNECT_BACKOFF,
    ) -> float:
        return get_reconnect_backoff(failure_count, min_backoff=min_backoff, max_backoff=max_backoff)
