"""Offline alerts say "5 hours", not "300 minutes" (UI audit 2026-11-12)."""

import pytest

from vizenlink_nvr.services.alert_service import _humanize_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (20, "1 minute"),
        (8 * 60, "8 minutes"),
        (60 * 60, "1 hour"),
        (300 * 60, "5 hours"),
        (80 * 60, "1 hour 20 minutes"),
        (24 * 3600, "1 day"),
        (51 * 3600, "2 days 3 hours"),
    ],
)
def test_humanize_duration(seconds: float, expected: str) -> None:
    assert _humanize_duration(seconds) == expected
