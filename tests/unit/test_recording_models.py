"""Unit tests for recording settings, segment catalog, and storage models."""

from __future__ import annotations

from datetime import datetime

from vizenlink_nvr.db.models import Camera, RecordingSettings, Segment, StorageSettings
from vizenlink_nvr.timeutil import UTC


def test_recording_settings_instantiation() -> None:
    """Test RecordingSettings model fields, defaults, and relationships."""
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    settings = RecordingSettings(
        camera_serial="VZL-CAM-001",
        mode="continuous",
        schedule_json="{}",
        audio_enabled=True,
        retention_days=14,
        retention_max_gb=100,
        created_at=now,
        updated_at=now,
    )
    assert settings.camera_serial == "VZL-CAM-001"
    assert settings.mode == "continuous"
    assert settings.schedule_json == "{}"
    assert settings.audio_enabled is True
    assert settings.retention_days == 14
    assert settings.retention_max_gb == 100
    assert settings.created_at == now
    assert settings.updated_at == now


def test_segment_model_instantiation() -> None:
    """Test Segment model attributes, defaults, and timestamps."""
    start = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 2, 12, 1, 0, tzinfo=UTC)
    created = datetime(2026, 11, 2, 12, 1, 1, tzinfo=UTC)

    segment = Segment(
        camera_serial="VZL-CAM-001",
        stream_type="main",
        file_path="/data/recordings/VZL-CAM-001/2026/11/02/2026-11-02T12-00-00Z.mp4",
        start_time=start,
        end_time=end,
        duration_seconds=60.0,
        file_size_bytes=15_000_000,
        status="active",
        is_protected=False,
        protection_reason=None,
        created_at=created,
    )

    assert segment.camera_serial == "VZL-CAM-001"
    assert segment.stream_type == "main"
    assert segment.file_path.endswith(".mp4")
    assert segment.start_time == start
    assert segment.end_time == end
    assert segment.duration_seconds == 60.0
    assert segment.file_size_bytes == 15_000_000
    assert segment.status == "active"
    assert segment.is_protected is False
    assert segment.protection_reason is None
    assert segment.created_at == created


def test_storage_settings_model_instantiation() -> None:
    """Test StorageSettings model defaults and values."""
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    storage = StorageSettings(
        id=1,
        storage_path="/mnt/recordings",
        allow_system_disk=False,
        reserve_bytes=10 * 1024 * 1024 * 1024,
        created_at=now,
        updated_at=now,
    )
    assert storage.id == 1
    assert storage.storage_path == "/mnt/recordings"
    assert storage.allow_system_disk is False
    assert storage.reserve_bytes == 10737418240
    assert storage.created_at == now
    assert storage.updated_at == now


def test_camera_recording_relationships() -> None:
    """Test Camera model relationships to RecordingSettings and Segments."""
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    camera = Camera(
        serial="VZL-CAM-REL",
        host="127.0.0.1",
        https_port=443,
        tls_fingerprint_sha256="abc",
        added_at=now,
        host_updated_at=now,
    )
    rec_settings = RecordingSettings(
        camera_serial="VZL-CAM-REL",
        mode="scheduled",
        created_at=now,
        updated_at=now,
    )
    camera.recording_settings = rec_settings

    seg = Segment(
        camera_serial="VZL-CAM-REL",
        stream_type="main",
        file_path="/path/test.mp4",
        start_time=now,
        end_time=now,
        duration_seconds=60.0,
        file_size_bytes=1000,
        status="active",
        created_at=now,
    )
    camera.segments.append(seg)

    assert camera.recording_settings.mode == "scheduled"
    assert len(camera.segments) == 1
    assert camera.segments[0].file_path == "/path/test.mp4"

