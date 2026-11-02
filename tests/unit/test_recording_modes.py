"""Unit tests for RecordingSettingsService, modes, audio, retention, and evaluation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.db.engine import create_engine_for
from vizenlink_nvr.db.models import Base, Camera, CameraCapabilitiesRow
from vizenlink_nvr.services.recording_settings import (
    AudioNotSupportedError,
    CameraNotFoundError,
    RecordingMode,
    get_or_create_recording_settings,
    set_recording_audio,
    set_recording_mode,
    set_recording_retention,
    set_recording_schedule,
    should_record_now,
)
from vizenlink_nvr.services.schedule import WeeklySchedule
from vizenlink_nvr.timeutil import UTC, utc_now


@pytest.fixture
async def db_session(tmp_path: Path):
    """Fixture providing isolated SQLite DB session with applied schema."""
    db_file = tmp_path / "test_rec_settings.db"
    engine = create_engine_for(db_file)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = utc_now()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Seed a camera
        cam = Camera(
            serial="VZL-CAM-TEST1",
            host="192.168.1.100",
            https_port=443,
            mac="AA:BB:CC:DD:EE:01",
            name="Test Camera 1",
            location="Front Entrance",
            group_tag="front",
            manufacturer="NuraEye",
            model="NE-4K",
            firmware_version="v2.1.0",
            hardware_id="HW-01",
            tls_fingerprint_sha256="abc",
            camera_id_check=True,
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam)

        # Seed a second camera that has no audio support
        cam_no_audio = Camera(
            serial="VZL-CAM-NOAUDIO",
            host="192.168.1.101",
            https_port=443,
            mac="AA:BB:CC:DD:EE:02",
            name="No Audio Camera",
            location="Warehouse",
            group_tag="storage",
            manufacturer="NuraEye",
            model="NE-2K-MUTE",
            firmware_version="v1.0.0",
            hardware_id="HW-02",
            tls_fingerprint_sha256="def",
            camera_id_check=False,
            added_at=now,
            host_updated_at=now,
        )
        session.add(cam_no_audio)

        caps_no_audio = CameraCapabilitiesRow(
            serial="VZL-CAM-NOAUDIO",
            raw_json=json.dumps({"audio_capable": False}),
            probed_at=now,
            firmware_version_at_probe="v1.0.0",
        )
        session.add(caps_no_audio)

        await session.commit()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_create_recording_settings(db_session: AsyncSession) -> None:
    """Initializes default settings for registered camera; fails for unknown camera."""
    # Unknown camera
    with pytest.raises(CameraNotFoundError, match="VZL-UNKNOWN"):
        await get_or_create_recording_settings(db_session, "VZL-UNKNOWN")

    # Registered camera
    settings = await get_or_create_recording_settings(db_session, "VZL-CAM-TEST1")
    assert settings.camera_serial == "VZL-CAM-TEST1"
    assert settings.mode == RecordingMode.CONTINUOUS.value
    assert settings.audio_enabled is False
    assert settings.retention_days is None
    assert settings.retention_max_gb is None


@pytest.mark.asyncio
async def test_set_recording_mode(db_session: AsyncSession) -> None:
    """Updates recording mode and rejects invalid mode strings."""
    settings = await set_recording_mode(db_session, "VZL-CAM-TEST1", RecordingMode.SCHEDULED)
    assert settings.mode == "scheduled"

    settings = await set_recording_mode(db_session, "VZL-CAM-TEST1", "event")
    assert settings.mode == "event"

    settings = await set_recording_mode(db_session, "VZL-CAM-TEST1", "off")
    assert settings.mode == "off"

    with pytest.raises(ValueError, match="Invalid recording mode"):
        await set_recording_mode(db_session, "VZL-CAM-TEST1", "super_record")


@pytest.mark.asyncio
async def test_set_recording_schedule(db_session: AsyncSession) -> None:
    """Updates recording schedule from preset or JSON."""
    settings = await set_recording_schedule(db_session, "VZL-CAM-TEST1", "business_hours")
    sched = WeeklySchedule.from_spec(settings.schedule_json)
    assert sched == WeeklySchedule.business_hours()


@pytest.mark.asyncio
async def test_set_recording_audio(db_session: AsyncSession) -> None:
    """Toggles audio and rejects enabling audio on cameras lacking capability."""
    # Camera with audio capability
    settings = await set_recording_audio(db_session, "VZL-CAM-TEST1", enabled=True)
    assert settings.audio_enabled is True

    settings = await set_recording_audio(db_session, "VZL-CAM-TEST1", enabled=False)
    assert settings.audio_enabled is False

    # Camera explicitly missing audio capability
    with pytest.raises(AudioNotSupportedError, match="does not support audio"):
        await set_recording_audio(db_session, "VZL-CAM-NOAUDIO", enabled=True)


@pytest.mark.asyncio
async def test_set_recording_retention(db_session: AsyncSession) -> None:
    """Sets retention days and max_gb, validating non-negative constraints."""
    settings = await set_recording_retention(db_session, "VZL-CAM-TEST1", days=30, max_gb=500)
    assert settings.retention_days == 30
    assert settings.retention_max_gb == 500

    with pytest.raises(ValueError, match="Retention days must be positive"):
        await set_recording_retention(db_session, "VZL-CAM-TEST1", days=-5, max_gb=None)

    with pytest.raises(ValueError, match="Retention max_gb must be positive"):
        await set_recording_retention(db_session, "VZL-CAM-TEST1", days=10, max_gb=0)


@pytest.mark.asyncio
async def test_should_record_now(db_session: AsyncSession) -> None:
    """Accurately evaluates whether recording should be active based on mode and schedule."""
    # 1. Off mode
    await set_recording_mode(db_session, "VZL-CAM-TEST1", RecordingMode.OFF)
    assert await should_record_now(db_session, "VZL-CAM-TEST1") is False

    # 2. Continuous mode
    await set_recording_mode(db_session, "VZL-CAM-TEST1", RecordingMode.CONTINUOUS)
    assert await should_record_now(db_session, "VZL-CAM-TEST1") is True

    # 3. Event mode (circular rolling buffer)
    await set_recording_mode(db_session, "VZL-CAM-TEST1", RecordingMode.EVENT)
    assert await should_record_now(db_session, "VZL-CAM-TEST1") is True

    # 4. Scheduled mode
    await set_recording_mode(db_session, "VZL-CAM-TEST1", RecordingMode.SCHEDULED)
    await set_recording_schedule(db_session, "VZL-CAM-TEST1", "business_hours")

    # Monday 10:00 UTC (inside business hours)
    mon_10 = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)
    assert await should_record_now(db_session, "VZL-CAM-TEST1", now=mon_10, tz_name="UTC") is True

    # Monday 22:00 UTC (outside business hours)
    mon_22 = datetime(2026, 11, 2, 22, 0, 0, tzinfo=UTC)
    assert await should_record_now(db_session, "VZL-CAM-TEST1", now=mon_22, tz_name="UTC") is False
