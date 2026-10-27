"""Time and timezone utilities for VizenLink NVR."""

import logging
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

import tzlocal

logger = logging.getLogger(__name__)

UTC: timezone = UTC
EPOCH: datetime = datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)

__all__ = [
    "Clock",
    "EPOCH",
    "FakeClock",
    "InvalidTimezone",
    "SystemClock",
    "UTC",
    "default_site_zone_name",
    "format_local",
    "from_epoch_us",
    "local_day_bounds_utc",
    "to_epoch_us",
    "utc_now",
    "validate_zone",
]


class Clock(Protocol):
    """Protocol for abstract clock providing UTC now."""

    def now(self) -> datetime: ...


class SystemClock:
    """Default system clock providing real UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Controllable clock for deterministic tests."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None or start.tzinfo.utcoffset(start) is None:
            raise ValueError("FakeClock requires an aware datetime")
        self._current: datetime = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current += delta

    def set(self, dt: datetime) -> None:
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ValueError("FakeClock requires an aware datetime")
        self._current = dt.astimezone(UTC)


def utc_now() -> datetime:
    """Return current aware UTC datetime."""
    return datetime.now(UTC)


def to_epoch_us(dt: datetime) -> int:
    """Convert aware datetime to integer epoch microseconds using integer arithmetic."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Naive datetime is not permitted; provide an aware datetime")
    dt_utc = dt.astimezone(UTC)
    return (dt_utc - EPOCH) // timedelta(microseconds=1)


def from_epoch_us(us: int) -> datetime:
    """Convert integer epoch microseconds to aware UTC datetime."""
    return EPOCH + timedelta(microseconds=us)


class InvalidTimezone(ValueError):
    """Raised when an invalid IANA timezone string is supplied."""

    pass


def validate_zone(name: str) -> ZoneInfo:
    """Validate and return ZoneInfo object or raise InvalidTimezone."""
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise InvalidTimezone(f"Invalid timezone: {name}") from exc


def default_site_zone_name() -> str:
    """Get the host system IANA timezone name or fall back to UTC."""
    try:
        name = tzlocal.get_localzone_name()
        if name:
            validate_zone(name)
            return name
    except Exception as exc:
        logger.debug("Could not resolve local timezone name, using UTC: %s", exc)
    return "UTC"


def format_local(dt: datetime, zone: ZoneInfo) -> str:
    """Format aware datetime in given zone e.g. '2026-11-01 01:30:00 EDT (-04:00)'."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Naive datetime is not permitted; provide an aware datetime")
    local_dt = dt.astimezone(zone)
    offset = local_dt.strftime("%z")
    if len(offset) == 5:
        offset_fmt = f"({offset[:3]}:{offset[3:]})"
    elif offset:
        offset_fmt = f"({offset})"
    else:
        offset_fmt = "(+00:00)"

    tz_name = local_dt.strftime("%Z")
    time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
    if tz_name:
        return f"{time_str} {tz_name} {offset_fmt}"
    return f"{time_str} {offset_fmt}"


def local_day_bounds_utc(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Calculate the UTC start and end bounds of a local calendar day."""

    def _resolve_midnight(d: date) -> datetime:
        dt = datetime.combine(d, time(0, 0, 0), tzinfo=zone)
        dt_utc = dt.astimezone(UTC)
        while dt_utc.astimezone(zone).date() < d:
            dt_utc += timedelta(minutes=1)
        return dt_utc

    start_utc = _resolve_midnight(day)
    end_utc = _resolve_midnight(day + timedelta(days=1))
    return (start_utc, end_utc)
