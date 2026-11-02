"""Unit tests for MediaMTX hook environment variables and segment path timestamp parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vizenlink_nvr.services.indexer import (
    parse_mtx_path,
    parse_segment_metadata,
    parse_start_time_from_path,
)
from vizenlink_nvr.timeutil import UTC


def test_parse_mtx_path_variations() -> None:
    """parse_mtx_path extracts camera serial (uppercase) and stream role correctly."""
    assert parse_mtx_path("cam/vzl-cam-001/main") == ("VZL-CAM-001", "main")
    assert parse_mtx_path("cam/vzl-cam-002/sub") == ("VZL-CAM-002", "sub")
    assert parse_mtx_path("/cam/vzl-cam-003/main/") == ("VZL-CAM-003", "main")
    assert parse_mtx_path("vzl-cam-004/main") == ("VZL-CAM-004", "main")
    assert parse_mtx_path("vzl-cam-005") == ("VZL-CAM-005", "main")
    assert parse_mtx_path("") == ("UNKNOWN", "main")


def test_parse_start_time_from_path_variations(tmp_path: Path) -> None:
    """parse_start_time_from_path parses various ISO-8601 and MediaMTX timestamp formats."""
    # Format with T and hyphens
    p1 = Path("/rec/cam1/2026-11-02T13-05-00Z-123456.mp4")
    assert parse_start_time_from_path(p1) == datetime(2026, 11, 2, 13, 5, 0, tzinfo=UTC)

    # Format with underscore and colons/hyphens
    p2 = Path("/rec/cam1/2026-11-02_13-05-00-123456_+0000.mp4")
    assert parse_start_time_from_path(p2) == datetime(2026, 11, 2, 13, 5, 0, tzinfo=UTC)

    # D-31 format: YYYY-MM-DDTHH-MM-SSZ.mp4
    p3 = Path("/rec/cam1/2026-10-28T16-51-46Z.mp4")
    assert parse_start_time_from_path(p3) == datetime(2026, 10, 28, 16, 51, 46, tzinfo=UTC)

    # Fallback to mtime if no pattern matched
    non_date_file = tmp_path / "custom_segment.mp4"
    non_date_file.write_bytes(b"x" * 2000)
    parsed_fallback = parse_start_time_from_path(non_date_file)
    assert parsed_fallback.tzinfo == UTC
    assert parsed_fallback.year >= 2026


def test_parse_segment_metadata(tmp_path: Path) -> None:
    """parse_segment_metadata integrates path, timestamps, durations, and sizes."""
    # Create mock video file larger than 1024 bytes
    seg_file = tmp_path / "2026-11-02T14-00-00Z-000000.mp4"
    seg_file.write_bytes(b"\x00" * 4096)

    env = {
        "MTX_PATH": "cam/vzl-cam-100/main",
        "MTX_SEGMENT_PATH": str(seg_file),
        "MTX_SEGMENT_DURATION": "60.05",
    }

    meta = parse_segment_metadata(env)
    assert meta.camera_serial == "VZL-CAM-100"
    assert meta.stream_type == "main"
    assert meta.file_path == seg_file.resolve()
    assert meta.start_time == datetime(2026, 11, 2, 14, 0, 0, tzinfo=UTC)
    assert meta.duration_seconds == 60.05
    assert meta.file_size_bytes == 4096
    assert meta.status == "active"


def test_parse_segment_metadata_truncated(tmp_path: Path) -> None:
    """Segments smaller than 1024 bytes are flagged as truncated."""
    truncated_file = tmp_path / "2026-11-02T14-00-00Z-000000.mp4"
    truncated_file.write_bytes(b"\x00" * 500)  # < 1024 bytes

    env = {
        "MTX_PATH": "cam/vzl-cam-100/main",
        "MTX_SEGMENT_PATH": str(truncated_file),
        "MTX_SEGMENT_DURATION": "10.0",
    }

    meta = parse_segment_metadata(env)
    assert meta.file_size_bytes == 500
    assert meta.status == "truncated"
