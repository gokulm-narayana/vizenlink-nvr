"""Unit tests for timeutil functions, timezone handling, and DST transitions."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from vizenlink_nvr.timeutil import (
    EPOCH,
    UTC,
    FakeClock,
    InvalidTimezone,
    SystemClock,
    default_site_zone_name,
    format_local,
    from_epoch_us,
    local_day_bounds_utc,
    to_epoch_us,
    utc_now,
    validate_zone,
)


@pytest.mark.parametrize(
    ("zone_name", "test_date", "expected_hours"),
    [
        ("America/New_York", date(2026, 3, 8), 23.0),
        ("America/New_York", date(2026, 6, 1), 24.0),
        ("America/New_York", date(2026, 11, 1), 25.0),
        ("Europe/London", date(2026, 3, 29), 23.0),
        ("Europe/London", date(2026, 10, 25), 25.0),
        ("Australia/Lord_Howe", date(2026, 4, 5), 24.5),
        ("Australia/Lord_Howe", date(2026, 10, 4), 23.5),
        ("America/Santiago", date(2026, 4, 4), 25.0),
        ("America/Santiago", date(2026, 9, 6), 23.0),
    ],
)
def test_local_day_bounds_dst_transitions(zone_name: str, test_date: date, expected_hours: float) -> None:
    """Verify local day bounds handle 23h, 24h, 25h, and 30-min DST transitions correctly."""
    zone = ZoneInfo(zone_name)
    start_utc, end_utc = local_day_bounds_utc(test_date, zone)
    duration_hours = (end_utc - start_utc) / timedelta(hours=1)
    assert duration_hours == expected_hours
    assert start_utc.tzinfo == UTC
    assert end_utc.tzinfo == UTC


def test_format_local_dst_fall_back_and_spring_forward() -> None:
    """Verify format_local renders wall clock, timezone abbreviation, and offset correctly."""
    ny = ZoneInfo("America/New_York")

    # Fall-back: Two distinct UTC instants render the same wall clock with different offsets
    t_edt = datetime(2026, 11, 1, 5, 30, 0, tzinfo=UTC)
    t_est = datetime(2026, 11, 1, 6, 30, 0, tzinfo=UTC)
    assert format_local(t_edt, ny) == "2026-11-01 01:30:00 EDT (-04:00)"
    assert format_local(t_est, ny) == "2026-11-01 01:30:00 EST (-05:00)"

    # Spring-forward: Jump across 2 AM
    t_before = datetime(2026, 3, 8, 6, 59, 59, tzinfo=UTC)
    t_after = datetime(2026, 3, 8, 7, 0, 0, tzinfo=UTC)
    assert format_local(t_before, ny) == "2026-03-08 01:59:59 EST (-05:00)"
    assert format_local(t_after, ny) == "2026-03-08 03:00:00 EDT (-04:00)"

    # Naive rejection
    naive_dt = datetime(2026, 1, 1, 0, 0, 0)  # noqa: DTZ001
    with pytest.raises(ValueError, match="Naive datetime"):
        format_local(naive_dt, ny)


def test_epoch_conversions_and_microseconds() -> None:
    """Verify microsecond precision and epoch conversions."""
    assert to_epoch_us(EPOCH) == 0
    assert from_epoch_us(0) == EPOCH

    dt_us = datetime(2026, 10, 27, 12, 34, 56, 999999, tzinfo=UTC)
    us = to_epoch_us(dt_us)
    assert from_epoch_us(us) == dt_us

    # Naive input raises
    with pytest.raises(ValueError, match="Naive datetime"):
        to_epoch_us(datetime(2026, 1, 1, 0, 0, 0))  # noqa: DTZ001


def test_zone_validation_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify validate_zone and fallback default."""
    assert isinstance(validate_zone("Europe/London"), ZoneInfo)
    with pytest.raises(InvalidTimezone):
        validate_zone("Not/AZone")

    # When tzlocal fails, fall back to UTC
    def broken_getzone() -> str:
        raise RuntimeError("Host timezone broken")

    monkeypatch.setattr("tzlocal.get_localzone_name", broken_getzone)
    assert default_site_zone_name() == "UTC"


def test_clocks() -> None:
    """Verify SystemClock and FakeClock advance and set."""
    sys_clock = SystemClock()
    assert sys_clock.now().tzinfo == UTC

    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    fake = FakeClock(start)
    assert fake.now() == start

    fake.advance(timedelta(hours=2))
    assert fake.now() == start + timedelta(hours=2)

    new_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    fake.set(new_time)
    assert fake.now() == new_time

    assert utc_now().tzinfo == UTC
