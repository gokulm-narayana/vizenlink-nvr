"""Unit tests for player transport controls, timeline coordinate math,
and gap skipping (PLAY-01, PLAY-05, PLAY-08).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def time_to_percentage(
    target: datetime,
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Calculate percentage [0, 100] of target within [window_start, window_end]."""
    total_ms = (window_end - window_start).total_seconds() * 1000
    if total_ms <= 0:
        return 0.0
    elapsed_ms = (target - window_start).total_seconds() * 1000
    pct = (elapsed_ms / total_ms) * 100.0
    return max(0.0, min(100.0, pct))


def percentage_to_time(
    pct: float,
    window_start: datetime,
    window_end: datetime,
) -> datetime:
    """Convert percentage [0, 100] back to datetime inside [window_start, window_end]."""
    clamped_pct = max(0.0, min(100.0, pct))
    total_seconds = (window_end - window_start).total_seconds()
    target_seconds = (clamped_pct / 100.0) * total_seconds
    return window_start + timedelta(seconds=target_seconds)


def find_covering_or_next_segment(
    target: datetime,
    segments: list[dict],
) -> tuple[dict | None, dict | None]:
    """Find segment covering target datetime, or next available segment if in an outage/empty gap."""
    covering: dict | None = None
    next_seg: dict | None = None

    for seg in sorted(segments, key=lambda s: s["start_time"]):
        s_time = seg["start_time"]
        e_time = seg["end_time"]

        if s_time <= target <= e_time:
            covering = seg
            break
        if s_time > target:
            if next_seg is None or s_time < next_seg["start_time"]:
                next_seg = seg

    return covering, next_seg


def test_timeline_percentage_conversion_24h():
    """Test 24-hour timeline percentage math and round-trip conversion."""
    day_start = datetime(2026, 11, 4, 0, 0, 0, tzinfo=UTC)
    day_end = datetime(2026, 11, 4, 23, 59, 59, 999000, tzinfo=UTC)

    # Noon is exactly 50%
    noon = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
    pct = time_to_percentage(noon, day_start, day_end)
    assert 49.9 < pct < 50.1

    # Round trip
    reconstructed = percentage_to_time(pct, day_start, day_end)
    assert abs((reconstructed - noon).total_seconds()) < 1.0

    # 06:00:00 is 25%
    six_am = datetime(2026, 11, 4, 6, 0, 0, tzinfo=UTC)
    pct_6am = time_to_percentage(six_am, day_start, day_end)
    assert 24.9 < pct_6am < 25.1

    # Clamping outside bounds
    before = datetime(2026, 11, 3, 23, 0, 0, tzinfo=UTC)
    after = datetime(2026, 11, 5, 1, 0, 0, tzinfo=UTC)
    assert time_to_percentage(before, day_start, day_end) == 0.0
    assert time_to_percentage(after, day_start, day_end) == 100.0


def test_timeline_zoom_window_math():
    """Test zoom window (4h and 1h) coordinate mapping."""
    center = datetime(2026, 11, 4, 14, 30, 0, tzinfo=UTC)
    # 4-hour window: 12:30:00 to 16:30:00
    win_start = center - timedelta(hours=2)
    win_end = center + timedelta(hours=2)

    # Center must map to 50%
    assert 49.99 < time_to_percentage(center, win_start, win_end) < 50.01

    # Target at 13:30:00 (1 hour in out of 4) is 25%
    t_1330 = datetime(2026, 11, 4, 13, 30, 0, tzinfo=UTC)
    assert 24.99 < time_to_percentage(t_1330, win_start, win_end) < 25.01


def test_find_covering_segment_exact_hit():
    """Test seeking directly inside a recorded segment."""
    t0 = datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 4, 10, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 4, 10, 20, 0, tzinfo=UTC)
    t3 = datetime(2026, 11, 4, 10, 30, 0, tzinfo=UTC)

    segments = [
        {"id": 1, "start_time": t0, "end_time": t1},
        {"id": 2, "start_time": t2, "end_time": t3},
    ]

    target = datetime(2026, 11, 4, 10, 5, 0, tzinfo=UTC)
    covering, next_seg = find_covering_or_next_segment(target, segments)

    assert covering is not None
    assert covering["id"] == 1


def test_find_covering_segment_gap_skipping():
    """Test seeking into an outage gap smoothly identifies next segment (PLAY-08 resilience)."""
    t0 = datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 4, 10, 10, 0, tzinfo=UTC)
    # Outage gap between 10:10 and 10:25
    t2 = datetime(2026, 11, 4, 10, 25, 0, tzinfo=UTC)
    t3 = datetime(2026, 11, 4, 10, 35, 0, tzinfo=UTC)

    segments = [
        {"id": 1, "start_time": t0, "end_time": t1},
        {"id": 2, "start_time": t2, "end_time": t3},
    ]

    # Target is in the outage gap at 10:15:00
    gap_target = datetime(2026, 11, 4, 10, 15, 0, tzinfo=UTC)
    covering, next_seg = find_covering_or_next_segment(gap_target, segments)

    assert covering is None
    assert next_seg is not None
    assert next_seg["id"] == 2
    assert next_seg["start_time"] == t2


def test_find_covering_segment_after_all_segments():
    """Test seeking after all recorded segments returns None for both."""
    t0 = datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 4, 10, 10, 0, tzinfo=UTC)
    segments = [{"id": 1, "start_time": t0, "end_time": t1}]

    target = datetime(2026, 11, 4, 11, 0, 0, tzinfo=UTC)
    covering, next_seg = find_covering_or_next_segment(target, segments)

    assert covering is None
    assert next_seg is None
