"""Unit tests for WeeklySchedule and timezone/DST active window evaluation."""

from __future__ import annotations

from datetime import datetime

import pytest

from vizenlink_nvr.services.schedule import WeeklySchedule
from vizenlink_nvr.timeutil import UTC


def test_presets_evaluation() -> None:
    """Built-in presets initialize expected active windows."""
    always = WeeklySchedule.always()
    never = WeeklySchedule.never()
    business = WeeklySchedule.business_hours(start_hour=9, end_hour=17)
    weekdays = WeeklySchedule.weekdays()
    weekends = WeeklySchedule.weekends()

    # Monday 10:00 UTC (weekday, business hours)
    mon_10 = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)
    assert always.is_active_at(mon_10) is True
    assert never.is_active_at(mon_10) is False
    assert business.is_active_at(mon_10) is True
    assert weekdays.is_active_at(mon_10) is True
    assert weekends.is_active_at(mon_10) is False

    # Monday 20:00 UTC (weekday, outside business hours)
    mon_20 = datetime(2026, 11, 2, 20, 0, 0, tzinfo=UTC)
    assert always.is_active_at(mon_20) is True
    assert never.is_active_at(mon_20) is False
    assert business.is_active_at(mon_20) is False
    assert weekdays.is_active_at(mon_20) is True
    assert weekends.is_active_at(mon_20) is False

    # Saturday 12:00 UTC (weekend)
    sat_12 = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
    assert always.is_active_at(sat_12) is True
    assert never.is_active_at(sat_12) is False
    assert business.is_active_at(sat_12) is False
    assert weekdays.is_active_at(sat_12) is False
    assert weekends.is_active_at(sat_12) is True


def test_schedule_timezone_conversion() -> None:
    """Schedule correctly evaluates active windows in target timezone."""
    # Business hours: 09:00 - 17:00 local time
    sched = WeeklySchedule.business_hours(start_hour=9, end_hour=17)

    # 14:00 UTC on Monday
    # In New York (EDT, UTC-4), 14:00 UTC = 10:00 AM (Active)
    # In Tokyo (JST, UTC+9), 14:00 UTC = 23:00 (Inactive)
    dt_utc = datetime(2026, 10, 19, 14, 0, 0, tzinfo=UTC)
    assert sched.is_active_at(dt_utc, "America/New_York") is True
    assert sched.is_active_at(dt_utc, "Asia/Tokyo") is False


def test_schedule_dst_transition() -> None:
    """Schedule evaluation remains accurate across Daylight Saving Time shifts."""
    sched = WeeklySchedule.business_hours(start_hour=9, end_hour=17)
    ny_tz = "America/New_York"

    # US DST ends on Sunday, Nov 1, 2026 at 02:00 AM.
    # Before switch: Friday, Oct 30, 2026 (EDT, UTC-4)
    # 10:00 AM EDT = 14:00 UTC
    before_dst_utc = datetime(2026, 10, 30, 14, 0, 0, tzinfo=UTC)
    assert sched.is_active_at(before_dst_utc, ny_tz) is True

    # After switch: Monday, Nov 2, 2026 (EST, UTC-5)
    # 10:00 AM EST = 15:00 UTC
    after_dst_utc = datetime(2026, 11, 2, 15, 0, 0, tzinfo=UTC)
    assert sched.is_active_at(after_dst_utc, ny_tz) is True

    # Check 14:00 UTC on Nov 2 (which is 09:00 AM EST - start of business hours)
    assert sched.is_active_at(datetime(2026, 11, 2, 14, 0, 0, tzinfo=UTC), ny_tz) is True

    # Check 13:00 UTC on Nov 2 (which is 08:00 AM EST - before business hours)
    assert sched.is_active_at(datetime(2026, 11, 2, 13, 0, 0, tzinfo=UTC), ny_tz) is False


def test_schedule_serialization_roundtrip() -> None:
    """Schedule serializes to JSON and deserializes back identically."""
    original = WeeklySchedule.business_hours()
    json_str = original.to_json()
    reconstructed = WeeklySchedule.from_spec(json_str)
    assert original == reconstructed

    # Test from_dict
    d = original.to_dict()
    assert WeeklySchedule.from_dict(d) == original


def test_from_spec_variations() -> None:
    """from_spec parses preset strings, dicts, and raw matrices."""
    assert WeeklySchedule.from_spec("always") == WeeklySchedule.always()
    assert WeeklySchedule.from_spec("never") == WeeklySchedule.never()
    assert WeeklySchedule.from_spec("weekdays") == WeeklySchedule.weekdays()
    assert WeeklySchedule.from_spec("weekends") == WeeklySchedule.weekends()
    assert WeeklySchedule.from_spec("business_hours") == WeeklySchedule.business_hours()

    # Dict with preset
    assert WeeklySchedule.from_spec({"preset": "weekdays"}) == WeeklySchedule.weekdays()

    # Invalid string raises ValueError
    with pytest.raises(ValueError, match="Unknown schedule preset"):
        WeeklySchedule.from_spec("nonexistent_preset")


def test_set_hour_and_set_day() -> None:
    """set_hour and set_day mutate schedule grid accurately."""
    sched = WeeklySchedule.never()
    sched.set_hour(0, 10, True)  # Mon 10:00
    assert sched.is_active_at(datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)) is True
    assert sched.is_active_at(datetime(2026, 11, 2, 11, 0, 0, tzinfo=UTC)) is False

    sched.set_day(1, True)  # Tuesday all day
    for h in range(24):
        assert sched.is_active_at(datetime(2026, 11, 3, h, 0, 0, tzinfo=UTC)) is True
