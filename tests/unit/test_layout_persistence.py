"""Unit tests for grid layout configuration persistence (LIVE-06)."""

from __future__ import annotations

from vizenlink_nvr.services.live_view import GridLayoutConfig


def test_layout_config_defaults() -> None:
    """Default layout is 2x2, page 0, empty slots."""
    cfg = GridLayoutConfig()
    assert cfg.dimension == 2
    assert cfg.page == 0
    assert cfg.slot_assignments == {}


def test_layout_config_serialization_roundtrip() -> None:
    """Config serializes to JSON and deserializes identically."""
    cfg = GridLayoutConfig(
        dimension=3,
        page=1,
        slot_assignments={0: "CAM-01", 1: "CAM-02", 4: "CAM-05"},
    )
    serialized = cfg.to_json()
    restored = GridLayoutConfig.from_json(serialized)

    assert restored.dimension == 3
    assert restored.page == 1
    assert restored.slot_assignments == {0: "CAM-01", 1: "CAM-02", 4: "CAM-05"}


def test_layout_config_invalid_data_sanitization() -> None:
    """Invalid dimensions or negative pages fall back safely."""
    # Invalid dimension 7 falls back to 2
    bad_dim = GridLayoutConfig.from_dict({"dimension": 7, "page": -5, "slot_assignments": {"bad": 123}})
    assert bad_dim.dimension == 2
    assert bad_dim.page == 0

    # Malformed JSON falls back to defaults
    malformed = GridLayoutConfig.from_json("invalid json string {}")
    assert malformed.dimension == 2
    assert malformed.page == 0

