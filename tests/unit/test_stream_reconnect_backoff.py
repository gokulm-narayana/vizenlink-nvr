"""Unit tests for stream reconnect exponential backoff (REC-10)."""

from __future__ import annotations

import pytest

from vizenlink_nvr.services.watchdog import WatchdogService, get_reconnect_backoff


def test_reconnect_backoff_progression() -> None:
    """Stream reconnect follows binary exponential progression: 1s, 2s, 4s, 8s, 16s, 32s, max 60s."""
    expected = [
        (0, 1.0),
        (1, 2.0),
        (2, 4.0),
        (3, 8.0),
        (4, 16.0),
        (5, 32.0),
        (6, 60.0),  # capped at 60s (not 64s)
        (7, 60.0),
        (10, 60.0),
    ]

    for failures, expected_backoff in expected:
        actual = get_reconnect_backoff(failures)
        assert actual == pytest.approx(expected_backoff), f"Failed for failure_count={failures}"
        # Also verify through WatchdogService class interface
        assert WatchdogService.get_reconnect_backoff(failures) == pytest.approx(expected_backoff)


def test_reconnect_backoff_negative_or_zero() -> None:
    """Negative or zero failure count returns base 1.0s backoff."""
    assert get_reconnect_backoff(0) == 1.0
    assert get_reconnect_backoff(-1) == 1.0
    assert get_reconnect_backoff(-99) == 1.0


def test_reconnect_backoff_custom_bounds() -> None:
    """Custom min and max backoff parameters are honoured."""
    assert get_reconnect_backoff(0, min_backoff=0.5, max_backoff=10.0) == 0.5
    assert get_reconnect_backoff(1, min_backoff=0.5, max_backoff=10.0) == 1.0
    assert get_reconnect_backoff(4, min_backoff=0.5, max_backoff=10.0) == 8.0
    assert get_reconnect_backoff(5, min_backoff=0.5, max_backoff=10.0) == 10.0
