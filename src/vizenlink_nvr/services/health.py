"""Aggregated recorder health evaluator and dual camera badge models (HLTH-01, HLTH-06)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from vizenlink_nvr.services.storage import StorageHealthState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class OnlineState(StrEnum):
    """Camera network reachability / credential health state."""

    ONLINE = "online"
    OFFLINE = "offline"
    AUTH_FAILED = "auth_failed"


class RecordingState(StrEnum):
    """Camera recording output health state."""

    RECORDING = "recording"
    NOT_RECORDING = "not_recording"
    DISABLED = "disabled"


class RecorderHealthStatus(StrEnum):
    """Overall recorder subsystem health state (HLTH-06)."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass(frozen=True)
class CameraHealth:
    """Dual independent health badges and gap monitoring for a camera (HLTH-01, HLTH-03)."""

    camera_serial: str
    online_state: OnlineState
    recording_state: RecordingState
    last_segment_at: datetime | None
    gap_alarm: bool
    segment_age_seconds: float | None = None
    details: str | None = None


@dataclass(frozen=True)
class RecorderStatus:
    """Aggregated recorder health status across DB, MediaMTX, Storage, and cameras."""

    status: RecorderHealthStatus
    db_ok: bool
    mediamtx_ok: bool
    storage_ok: bool
    details: dict[str, Any] = field(default_factory=dict)


class RecorderHealthService:
    """Aggregates recorder health from DB, MediaMTX process, storage volume, and camera gaps."""

    @staticmethod
    async def get_recorder_status(
        session: AsyncSession | None,
        media_status: bool | dict[str, Any] | None = True,
        storage_status: bool | Any | None = True,
        gap_count: int = 0,
    ) -> RecorderStatus:
        """Evaluate overall recorder health: healthy, degraded, or critical (HLTH-06)."""
        db_ok = False
        if session is not None:
            try:
                res = await session.execute(text("SELECT 1"))
                db_ok = (res.scalar() == 1)
            except Exception as exc:
                logger.warning("Database health probe failed: %s", exc)
                db_ok = False

        # MediaMTX status resolution
        if isinstance(media_status, bool):
            mediamtx_ok = media_status
        elif isinstance(media_status, dict):
            mediamtx_ok = bool(media_status.get("alive", True))
        elif media_status is None:
            mediamtx_ok = False
        else:
            mediamtx_ok = bool(media_status)

        # Storage status resolution
        if storage_status is None:
            storage_ok = False
        elif isinstance(storage_status, bool):
            storage_ok = storage_status
        elif isinstance(storage_status, StorageHealthState):
            storage_ok = (storage_status == StorageHealthState.OK)
        elif hasattr(storage_status, "health_state"):
            storage_ok = (str(storage_status.health_state).lower() in ("ok", "storagehealthstate.ok"))
        else:
            storage_ok = bool(storage_status)

        details: dict[str, Any] = {
            "db": "ok" if db_ok else "unreachable",
            "mediamtx": "ok" if mediamtx_ok else "unreachable",
            "storage": "ok" if storage_ok else "unhealthy",
            "gap_count": gap_count,
        }

        # Overall health classification
        if not db_ok:
            status = RecorderHealthStatus.CRITICAL
        elif not mediamtx_ok or not storage_ok or gap_count > 0:
            status = RecorderHealthStatus.DEGRADED
        else:
            status = RecorderHealthStatus.HEALTHY

        return RecorderStatus(
            status=status,
            db_ok=db_ok,
            mediamtx_ok=mediamtx_ok,
            storage_ok=storage_ok,
            details=details,
        )
