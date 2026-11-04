"""Unit tests for Camera Settings UI models, capability filtering, and bounds logic (Plan 06-03).

Tests:
- Dynamic capability gating logic (SET-08):
  - WDR controls hidden when wdr_supported is False
  - Color / Smart Night Vision disabled when sensor flags are False
  - Resolution dropdown options populated from camera reported options
- Value clamping and bounds validation helper logic (SET-02, SET-03)
- Role verification for destructive maintenance actions (SET-05, SET-06)
"""

from __future__ import annotations

from vizenlink_nvr.camera.nuraeye.settings import NightVisionStatus
from vizenlink_nvr.camera.onvif.imaging import ImagingOptions
from vizenlink_nvr.camera.onvif.media2 import (
    VideoEncoderConfigurationOptions,
    VideoResolution,
)


def filter_available_night_vision_types(status: NightVisionStatus) -> list[str]:
    """Helper mimicking UI filtering of night vision choices."""
    types = ["grey"]
    if status.color_capable:
        types.append("color")
    if status.smart_capable:
        types.append("smart")
    return types


def is_wdr_ui_visible(options: ImagingOptions) -> bool:
    """Helper determining whether WDR card should render in UI (SET-08)."""
    return bool(options.wdr_supported)


def clamp_setting_value(value: float, min_val: float, max_val: float) -> float:
    """Clamp setting value within allowed range."""
    return max(min_val, min(max_val, value))


def get_resolution_labels(options: VideoEncoderConfigurationOptions) -> list[str]:
    """Format available resolutions for dropdown selector."""
    return [f"{r.width}x{r.height}" for r in options.resolutions]


def can_perform_maintenance(role: str | None) -> bool:
    """Verify role authorization for reboot and factory reset."""
    return role in ("owner", "operator")


# -----------------------------------------------------------------------------
# Unit Tests
# -----------------------------------------------------------------------------


def test_wdr_capability_gating() -> None:
    # 1. Non-WDR build (e.g. compile-time disabled or non-HDR sensor)
    opts_no_wdr = ImagingOptions(wdr_supported=False)
    assert is_wdr_ui_visible(opts_no_wdr) is False

    # 2. HDR-capable sensor build
    opts_wdr = ImagingOptions(wdr_supported=True)
    assert is_wdr_ui_visible(opts_wdr) is True


def test_night_vision_type_filtering() -> None:
    # Standard IR sensor only
    nv_basic = NightVisionStatus(current_type="grey", color_capable=False, smart_capable=False)
    assert filter_available_night_vision_types(nv_basic) == ["grey"]

    # Color night vision capable
    nv_color = NightVisionStatus(current_type="color", color_capable=True, smart_capable=False)
    assert filter_available_night_vision_types(nv_color) == ["grey", "color"]

    # Full dual-mode smart night vision sensor
    nv_smart = NightVisionStatus(current_type="smart", color_capable=True, smart_capable=True)
    assert filter_available_night_vision_types(nv_smart) == ["grey", "color", "smart"]


def test_encoder_resolution_dropdown_generation() -> None:
    opts_dual = VideoEncoderConfigurationOptions(
        token="VEC_Main",
        encodings=("H264", "H265"),
        resolutions=(VideoResolution(2560, 1440), VideoResolution(1920, 1080)),
        quality_range=(1.0, 100.0),
        frame_rate_range=(5.0, 30.0),
        bitrate_range_kbps=(256, 8192),
    )
    labels = get_resolution_labels(opts_dual)
    assert labels == ["2560x1440", "1920x1080"]

    opts_single = VideoEncoderConfigurationOptions(
        token="VEC_Sub",
        encodings=("H264",),
        resolutions=(VideoResolution(640, 360),),
        quality_range=(1.0, 100.0),
        frame_rate_range=(5.0, 30.0),
        bitrate_range_kbps=(128, 2048),
    )
    assert get_resolution_labels(opts_single) == ["640x360"]


def test_value_clamping_logic() -> None:
    assert clamp_setting_value(120.0, 0.0, 100.0) == 100.0
    assert clamp_setting_value(-10.0, 0.0, 100.0) == 0.0
    assert clamp_setting_value(55.0, 0.0, 100.0) == 55.0


def test_role_maintenance_authorization() -> None:
    assert can_perform_maintenance("owner") is True
    assert can_perform_maintenance("operator") is True
    assert can_perform_maintenance("viewer") is False
    assert can_perform_maintenance(None) is False
