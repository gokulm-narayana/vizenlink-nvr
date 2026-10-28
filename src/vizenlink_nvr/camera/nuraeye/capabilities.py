# mirrors: mobile_app/packages/camera_api/lib/src/recording_mode_types.dart@871a4cd15860
# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/capabilities_client.dart@109c790ed5ae
"""Typed models and parser for NuraEye camera capabilities."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vizenlink_nvr.camera.result import Failure, FailureKind


class RecordingMode(StrEnum):
    """Local SD recording modes."""

    CONTINUOUS = "continuous"
    SCHEDULED = "scheduled"
    EVENT_TRIGGERED = "event_triggered"


class Capabilities(BaseModel):
    """Typed camera capabilities parsed from /nuraeye/capabilities."""

    model_config = ConfigDict(frozen=True)

    raw: dict[str, Any] = Field(default_factory=dict)
    wan_command_capable: bool = False
    wan_live_view_capable: bool = False
    siren_capable: bool = False
    spotlight_capable: bool = False
    warning_capable: bool = False
    local_storage_capable: bool = False
    recording_clip_duration_min_seconds: int = 0
    recording_clip_duration_max_seconds: int = 0
    supported_recording_modes: list[RecordingMode] = Field(default_factory=list)
    multi_user: bool = False
    default_password_in_use: bool = False
    max_users: int = 1
    user_roles: list[str] = Field(default_factory=list)
    camera_id_check: bool = False
    max_recording_schedule_windows: int = 14
    loitering_duration_min_seconds: int = 0
    loitering_duration_max_seconds: int = 0
    bbox_overlay_capable: bool = False
    night_vision_color_capable: bool = False
    night_vision_smart_capable: bool = False
    supported_event_types: list[str] = Field(default_factory=list)
    supported_event_deterrence_options: dict[str, list[str]] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)


def parse_capabilities(
    output: dict[str, Any],
    *,
    strict: bool = False,
) -> Capabilities | Failure:
    """Parse /nuraeye/capabilities output dict into typed Capabilities object."""
    missing_required: list[str] = []
    if not isinstance(output.get("wan_command_capable"), bool):
        missing_required.append("wan_command_capable")
    if not isinstance(output.get("wan_live_view_capable"), bool):
        missing_required.append("wan_live_view_capable")

    if strict and missing_required:
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=(f"GetCapabilities response missing {', '.join(missing_required)}: {output}"),
        )

    wan_command_capable = (
        output["wan_command_capable"] if isinstance(output.get("wan_command_capable"), bool) else False
    )
    wan_live_view_capable = (
        output["wan_live_view_capable"] if isinstance(output.get("wan_live_view_capable"), bool) else False
    )

    siren_capable = output.get("siren_capable") is True
    spotlight_capable = output.get("spotlight_capable") is True
    warning_capable = output.get("warning_capable") is True
    local_storage_capable = output.get("local_storage_capable") is True

    rec_min = (
        output["recording_clip_duration_min_seconds"]
        if isinstance(output.get("recording_clip_duration_min_seconds"), int)
        else 0
    )
    rec_max = (
        output["recording_clip_duration_max_seconds"]
        if isinstance(output.get("recording_clip_duration_max_seconds"), int)
        else 0
    )
    loit_min = (
        output["loitering_duration_min_seconds"]
        if isinstance(output.get("loitering_duration_min_seconds"), int)
        else 0
    )
    loit_max = (
        output["loitering_duration_max_seconds"]
        if isinstance(output.get("loitering_duration_max_seconds"), int)
        else 0
    )

    bbox_overlay_capable = output.get("bbox_overlay_capable") is True
    multi_user = output.get("multi_user") is True
    max_users = output["max_users"] if isinstance(output.get("max_users"), int) else 1

    raw_user_roles = output.get("user_roles")
    user_roles = (
        [str(r) for r in raw_user_roles if isinstance(r, str)] if isinstance(raw_user_roles, list) else []
    )

    default_password_in_use = output.get("default_password_in_use") is True
    camera_id_check = output.get("camera_id_check") is True
    night_vision_color_capable = output.get("night_vision_color_capable") is True
    night_vision_smart_capable = output.get("night_vision_smart_capable") is True

    max_schedule_windows = (
        output["max_recording_schedule_windows"]
        if isinstance(output.get("max_recording_schedule_windows"), int)
        else 14
    )

    rec_modes: list[RecordingMode] = []
    raw_modes = output.get("supported_recording_modes")
    if isinstance(raw_modes, list):
        for m in raw_modes:
            if isinstance(m, str):
                try:
                    rec_modes.append(RecordingMode(m))
                except ValueError:
                    pass

    raw_event_types = output.get("supported_event_types")
    supported_event_types = (
        [str(e) for e in raw_event_types if isinstance(e, str)] if isinstance(raw_event_types, list) else []
    )

    raw_deterrence = output.get("supported_event_deterrence_options")
    supported_event_deterrence_options: dict[str, list[str]] = {}
    if isinstance(raw_deterrence, dict):
        for k, v in raw_deterrence.items():
            if isinstance(v, list):
                supported_event_deterrence_options[str(k)] = [
                    str(action) for action in v if isinstance(action, str)
                ]
            else:
                supported_event_deterrence_options[str(k)] = []

    return Capabilities(
        raw=output,
        wan_command_capable=wan_command_capable,
        wan_live_view_capable=wan_live_view_capable,
        siren_capable=siren_capable,
        spotlight_capable=spotlight_capable,
        warning_capable=warning_capable,
        local_storage_capable=local_storage_capable,
        recording_clip_duration_min_seconds=rec_min,
        recording_clip_duration_max_seconds=rec_max,
        supported_recording_modes=rec_modes,
        multi_user=multi_user,
        default_password_in_use=default_password_in_use,
        max_users=max_users,
        user_roles=user_roles,
        camera_id_check=camera_id_check,
        max_recording_schedule_windows=max_schedule_windows,
        loitering_duration_min_seconds=loit_min,
        loitering_duration_max_seconds=loit_max,
        bbox_overlay_capable=bbox_overlay_capable,
        night_vision_color_capable=night_vision_color_capable,
        night_vision_smart_capable=night_vision_smart_capable,
        supported_event_types=supported_event_types,
        supported_event_deterrence_options=supported_event_deterrence_options,
        missing_required=missing_required,
    )
