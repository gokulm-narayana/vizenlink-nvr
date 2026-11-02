"""Weekly recording schedule representation and active window evaluator."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from vizenlink_nvr.timeutil import UTC

DAYS_PER_WEEK: int = 7
HOURS_PER_DAY: int = 24
DAY_NAMES: list[str] = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
DAY_NAME_TO_INDEX: dict[str, int] = {name: i for i, name in enumerate(DAY_NAMES)}
for i, name in enumerate(DAY_NAMES):
    DAY_NAME_TO_INDEX[name[:3]] = i


class WeeklySchedule:
    """7 days x 24 hours weekly recording schedule matrix."""

    def __init__(self, grid: list[list[bool]] | None = None) -> None:
        if grid is not None:
            if len(grid) != DAYS_PER_WEEK or any(len(day) != HOURS_PER_DAY for day in grid):
                raise ValueError("Grid must be exactly 7 days x 24 hours")
            self._grid = [[bool(hour) for hour in day] for day in grid]
        else:
            self._grid = [[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)]

    @classmethod
    def always(cls) -> WeeklySchedule:
        """Schedule active 24/7 all 7 days."""
        return cls([[True] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)])

    @classmethod
    def never(cls) -> WeeklySchedule:
        """Schedule inactive at all times."""
        return cls([[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)])

    @classmethod
    def weekdays(cls) -> WeeklySchedule:
        """Schedule active 24 hours Monday through Friday."""
        grid = [[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)]
        for d in range(5):
            grid[d] = [True] * HOURS_PER_DAY
        return cls(grid)

    @classmethod
    def weekends(cls) -> WeeklySchedule:
        """Schedule active 24 hours Saturday and Sunday."""
        grid = [[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)]
        grid[5] = [True] * HOURS_PER_DAY
        grid[6] = [True] * HOURS_PER_DAY
        return cls(grid)

    @classmethod
    def business_hours(cls, start_hour: int = 9, end_hour: int = 17) -> WeeklySchedule:
        """Schedule active Monday through Friday from start_hour to end_hour inclusive."""
        grid = [[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)]
        for d in range(5):
            for h in range(start_hour, min(end_hour + 1, HOURS_PER_DAY)):
                grid[d][h] = True
        return cls(grid)

    @classmethod
    def nights(cls, start_hour: int = 18, end_hour: int = 6) -> WeeklySchedule:
        """Schedule active overnight (start_hour to 23:59 and 00:00 to end_hour) every day."""
        grid = [[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)]
        for d in range(DAYS_PER_WEEK):
            for h in range(start_hour, HOURS_PER_DAY):
                grid[d][h] = True
            for h in range(0, min(end_hour + 1, HOURS_PER_DAY)):
                grid[d][h] = True
        return cls(grid)

    @classmethod
    def from_preset(cls, name: str) -> WeeklySchedule:
        """Construct schedule from preset name."""
        key = name.strip().lower()
        if key in ("always", "continuous", "24/7", "all"):
            return cls.always()
        if key in ("never", "none", "off"):
            return cls.never()
        if key in ("weekdays", "workdays"):
            return cls.weekdays()
        if key in ("weekends", "weekend"):
            return cls.weekends()
        if key in ("business", "business_hours", "office"):
            return cls.business_hours()
        if key in ("nights", "overnight", "night"):
            return cls.nights()
        raise ValueError(f"Unknown schedule preset: {name}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeeklySchedule:
        """Construct schedule from dictionary structure."""
        if "preset" in data:
            return cls.from_preset(str(data["preset"]))

        if "days" in data and isinstance(data["days"], list):
            return cls(data["days"])

        grid = [[False] * HOURS_PER_DAY for _ in range(DAYS_PER_WEEK)]
        matched_any = False
        for day_name, hours in data.items():
            key = day_name.strip().lower()
            if key in DAY_NAME_TO_INDEX:
                matched_any = True
                idx = DAY_NAME_TO_INDEX[key]
                if isinstance(hours, list):
                    if len(hours) == HOURS_PER_DAY:
                        grid[idx] = [bool(h) for h in hours]
                    else:
                        for h in hours:
                            if isinstance(h, int) and 0 <= h < HOURS_PER_DAY:
                                grid[idx][h] = True

        if not matched_any:
            raise ValueError(f"No valid day keys found in schedule dictionary: {list(data.keys())}")
        return cls(grid)

    @classmethod
    def from_spec(cls, spec: WeeklySchedule | str | dict[str, Any] | list[Any]) -> WeeklySchedule:
        """Construct schedule from preset name, JSON string, dictionary, or matrix."""
        if isinstance(spec, cls):
            return spec

        if isinstance(spec, str):
            clean = spec.strip()
            # If preset name without JSON brackets
            if not clean.startswith(("{", "[")):
                return cls.from_preset(clean)
            try:
                parsed = json.loads(clean)
                return cls.from_spec(parsed)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid schedule JSON: {exc}") from exc

        if isinstance(spec, dict):
            return cls.from_dict(spec)

        if isinstance(spec, list):
            if len(spec) == DAYS_PER_WEEK and all(isinstance(row, list) for row in spec):
                return cls(spec)
            raise ValueError(f"Schedule list must be 7 days x 24 hours, got length {len(spec)}")

        raise ValueError(f"Unsupported schedule specification type: {type(spec)}")

    def set_hour(self, weekday: int, hour: int, active: bool = True) -> None:
        """Set active state for specific weekday (0=Mon..6=Sun) and hour (0..23)."""
        if not (0 <= weekday < DAYS_PER_WEEK):
            raise ValueError(f"Weekday must be 0..{DAYS_PER_WEEK - 1}, got {weekday}")
        if not (0 <= hour < HOURS_PER_DAY):
            raise ValueError(f"Hour must be 0..{HOURS_PER_DAY - 1}, got {hour}")
        self._grid[weekday][hour] = active

    def set_day(self, weekday: int, active: bool = True) -> None:
        """Set all 24 hours of a specific weekday (0=Mon..6=Sun)."""
        if not (0 <= weekday < DAYS_PER_WEEK):
            raise ValueError(f"Weekday must be 0..{DAYS_PER_WEEK - 1}, got {weekday}")
        self._grid[weekday] = [active] * HOURS_PER_DAY

    def is_active_at(self, dt: datetime, tz_name: str = "UTC") -> bool:
        """Evaluate whether the schedule is active at dt in the given timezone."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        try:
            zone = ZoneInfo(tz_name)
        except Exception as exc:
            raise ValueError(f"Invalid timezone: {tz_name}") from exc

        local_dt = dt.astimezone(zone)
        weekday = local_dt.weekday()
        hour = local_dt.hour
        return self._grid[weekday][hour]

    def to_dict(self) -> dict[str, list[bool]]:
        """Serialize schedule to dictionary keyed by day name."""
        return {name: list(self._grid[i]) for i, name in enumerate(DAY_NAMES)}

    def to_json(self) -> str:
        """Serialize schedule to compact JSON string."""
        return json.dumps(self.to_dict())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WeeklySchedule):
            return False
        return self._grid == other._grid
