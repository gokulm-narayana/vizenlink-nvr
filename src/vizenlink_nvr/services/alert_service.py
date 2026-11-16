"""In-app alert evaluation service (HLTH-08)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.models import Camera, CameraOutage
from vizenlink_nvr.services.settings import read_site_timezone
from vizenlink_nvr.services.storage import StorageHealthState, get_storage_config
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
        # People know cameras by name ("Lobby"), not serial; fall back to the serial if unnamed.
        names = {
            serial: name
            for serial, name in (await session.execute(select(Camera.serial, Camera.name))).all()
            if name
        }

        # Show the start time in the site time zone, like every other time in the UI.
        try:
            site_zone: ZoneInfo | None = ZoneInfo(await read_site_timezone(session))
        except Exception:  # noqa: BLE001 - an unreadable zone must not hide the alert
            site_zone = None

        for outage in open_outages:
            offline_duration = (current_time - outage.started_at).total_seconds()
            if offline_duration >= offline_threshold_seconds:
                started_local = outage.started_at.astimezone(site_zone) if site_zone else outage.started_at
                same_day = started_local.date() == current_time.astimezone(started_local.tzinfo).date()
                since = started_local.strftime("%H:%M" if same_day else "%b %d, %H:%M")
                cam_label = names.get(outage.camera_serial, outage.camera_serial)
                alerts.append(
                    InAppAlert(
                        id=f"camera_offline_{outage.camera_serial}",
                        severity="warning",
                        title=f"{cam_label} is offline",
                        message=(
                            f"Offline for {_humanize_duration(offline_duration)} (since {since})."
                        ),
                        timestamp=outage.started_at,
                        source=f"camera:{outage.camera_serial}",
                    )
                )

        # 2. Disk low space alerts
        try:
            cfg = await get_storage_config(session, default_path=default_storage_path)
            if cfg.health_state != StorageHealthState.OK:
                # Recording cannot write anywhere: this is the most important alert the NVR has.
                alerts.append(
                    InAppAlert(
                        id="storage_unavailable",
                        severity="critical",
                        title="Not recording: storage unavailable",
                        message=(
                            f"The recording folder '{cfg.storage_path}' can't be used "
                            f"({cfg.health_state.value}). No footage is being saved. "
                            "Choose a writable storage location in Settings."
                        ),
                        timestamp=current_time,
                        source="storage",
                    )
                )
            elif cfg.telemetry is not None:
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


def _humanize_duration(seconds: float) -> str:
    """Render a duration the way people say it: "8 minutes", "5 hours", "2 days 3 hours"."""

    def unit(value: int, name: str) -> str:
        return f"{value} {name}" if value == 1 else f"{value} {name}s"

    minutes = int(seconds // 60)
    if minutes < 60:
        return unit(max(minutes, 1), "minute")
    hours, rem_minutes = divmod(minutes, 60)
    if hours < 24:
        return unit(hours, "hour") + (f" {unit(rem_minutes, 'minute')}" if rem_minutes else "")
    days, rem_hours = divmod(hours, 24)
    return unit(days, "day") + (f" {unit(rem_hours, 'hour')}" if rem_hours else "")
