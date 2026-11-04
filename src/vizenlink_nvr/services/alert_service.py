"""In-app alert evaluation service (HLTH-08)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import CameraOutage
from vizenlink_nvr.services.storage import get_storage_config
from vizenlink_nvr.timeutil import utc_now

logger = logging.getLogger(__name__)

DEFAULT_OFFLINE_ALERT_SECONDS: float = 300.0  # 5 minutes
DISK_HYSTERESIS_BYTES: int = 1024 * 1024 * 1024  # 1 GiB


@dataclass(frozen=True)
class InAppAlert:
    """Structured in-app notification for operational anomalies."""

    id: str
    severity: str  # "info", "warning", "critical"
    title: str
    message: str
    timestamp: datetime
    source: str


class AlertService:
    """Evaluates active system health alerts across cameras, storage, and recording watchdog."""

    @staticmethod
    async def evaluate_active_alerts(
        session: AsyncSession,
        now: datetime | None = None,
        offline_threshold_seconds: float = DEFAULT_OFFLINE_ALERT_SECONDS,
        default_storage_path: Path = Path("/var/lib/vizenlink-nvr/recordings"),
        gap_serials: list[str] | None = None,
    ) -> list[InAppAlert]:
        """Evaluate all active anomalies and return current list of alerts."""
        current_time = now or utc_now()
        alerts: list[InAppAlert] = []

        # 1. Prolonged camera offline alerts
        stmt = select(CameraOutage).where(CameraOutage.ended_at.is_(None))
        open_outages = (await session.execute(stmt)).scalars().all()

        for outage in open_outages:
            offline_duration = (current_time - outage.started_at).total_seconds()
            if offline_duration >= offline_threshold_seconds:
                mins = int(offline_duration // 60)
                alerts.append(
                    InAppAlert(
                        id=f"camera_offline_{outage.camera_serial}",
                        severity="warning",
                        title=f"Camera {outage.camera_serial} Offline",
                        message=(
                            f"Camera '{outage.camera_serial}' has been offline for "
                            f"{mins} minutes (since {outage.started_at.strftime('%H:%M:%S')})."
                        ),
                        timestamp=outage.started_at,
                        source=f"camera:{outage.camera_serial}",
                    )
                )

        # 2. Disk low space alerts
        try:
            cfg = await get_storage_config(session, default_path=default_storage_path)
            if cfg.telemetry is not None:
                critical_threshold = cfg.reserve_bytes + DISK_HYSTERESIS_BYTES
                if cfg.telemetry.free_bytes < critical_threshold:
                    free_gb = cfg.telemetry.free_bytes / (1024 * 1024 * 1024)
                    reserve_gb = cfg.reserve_bytes / (1024 * 1024 * 1024)
                    alerts.append(
                        InAppAlert(
                            id="storage_disk_nearly_full",
                            severity="critical",
                            title="Recording Storage Space Low",
                            message=(
                                f"Free disk space ({free_gb:.1f} GiB) is approaching the "
                                f"reserve threshold ({reserve_gb:.1f} GiB)."
                            ),
                            timestamp=current_time,
                            source="storage",
                        )
                    )
        except Exception as exc:
            logger.warning("Failed to evaluate storage disk space for alerts: %s", exc)

        # 3. Recording gap alarms
        if gap_serials:
            for serial in gap_serials:
                alerts.append(
                    InAppAlert(
                        id=f"recording_gap_{serial}",
                        severity="warning",
                        title=f"Recording Gap Alarm: {serial}",
                        message=f"Camera '{serial}' experienced an unexpected gap in continuous recording.",
                        timestamp=current_time,
                        source=f"watchdog:{serial}",
                    )
                )

        return alerts
