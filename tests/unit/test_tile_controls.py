"""Unit tests for tile overlay controls, audio mute, and snapshot validation (LIVE-05)."""

from __future__ import annotations

from vizenlink_nvr.services.live_view import TileControlsModel, TileState


def test_tile_controls_mute_toggle() -> None:
    """Audio starts muted by default and toggles cleanly."""
    tile = TileControlsModel(camera_serial="CAM-01", camera_name="Front")
    assert tile.is_muted is True

    # Unmute
    assert tile.toggle_mute() is False
    assert tile.is_muted is False

    # Mute again
    assert tile.toggle_mute() is True
    assert tile.is_muted is True


def test_tile_controls_snapshot_validation() -> None:
    """Snapshot is only permissible when stream state is actively LIVE (LIVE-04, LIVE-05)."""
    tile = TileControlsModel(camera_serial="CAM-01", camera_name="Front")

    # Initial state is CONNECTING -> snapshot forbidden
    tile.state = TileState.CONNECTING
    assert tile.can_snapshot() is False

    # Stream stalls -> snapshot forbidden
    tile.state = TileState.STALLED
    assert tile.can_snapshot() is False

    # Stream offline -> snapshot forbidden
    tile.state = TileState.OFFLINE
    assert tile.can_snapshot() is False

    # Stream error -> snapshot forbidden
    tile.state = TileState.ERROR
    assert tile.can_snapshot() is False

    # Stream is live -> snapshot allowed
    tile.state = TileState.LIVE
    assert tile.can_snapshot() is True


def test_tile_controls_recording_badge_state() -> None:
    """Recording indicator state properly reflects camera recording status."""
    tile = TileControlsModel(camera_serial="CAM-01", camera_name="Front", is_recording=False)
    assert tile.is_recording is False

    tile.is_recording = True
    assert tile.is_recording is True
