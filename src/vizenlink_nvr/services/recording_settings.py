"""Per-camera recording configuration and policy management service."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from vizenlink_nvr.db.models import Camera, CameraCapabilitiesRow, RecordingSettings
from vizenlink_nvr.services.schedule import WeeklySchedule
from vizenlink_nvr.timeutil import utc_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class RecordingMode(StrEnum):
    """Recording mode operational policy."""

    CONTINUOUS = "continuous"
    SCHEDULED = "scheduled"
    EVENT = "event"
    OFF = "off"


class CameraNotFoundError(ValueError):
    """Camera serial does not exist in database."""


class AudioNotSupportedError(ValueError):
    """Camera hardware does not support audio recording."""


def camera_supports_audio(caps_raw: str | None) -> bool:
    """Determine whether camera hardware capabilities support audio recording."""
    if not caps_raw:
        # Capabilities not probed or empty; assume supported until probed otherwise
        return True

    try:
        data = json.loads(caps_raw)
        if not isinstance(data, dict):
            return True

        if "audio_capable" in data:
            return bool(data["audio_capable"])
        if "has_audio" in data:
            return bool(data["has_audio"])
        if "audio" in data and isinstance(data["audio"], bool):
            return bool(data["audio"])

        # Check for presence of audio strings in raw payload
        if "audio_encoder" in caps_raw or "audio_source" in caps_raw:
            return True

        return True
    except Exception:
        return True


async def get_recording_settings(
    session: AsyncSession,
    camera_serial: str,
) -> RecordingSettings | None:
    """Retrieve recording settings for camera_serial if configured."""
    stmt = select(RecordingSettings).where(RecordingSettings.camera_serial == camera_serial)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_recording_settings(
    session: AsyncSession,
    camera_serial: str,
    *, commit: bool = True,
) -> RecordingSettings:
    """Retrieve existing recording settings or initialize default settings for registered camera."""
    # Ensure camera exists
    cam_stmt = select(Camera).where(Camera.serial == camera_serial)
    cam_res = await session.execute(cam_stmt)
    if cam_res.scalar_one_or_none() is None:
        raise CameraNotFoundError(f"Camera '{camera_serial}' does not exist")

    settings = await get_recording_settings(session, camera_serial)
    if settings is not None:
        return settings

    now = utc_now()
    default_schedule = WeeklySchedule.always().to_json()
    new_settings = RecordingSettings(
        camera_serial=camera_serial,
        mode=RecordingMode.CONTINUOUS.value,
        schedule_json=default_schedule,
        audio_enabled=False,
        retention_days=None,
        retention_max_gb=None,
        created_at=now,
        updated_at=now,
    )
    session.add(new_settings)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return new_settings


async def set_recording_mode(
    session: AsyncSession,
    camera_serial: str,
    mode: RecordingMode | str,
    *, commit: bool = True,
) -> RecordingSettings:
    """Set recording operational mode for camera."""
    mode_str = str(mode).strip().lower()
    valid_modes = {m.value for m in RecordingMode}
    if mode_str not in valid_modes:
        raise ValueError(f"Invalid recording mode '{mode_str}'. Valid modes: {sorted(valid_modes)}")

    settings = await get_or_create_recording_settings(session, camera_serial, commit=commit)
    settings.mode = mode_str
    settings.updated_at = utc_now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return settings


async def set_recording_schedule(
    session: AsyncSession,
    camera_serial: str,
    schedule: WeeklySchedule | str | dict[str, Any],
    *, commit: bool = True,
) -> RecordingSettings:
    """Set weekly recording schedule for camera."""
    sched_obj = WeeklySchedule.from_spec(schedule)
    settings = await get_or_create_recording_settings(session, camera_serial, commit=commit)
    settings.schedule_json = sched_obj.to_json()
    settings.updated_at = utc_now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return settings


async def set_recording_audio(
    session: AsyncSession,
    camera_serial: str,
    enabled: bool,
    *, commit: bool = True,
) -> RecordingSettings:
    """Toggle audio recording track for camera, verifying camera capabilities."""
    if enabled:
        # Check camera capabilities
        caps_stmt = select(CameraCapabilitiesRow).where(CameraCapabilitiesRow.serial == camera_serial)
        caps_res = await session.execute(caps_stmt)
        caps_row = caps_res.scalar_one_or_none()
        if caps_row is not None and not camera_supports_audio(caps_row.raw_json):
            raise AudioNotSupportedError(f"Camera '{camera_serial}' does not support audio recording")

    settings = await get_or_create_recording_settings(session, camera_serial, commit=commit)
    settings.audio_enabled = enabled
    settings.updated_at = utc_now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return settings


async def set_recording_retention(
    session: AsyncSession,
    camera_serial: str,
    days: int | None,
    max_gb: int | None,
    *, commit: bool = True,
) -> RecordingSettings:
    """Configure retention window and size limit for camera."""
    if days is not None and days <= 0:
        raise ValueError("Retention days must be positive")
    if max_gb is not None and max_gb <= 0:
        raise ValueError("Retention max_gb must be positive")

    settings = await get_or_create_recording_settings(session, camera_serial, commit=commit)
    settings.retention_days = days
    settings.retention_max_gb = max_gb
    settings.updated_at = utc_now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return settings


async def should_record_now(
    session: AsyncSession,
    camera_serial: str,
    now: datetime | None = None,
    tz_name: str = "UTC",
) -> bool:
    """Evaluate whether camera should be actively recording at this moment."""
    settings = await get_recording_settings(session, camera_serial)
    if settings is None:
        return False

    mode = settings.mode
    if mode == RecordingMode.OFF.value:
        return False

    if mode == RecordingMode.CONTINUOUS.value:
        return True

    if mode == RecordingMode.EVENT.value:
        # Rolling circular buffer active ready for event locks (Phase 4)
        return True

    if mode == RecordingMode.SCHEDULED.value:
        if now is None:
            now = utc_now()
        schedule = WeeklySchedule.from_spec(settings.schedule_json)
        return schedule.is_active_at(now, tz_name)

    return False
