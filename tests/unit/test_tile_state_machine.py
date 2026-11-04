"""Unit tests for tile state machine and truthful stall detection (LIVE-04)."""

from __future__ import annotations

from vizenlink_nvr.services.live_view import TileState, TileStateMachine


def test_tile_state_machine_initial_state() -> None:
    """Player begins in CONNECTING state with is_live=False."""
    sm = TileStateMachine(stall_timeout_seconds=5.0)
    assert sm.state == TileState.CONNECTING
    assert sm.is_live is False


def test_tile_state_machine_first_frame_to_live() -> None:
    """Receiving first decoded frame transitions to LIVE."""
    sm = TileStateMachine(stall_timeout_seconds=5.0)
    sm.on_first_frame(current_time=100.0)
    assert sm.state == TileState.LIVE
    assert sm.is_live is True


def test_tile_state_machine_prohibition_frozen_frame_not_live() -> None:
    """Stream stalled for > 5.0s transitions to STALLED and is_live becomes False (LIVE-04)."""
    sm = TileStateMachine(stall_timeout_seconds=5.0)
    sm.on_first_frame(current_time=100.0)
    assert sm.is_live is True

    # 4 seconds later (within timeout) -> still LIVE
    assert sm.check_staleness(current_time=104.0) == TileState.LIVE
    assert sm.is_live is True

    # 5.1 seconds later (exceeds timeout) -> must leave LIVE to STALLED
    assert sm.check_staleness(current_time=105.1) == TileState.STALLED
    assert sm.is_live is False

    # When new frame arrives -> resumes LIVE
    sm.on_frame_progress(current_time=106.0)
    assert sm.state == TileState.LIVE
    assert sm.is_live is True


def test_tile_state_machine_retry_and_offline() -> None:
    """Exceeding max retries marks the tile OFFLINE."""
    sm = TileStateMachine(max_retries=2)
    sm.on_first_frame(current_time=10.0)

    # Retry 1
    sm.on_disconnect_or_error(fatal=False)
    assert sm.state == TileState.CONNECTING

    # Retry 2
    sm.on_disconnect_or_error(fatal=False)
    assert sm.state == TileState.CONNECTING

    # Retry 3 (> max_retries 2) -> OFFLINE
    sm.on_disconnect_or_error(fatal=False)
    assert sm.state == TileState.OFFLINE
    assert sm.is_live is False


def test_tile_state_machine_fatal_error() -> None:
    """Fatal errors immediately transition to ERROR."""
    sm = TileStateMachine()
    sm.on_disconnect_or_error(fatal=True)
    assert sm.state == TileState.ERROR
    assert sm.is_live is False
