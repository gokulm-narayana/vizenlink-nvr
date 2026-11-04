"""Unit tests for event notifications, unread counters, and filter logic (EVT-02, EVT-03)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class EventFilterEngine:
    """Helper class encapsulating client-side or service-side event filtering logic."""

    @staticmethod
    def filter_events(
        events: list[dict[str, Any]],
        camera_serial: str | None = None,
        event_type: str | None = None,
        is_locked: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        filtered = []
        for evt in events:
            if camera_serial and evt.get("camera_serial") != camera_serial:
                continue
            if event_type and evt.get("event_type") != event_type:
                continue
            if is_locked is not None and evt.get("is_locked") != is_locked:
                continue
            evt_time = evt.get("start_time")
            if isinstance(evt_time, str):
                evt_time = datetime.fromisoformat(evt_time)
            if start_time and evt_time and evt_time < start_time:
                continue
            if end_time and evt_time and evt_time > end_time:
                continue
            filtered.append(evt)
        return filtered

    @staticmethod
    def compute_unread_count(events: list[dict[str, Any]], read_ids: set[int]) -> int:
        return sum(1 for e in events if e.get("id") not in read_ids)


def test_unread_event_counter_and_mark_read():
    events = [
        {"id": 1, "camera_serial": "CAM-1", "event_type": "motion"},
        {"id": 2, "camera_serial": "CAM-1", "event_type": "tamper"},
        {"id": 3, "camera_serial": "CAM-2", "event_type": "line_crossing"},
    ]
    read_ids: set[int] = set()

    # Initial state: all 3 are unread
    assert EventFilterEngine.compute_unread_count(events, read_ids) == 3

    # Mark event 1 as read
    read_ids.add(1)
    assert EventFilterEngine.compute_unread_count(events, read_ids) == 2

    # Mark event 2 and 3 as read
    read_ids.update([2, 3])
    assert EventFilterEngine.compute_unread_count(events, read_ids) == 0

    # New incoming event 4 arrives
    events.append({"id": 4, "camera_serial": "CAM-1", "event_type": "person"})
    assert EventFilterEngine.compute_unread_count(events, read_ids) == 1


def test_event_filtering_by_type_and_camera():
    events = [
        {"id": 1, "camera_serial": "CAM-1", "event_type": "motion", "is_locked": False},
        {"id": 2, "camera_serial": "CAM-1", "event_type": "line_crossing", "is_locked": True},
        {"id": 3, "camera_serial": "CAM-2", "event_type": "motion", "is_locked": True},
        {"id": 4, "camera_serial": "CAM-2", "event_type": "tamper", "is_locked": False},
    ]

    # Filter by camera_serial
    res = EventFilterEngine.filter_events(events, camera_serial="CAM-1")
    assert len(res) == 2
    assert {e["id"] for e in res} == {1, 2}

    # Filter by event_type
    res = EventFilterEngine.filter_events(events, event_type="motion")
    assert len(res) == 2
    assert {e["id"] for e in res} == {1, 3}

    # Filter by is_locked
    res = EventFilterEngine.filter_events(events, is_locked=True)
    assert len(res) == 2
    assert {e["id"] for e in res} == {2, 3}

    # Combined filter
    res = EventFilterEngine.filter_events(events, camera_serial="CAM-2", is_locked=True)
    assert len(res) == 1
    assert res[0]["id"] == 3


def test_event_filtering_by_time_window():
    t0 = datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 4, 10, 30, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 4, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 11, 4, 11, 30, 0, tzinfo=UTC)

    events = [
        {"id": 1, "start_time": t0},
        {"id": 2, "start_time": t1},
        {"id": 3, "start_time": t2},
        {"id": 4, "start_time": t3},
    ]

    # Filter >= t1
    res = EventFilterEngine.filter_events(events, start_time=t1)
    assert len(res) == 3
    assert {e["id"] for e in res} == {2, 3, 4}

    # Filter between t1 and t2
    res = EventFilterEngine.filter_events(events, start_time=t1, end_time=t2)
    assert len(res) == 2
    assert {e["id"] for e in res} == {2, 3}
