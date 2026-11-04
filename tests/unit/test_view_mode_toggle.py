"""Unit tests for Simple vs Advanced view mode toggle (AUTH-06)."""

from __future__ import annotations

from vizenlink_nvr.services.live_view import (
    ADVANCED_METRIC_KEYS,
    ViewMode,
    filter_dashboard_metrics,
)


def test_view_mode_simple_filters_technical_telemetry() -> None:
    """Simple view mode omits low-level diagnostic fields (AUTH-06)."""
    full_metrics = {
        "status": "healthy",
        "total_cameras": 8,
        "active_cameras": 7,
        "db_ok": True,
        "mediamtx_ok": True,
        "reserve_bytes": 10737418240,
        "details": {"gap_count": 0, "db": "ok"},
        "mountpoint": "/var/lib/vizenlink-nvr/recordings",
    }

    filtered = filter_dashboard_metrics(full_metrics, mode=ViewMode.SIMPLE)

    # Core user-facing summary values remain
    assert filtered["status"] == "healthy"
    assert filtered["total_cameras"] == 8
    assert filtered["active_cameras"] == 7

    # Technical/diagnostic fields are omitted in Simple mode
    for key in ADVANCED_METRIC_KEYS:
        assert key not in filtered


def test_view_mode_advanced_exposes_all_telemetry() -> None:
    """Advanced view mode retains all diagnostic and hardware fields."""
    full_metrics = {
        "status": "healthy",
        "total_cameras": 8,
        "active_cameras": 7,
        "db_ok": True,
        "mediamtx_ok": True,
        "reserve_bytes": 10737418240,
        "details": {"gap_count": 0, "db": "ok"},
        "mountpoint": "/var/lib/vizenlink-nvr/recordings",
    }

    result = filter_dashboard_metrics(full_metrics, mode=ViewMode.ADVANCED)
    assert result == full_metrics
    assert result["reserve_bytes"] == 10737418240
    assert result["db_ok"] is True

