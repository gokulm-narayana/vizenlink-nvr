"""Stateful simulated camera engine for offline demo / UI testing.

Activated ONLY for cameras whose ``hardware_id`` starts with ``HW-SIM-``.
Provides realistic, mutable responses for Camera Settings, Features, Privacy Masks,
Camera Accounts, Health, Reprobe, and dynamic 16:9 SVG snapshots reflecting Day/Night,
Infrared vs Full-Color Night Vision, Brightness/Contrast/Saturation, Orientation, OSD,
and Privacy Masks.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from html import escape
import math
from typing import Any

from fastapi import HTTPException

from vizenlink_nvr.db.models import Camera

SUPPORTED_TIMEZONES: list[dict[str, str]] = [
    {"code": "UTC", "label": "Coordinated Universal Time"},
    {"code": "Asia/Kolkata", "label": "India Standard Time"},
    {"code": "America/New_York", "label": "Eastern Time"},
    {"code": "America/Los_Angeles", "label": "Pacific Time"},
    {"code": "Europe/London", "label": "Greenwich Mean Time"},
]


def is_sim_camera(cam: Camera | None) -> bool:
    """Return True when the camera is marked as an interactive simulated device."""
    return bool(cam and cam.hardware_id and cam.hardware_id.startswith("HW-SIM-"))


class SimCameraManager:
    """In-memory state store for simulated cameras keyed by serial."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    def _default_state(self, cam: Camera) -> dict[str, Any]:
        serial = cam.serial
        is_outdoor = any(k in (cam.name + serial).lower() for k in ("parking", "gate", "dock", "lot"))
        scene_kind = (
            "parking"
            if "parking" in (cam.name + serial).lower()
            else "server"
            if "server" in (cam.name + serial).lower()
            else "cafe"
            if "cafe" in (cam.name + serial).lower()
            else "lobby"
        )
        return {
            "scene_kind": scene_kind,
            "identity": {
                "name": cam.name,
                "location": cam.location or "",
                "timezone": "Asia/Kolkata",
                "supported_timezones": copy.deepcopy(SUPPORTED_TIMEZONES),
            },
            "device_info": {
                "manufacturer": cam.manufacturer or "VizenLink",
                "model": cam.model or "VL-4K-ProDome",
                "firmware_version": cam.firmware_version or "3.4.2-sim",
                "serial_number": serial,
                "hardware_id": cam.hardware_id or "HW-SIM-01",
            },
            "encoders": [
                {
                    "profile_token": "prof_main",
                    "profile_name": "Main Stream (4K)",
                    "venc_token": "venc_main",
                    "current": {
                        "encoding": "H265",
                        "width": 3840,
                        "height": 2160,
                        "quality": 85,
                        "frame_rate_limit": 25,
                        "bitrate_limit_kbps": 4096,
                        "gov_length": 50,
                        "profile": "Main",
                        "cbr": False,
                    },
                    "options": {
                        "encodings": ["H264", "H265"],
                        "resolutions": [
                            {"width": 3840, "height": 2160},
                            {"width": 2560, "height": 1440},
                            {"width": 1920, "height": 1080},
                        ],
                        "quality_range": [1, 100],
                        "frame_rate_range": [1, 30],
                        "bitrate_range_kbps": [512, 8192],
                        "gov_length_range": [10, 120],
                        "supports_cbr": True,
                        "encoder_profiles": ["Main", "High"],
                        "frame_rates": [15, 20, 25, 30],
                        "codecs": [],
                    },
                },
                {
                    "profile_token": "prof_sub",
                    "profile_name": "Sub Stream (1080p)",
                    "venc_token": "venc_sub",
                    "current": {
                        "encoding": "H264",
                        "width": 1920,
                        "height": 1080,
                        "quality": 70,
                        "frame_rate_limit": 15,
                        "bitrate_limit_kbps": 1024,
                        "gov_length": 30,
                        "profile": "Main",
                        "cbr": True,
                    },
                    "options": {
                        "encodings": ["H264", "H265"],
                        "resolutions": [
                            {"width": 1920, "height": 1080},
                            {"width": 1280, "height": 720},
                            {"width": 640, "height": 360},
                        ],
                        "quality_range": [1, 100],
                        "frame_rate_range": [1, 30],
                        "bitrate_range_kbps": [128, 2048],
                        "gov_length_range": [10, 90],
                        "supports_cbr": True,
                        "encoder_profiles": ["Baseline", "Main", "High"],
                        "frame_rates": [10, 15, 20, 25],
                        "codecs": [],
                    },
                },
            ],
            "imaging": {
                "current": {
                    "brightness": 54.0,
                    "contrast": 52.0,
                    "color_saturation": 52.0,
                    "sharpness": 55.0,
                    "ir_cut_filter": "AUTO",
                    "day_night_now": "day",
                    "wdr_mode": "ON",
                    "wdr_level": 40.0,
                    "exposure_mode": "AUTO",
                    "exposure_time": 10000.0,
                    "exposure_gain": 15.0,
                    "white_balance_mode": "AUTO",
                    "night_vision_type": "smart",
                    "mirror_flip": "off",
                    "anti_flicker": "50Hz",
                },
                "options": {
                    "brightness_range": [0, 100],
                    "contrast_range": [0, 100],
                    "color_saturation_range": [0, 100],
                    "sharpness_range": [0, 100],
                    "ir_cut_filter_modes": ["AUTO", "ON", "OFF"],
                    "wdr_supported": True,
                    "wdr_level_range": [0, 100],
                    "exposure_modes": ["AUTO", "MANUAL"],
                    "exposure_time_range": [100, 40000],
                    "exposure_gain_range": [0, 100],
                    "white_balance_modes": ["AUTO", "MANUAL"],
                    "night_vision_color_capable": True,
                    "night_vision_smart_capable": True,
                },
            },
            "osd_options": {
                "positions": ["UpperLeft", "UpperRight", "BottomLeft", "BottomRight", "Custom"],
                "date_formats": ["dd/MM/yyyy", "MM/dd/yyyy", "yyyy-MM-dd"],
                "time_formats": ["hh:mm:ss tt", "HH:mm:ss"],
                "font_size_range": [14, 64],
                "font_color_range": True,
            },
            "osd": [
                {
                    "token": "OSD_Time",
                    "video_source_token": "VideoSource_1",
                    "osd_type": "DateAndTime",
                    "position": "UpperLeft",
                    "plain_text": "",
                    "date_format": "dd/MM/yyyy",
                    "time_format": "HH:mm:ss",
                    "position_x": -0.92,
                    "position_y": 0.9,
                    "font_size": 24,
                    "font_color": {"x": 1.0, "y": 1.0, "z": 1.0, "colorspace": "http://www.onvif.org/ver10/colorspace/RGB"},
                },
                {
                    "token": "OSD_Title",
                    "video_source_token": "VideoSource_1",
                    "osd_type": "Plain",
                    "position": "BottomRight",
                    "plain_text": cam.name,
                    "date_format": "",
                    "time_format": "",
                    "position_x": 0.9,
                    "position_y": -0.88,
                    "font_size": 24,
                    "font_color": {"x": 1.0, "y": 1.0, "z": 1.0, "colorspace": "http://www.onvif.org/ver10/colorspace/RGB"},
                },
            ],
            "health": {
                "serial": serial,
                "online": True,
                "uptime_seconds": 384620,
                "reboot_reason": "Power-on self test passed",
                "clock_sync_status": "synced",
                "firmware_version": cam.firmware_version or "3.4.2-sim",
                "last_seen": datetime.now(timezone.utc).isoformat(),
            },
            "capabilities": {
                "local_storage_capable": True,
                "accelerometer_capable": True,
                "bbox_overlay_capable": True,
                "has_microphone": True,
                "has_speaker": True,
                "buzzer_capable": True,
                "siren_capable": True,
                "spotlight_capable": True,
                "warning_capable": is_outdoor,
                "night_vision_color_capable": True,
                "night_vision_smart_capable": True,
                "multi_user": True,
                "user_roles": ["Operator", "User"],
                "max_users": 8,
                "supported_event_types": [
                    "PersonDetected",
                    "VehicleDetected",
                    "Loitering",
                    "MotionDetected",
                    "Tamper",
                ],
                "supported_event_deterrence_options": {
                    "PersonDetected": ["mobile_alert", "spotlight", "siren"],
                    "VehicleDetected": ["mobile_alert", "spotlight"],
                    "Loitering": ["mobile_alert", "spotlight"],
                    "MotionDetected": ["mobile_alert"],
                    "Tamper": ["mobile_alert", "siren"],
                },
                "loitering_duration_min_seconds": 5,
                "loitering_duration_max_seconds": 180,
                "supported_recording_modes": ["continuous", "scheduled", "event_triggered"],
                "recording_clip_duration_min_seconds": 10,
                "recording_clip_duration_max_seconds": 120,
                "max_recording_schedule_windows": 8,
                "supported_movement_sensitivities": ["Off", "Low", "Medium", "High"],
            },
            "feature_values": {
                "getPrivacyMode": {"mode": "None"},
                "getEventPreferences": {
                    "PersonDetected": True,
                    "VehicleDetected": is_outdoor,
                    "Loitering": False,
                    "MotionDetected": True,
                    "Tamper": True,
                },
                "getEventResponseActions": {
                    "PersonDetected": ["mobile_alert"],
                    "VehicleDetected": ["mobile_alert"] if is_outdoor else [],
                    "Loitering": [],
                    "MotionDetected": ["mobile_alert"],
                    "Tamper": ["mobile_alert", "siren"],
                },
                "getLoiteringDuration": {"loitering_duration_seconds": 25},
                "getBboxOverlay": {"enabled": True},
                "getAudioSettings": {"mic_gain": 65, "speaker_volume": 72},
                "getAudioRecording": {"enabled": True},
                "getTestSoundStatus": {"playing": False},
                "getBuzzerStatus": {"active": False},
                "getLocalStorage": {"enabled": True, "card_present": True, "capacity_gb": 128, "free_gb": 84},
                "getRecordingMode": {"mode": "continuous", "schedule": []},
                "getRecordingClipDuration": {"clip_duration_seconds": 30},
                "getRecordingDates": {"dates": [datetime.now(timezone.utc).strftime("%Y-%m-%d")]},
                "getDeterrenceStatus": {"siren": False, "spotlight": False, "warning": False},
                "getDeterrenceDurations": {"siren_seconds": 30, "spotlight_seconds": 60, "warning_repeat_count": 2},
                "getDeterrenceDurationOptions": {
                    "siren_seconds_min": 5,
                    "siren_seconds_max": 120,
                    "spotlight_seconds_min": 10,
                    "spotlight_seconds_max": 300,
                    "warning_repeat_count_min": 1,
                    "warning_repeat_count_max": 5,
                },
                "getMovementProtection": {"sensitivity": "Medium", "calibrated": True},
                "getWifi": {"ssid": "VizenLink-Corp-CAM", "security": "WPA2-PSK", "connected": True},
                "getWifiSignal": {"rssi_dbm": -52, "quality_percent": 88, "band": "5 GHz"},
                "getTimezones": {"timezone": "Asia/Kolkata"},
                "getDeviceHealth": {"status": "healthy", "uptime_seconds": 384620, "cpu_percent": 28, "temp_c": 41.5},
                "getVideoMode": {"mode": "Auto", "effective_state": "day"},
                "getImageDefaults": {"brightness": 50, "contrast": 50, "color_saturation": 50, "sharpness": 50},
                "getNightVisionType": {"type": "Smart"},
                "getMirrorFlip": {"mode": "Off"},
                "getAntiFlickerMode": {"mode": "50Hz"},
                "getLiveStreamUri": {"uri": f"rtsps://{cam.host}:560/stream1", "transport": "RTSPS"},
                "getTalkUri": {"uri": f"rtsps://{cam.host}:560/talk", "supported": True},
                "getCloudStreamingStatus": {"active": False},
            },
            "masks": {
                "options": {
                    "max_masks": 4,
                    "types": ["Color", "Pixelate"],
                    "colors": ["#000000"],
                    "rectangle_only": True,
                },
                "masks": [],
            },
            "accounts": {
                "accounts": [
                    {"username": "admin", "role": "Administrator"},
                    {"username": "nvr_sync", "role": "Operator"},
                    {"username": "guard_desk", "role": "User"},
                ],
                "roles": ["Operator", "User"],
                "max_users": 8,
                "current_username": "admin",
            },
        }

    def ensure(self, cam: Camera) -> dict[str, Any]:
        """Return mutable simulated state for ``cam``, creating defaults if missing."""
        if cam.serial not in self._states:
            self._states[cam.serial] = self._default_state(cam)
        state = self._states[cam.serial]
        state["identity"]["name"] = cam.name
        state["identity"]["location"] = cam.location or ""
        return state

    def get_settings(self, cam: Camera) -> dict[str, Any]:
        state = self.ensure(cam)
        return {
            "read_errors": {},
            "unavailable_sections": [],
            "identity": copy.deepcopy(state["identity"]),
            "device_info": copy.deepcopy(state["device_info"]),
            "encoders": copy.deepcopy(state["encoders"]),
            "imaging": copy.deepcopy(state["imaging"]),
            "osd_options": copy.deepcopy(state["osd_options"]),
            "osd": copy.deepcopy(state["osd"]),
        }

    def update_identity(
        self, cam: Camera, name: str | None = None, location: str | None = None, timezone: str | None = None
    ) -> dict[str, Any]:
        state = self.ensure(cam)
        updated: dict[str, Any] = {}
        if name is not None and name.strip():
            clean = name.strip()
            cam.name = clean
            state["identity"]["name"] = clean
            updated["name"] = clean
        if location is not None:
            clean_loc = location.strip()
            cam.location = clean_loc
            state["identity"]["location"] = clean_loc
            updated["location"] = clean_loc
        if timezone is not None and timezone.strip():
            clean_tz = timezone.strip()
            state["identity"]["timezone"] = clean_tz
            updated["timezone"] = clean_tz
        return {"status": "ok", "updated": updated}

    def update_encoder(self, cam: Camera, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.ensure(cam)
        venc_token = payload.get("venc_token")
        enc = next((e for e in state["encoders"] if e["venc_token"] == venc_token), state["encoders"][0])
        curr = enc["current"]
        for k in (
            "encoding",
            "width",
            "height",
            "frame_rate_limit",
            "bitrate_limit_kbps",
            "quality",
            "gov_length",
            "profile",
            "cbr",
        ):
            if payload.get(k) is not None:
                curr[k] = payload[k]
        return {"status": "ok", "encoder": copy.deepcopy(curr)}

    def update_imaging(self, cam: Camera, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.ensure(cam)
        curr = state["imaging"]["current"]
        for k, v in payload.items():
            if v is not None and k in curr:
                curr[k] = v

        ir = str(curr.get("ir_cut_filter") or "AUTO").upper()
        if ir == "OFF":
            curr["day_night_now"] = "night"
        elif ir == "ON":
            curr["day_night_now"] = "day"
        else:
            curr["day_night_now"] = "day"

        # Keep feature mirror state synchronized
        nv = str(curr.get("night_vision_type") or "smart").capitalize()
        if nv in ("Grey", "Color", "Smart"):
            state["feature_values"]["getNightVisionType"]["type"] = nv
        mf_map = {"off": "Off", "mirror": "Mirror", "flip": "Flip", "flip_mirror": "Both"}
        if curr.get("mirror_flip") in mf_map:
            state["feature_values"]["getMirrorFlip"]["mode"] = mf_map[curr["mirror_flip"]]
        state["feature_values"]["getVideoMode"] = {
            "mode": "Night" if ir == "OFF" else "Day" if ir == "ON" else "Auto",
            "effective_state": curr["day_night_now"],
        }
        return {"status": "ok", "imaging": copy.deepcopy(curr)}

    def update_osd(self, cam: Camera, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.ensure(cam)
        token = payload.get("token")
        target = next((o for o in state["osd"] if o["token"] == token), None)
        if target is None:
            raise HTTPException(404, "OSD overlay not found")
        for k in (
            "osd_type",
            "position",
            "plain_text",
            "date_format",
            "time_format",
            "position_x",
            "position_y",
            "font_size",
            "font_color",
        ):
            if payload.get(k) is not None:
                target[k] = payload[k]
        return {"status": "ok", "osd": copy.deepcopy(target)}

    def create_osd(self, cam: Camera, payload: dict[str, Any]) -> str:
        state = self.ensure(cam)
        token = f"OSD_{payload.get('osd_type', 'Custom')}_{len(state['osd']) + 1}"
        item = {
            "token": token,
            "video_source_token": payload.get("video_source_token", "VideoSource_1"),
            "osd_type": payload.get("osd_type", "Plain"),
            "position": payload.get("position", "UpperLeft"),
            "plain_text": payload.get("plain_text") or cam.name,
            "date_format": payload.get("date_format", "dd/MM/yyyy"),
            "time_format": payload.get("time_format", "HH:mm:ss"),
            "position_x": payload.get("position_x", -0.9),
            "position_y": payload.get("position_y", 0.9),
            "font_size": payload.get("font_size", 24),
            "font_color": payload.get("font_color")
            or {"x": 1.0, "y": 1.0, "z": 1.0, "colorspace": "http://www.onvif.org/ver10/colorspace/RGB"},
        }
        state["osd"].append(item)
        return token

    def delete_osd(self, cam: Camera, token: str) -> None:
        state = self.ensure(cam)
        state["osd"] = [o for o in state["osd"] if o["token"] != token]

    def get_health(self, cam: Camera) -> dict[str, Any]:
        state = self.ensure(cam)
        health = copy.deepcopy(state["health"])
        health["last_seen"] = datetime.now(timezone.utc).isoformat()
        return health

    def feature_state(self, cam: Camera, group: str, catalog: dict[str, Any]) -> dict[str, Any]:
        state = self.ensure(cam)
        values: dict[str, Any] = {}
        for op in catalog["operations"]:
            if op["method"] == "GET" and op["id"] in state["feature_values"]:
                values[op["id"]] = copy.deepcopy(state["feature_values"][op["id"]])
        return {
            **catalog,
            "capabilities": copy.deepcopy(state["capabilities"]),
            "values": values,
            "errors": {},
        }

    def execute_feature_action(
        self, cam: Camera, operation: str, payload: dict[str, Any], query: dict[str, Any]
    ) -> dict[str, Any]:
        state = self.ensure(cam)
        fv = state["feature_values"]
        output: dict[str, Any] = {}
        if operation == "setPrivacyMode":
            fv["getPrivacyMode"] = {"mode": payload["mode"]}
            output = copy.deepcopy(fv["getPrivacyMode"])
        elif operation == "setEventPreferences":
            fv["getEventPreferences"].update(payload)
            output = copy.deepcopy(fv["getEventPreferences"])
        elif operation == "setEventResponseActions":
            fv["getEventResponseActions"].update(payload)
            output = copy.deepcopy(fv["getEventResponseActions"])
        elif operation == "setLoiteringDuration":
            fv["getLoiteringDuration"] = {"loitering_duration_seconds": payload["loitering_duration_seconds"]}
            output = copy.deepcopy(fv["getLoiteringDuration"])
        elif operation == "setBboxOverlay":
            fv["getBboxOverlay"] = {"enabled": payload["enabled"]}
            output = copy.deepcopy(fv["getBboxOverlay"])
        elif operation == "setAudioSettings":
            fv["getAudioSettings"].update({k: v for k, v in payload.items() if v is not None})
            output = copy.deepcopy(fv["getAudioSettings"])
        elif operation == "setAudioRecording":
            fv["getAudioRecording"] = {"enabled": payload["enabled"]}
            output = copy.deepcopy(fv["getAudioRecording"])
        elif operation == "setTestSound":
            fv["getTestSoundStatus"] = {"playing": payload["active"]}
            output = copy.deepcopy(fv["getTestSoundStatus"])
        elif operation == "setBuzzer":
            fv["getBuzzerStatus"] = {"active": payload["active"]}
            output = copy.deepcopy(fv["getBuzzerStatus"])
        elif operation == "setDeterrence":
            fv["getDeterrenceStatus"][payload["action"]] = payload["active"]
            output = copy.deepcopy(fv["getDeterrenceStatus"])
        elif operation == "setDeterrenceDurations":
            fv["getDeterrenceDurations"].update({k: v for k, v in payload.items() if v is not None})
            output = copy.deepcopy(fv["getDeterrenceDurations"])
        elif operation == "setLocalStorage":
            fv["getLocalStorage"]["enabled"] = payload["enabled"]
            output = copy.deepcopy(fv["getLocalStorage"])
        elif operation == "setRecordingMode":
            fv["getRecordingMode"] = {"mode": payload["mode"], "schedule": payload.get("schedule", [])}
            output = copy.deepcopy(fv["getRecordingMode"])
        elif operation == "setRecordingClipDuration":
            fv["getRecordingClipDuration"] = {"clip_duration_seconds": payload["clip_duration_seconds"]}
            output = copy.deepcopy(fv["getRecordingClipDuration"])
        elif operation == "getRecordings":
            output = {"recordings": [], "card_present": True, "truncated": False}
        elif operation == "setMovementProtectionSensitivity":
            fv["getMovementProtection"]["sensitivity"] = payload["sensitivity"]
            output = copy.deepcopy(fv["getMovementProtection"])
        elif operation == "calibrateMovementProtection":
            fv["getMovementProtection"]["calibrated"] = True
            output = {"calibrated": True}
        elif operation == "setNightVisionType":
            fv["getNightVisionType"] = {"type": payload["type"]}
            state["imaging"]["current"]["night_vision_type"] = payload["type"].lower()
            output = copy.deepcopy(fv["getNightVisionType"])
        elif operation == "setMirrorFlip":
            fv["getMirrorFlip"] = {"mode": payload["mode"]}
            rev = {"Off": "off", "Mirror": "mirror", "Flip": "flip", "Both": "flip_mirror"}
            if payload["mode"] in rev:
                state["imaging"]["current"]["mirror_flip"] = rev[payload["mode"]]
            output = copy.deepcopy(fv["getMirrorFlip"])
        elif operation == "setAntiFlickerMode":
            fv["getAntiFlickerMode"] = {"mode": payload["mode"]}
            state["imaging"]["current"]["anti_flicker"] = payload["mode"]
            output = copy.deepcopy(fv["getAntiFlickerMode"])
        elif operation in fv:
            output = copy.deepcopy(fv[operation])
        else:
            output = {"applied": True, **payload}
        return {"status": "ok", "operation": operation, "output": output}

    def list_masks(self, cam: Camera) -> dict[str, Any]:
        return copy.deepcopy(self.ensure(cam)["masks"])

    def save_mask(
        self, cam: Camera, polygon: list[dict[str, float]], mask_type: str | None, enabled: bool, token: str | None
    ) -> dict[str, Any]:
        state = self.ensure(cam)
        masks = state["masks"]["masks"]
        chosen_type = mask_type or "Color"
        if token:
            for item in masks:
                if item["token"] == token:
                    item["polygon"] = polygon
                    item["type"] = chosen_type
                    item["enabled"] = enabled
                    return copy.deepcopy(item)
            raise HTTPException(404, "Privacy zone not found")
        if len(masks) >= state["masks"]["options"]["max_masks"]:
            raise HTTPException(422, "The camera's privacy-zone limit has been reached")
        new_token = f"Mask_{len(masks) + 1}"
        item = {"token": new_token, "polygon": polygon, "type": chosen_type, "enabled": enabled}
        masks.append(item)
        return copy.deepcopy(item)

    def delete_mask(self, cam: Camera, token: str) -> dict[str, str]:
        state = self.ensure(cam)
        state["masks"]["masks"] = [m for m in state["masks"]["masks"] if m["token"] != token]
        return {"status": "ok"}

    def list_accounts(self, cam: Camera) -> dict[str, Any]:
        return copy.deepcopy(self.ensure(cam)["accounts"])

    def change_account(self, cam: Camera, action: str, username: str, role: str | None) -> dict[str, str]:
        state = self.ensure(cam)
        accs = state["accounts"]["accounts"]
        existing = next((a for a in accs if a["username"] == username), None)
        if action == "create":
            if existing:
                raise HTTPException(409, "This camera account already exists")
            accs.append({"username": username, "role": role or "User"})
        elif action == "role":
            if not existing:
                raise HTTPException(404, "Camera account not found")
            existing["role"] = role or existing["role"]
        elif action == "delete":
            if not existing:
                raise HTTPException(404, "Camera account not found")
            if existing["role"] == "Administrator" or username == state["accounts"]["current_username"]:
                raise HTTPException(422, "This account is protected.")
            state["accounts"]["accounts"] = [a for a in accs if a["username"] != username]
        return {"status": "ok"}

    def render_snapshot_svg(self, cam: Camera, *, include_osd: bool = True) -> bytes:
        """Render a crisp 1280x720 simulated SVG camera feed reflecting live camera settings."""
        state = self.ensure(cam)
        curr = state["imaging"]["current"]
        day_night = curr.get("day_night_now", "day")
        nv_type = str(curr.get("night_vision_type") or "grey").lower()
        is_night = day_night == "night"
        is_ir_bw = is_night and nv_type == "grey"
        is_color_night = is_night and nv_type in ("color", "smart")

        bright = float(curr.get("brightness", 50)) / 50.0
        contrast = float(curr.get("contrast", 50)) / 50.0
        sat = 0.0 if is_ir_bw else float(curr.get("color_saturation", 50)) / 50.0

        mf = curr.get("mirror_flip", "off")
        sx = -1 if mf in ("mirror", "flip_mirror") else 1
        sy = -1 if mf in ("flip", "flip_mirror") else 1
        tx = 1280 if sx == -1 else 0
        ty = 720 if sy == -1 else 0
        flip_transform = f"translate({tx},{ty}) scale({sx},{sy})" if (sx == -1 or sy == -1) else ""

        if is_ir_bw:
            sky_top, sky_bot = "#080b10", "#161d26"
            floor_top, floor_bot = "#1b232d", "#0e1319"
            wall_fill, accent_fill = "#222b36", "#9fb3c8"
            person_fill, pillar_fill = "#d5e2ee", "#2f3a47"
            mode_badge = "NIGHT MODE · INFRARED 850nm (B&W)"
            badge_bg = "#1e293b"
            badge_fg = "#e2e8f0"
        elif is_color_night:
            sky_top, sky_bot = "#060c1a", "#101e36"
            floor_top, floor_bot = "#16253b", "#0b1322"
            wall_fill, accent_fill = "#1e3250", "#38bdf8"
            person_fill, pillar_fill = "#f59e0b", "#2a4365"
            mode_badge = f"NIGHT MODE · {'SMART DUAL-LED' if nv_type == 'smart' else 'FULL COLOR SPOTLIGHT'}"
            badge_bg = "#0f2942"
            badge_fg = "#7dd3fc"
        else:
            sky_top, sky_bot = "#87b5e5", "#d4e6f8"
            floor_top, floor_bot = "#dbe2ec", "#b8c4d4"
            wall_fill, accent_fill = "#f1f5f9", "#0056d2"
            person_fill, pillar_fill = "#1e293b", "#cbd5e1"
            mode_badge = f"DAY MODE · COLOUR ({curr.get('ir_cut_filter', 'AUTO')})"
            badge_bg = "#064e3b"
            badge_fg = "#6ee7b7"

        wdr_on = curr.get("wdr_mode", "OFF") != "OFF"
        deterrence = state["feature_values"].get("getDeterrenceStatus", {})
        spotlight_on = bool(deterrence.get("spotlight")) or is_color_night
        privacy_full = state["feature_values"].get("getPrivacyMode", {}).get("mode") == "Full"

        scene_kind = state["scene_kind"]
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        bboxes_on = bool(state["feature_values"].get("getBboxOverlay", {}).get("enabled", True))

        # Scene elements
        scene_shapes: list[str] = []
        if privacy_full:
            scene_shapes.append('<rect width="1280" height="720" fill="#05070b"/>')
            scene_shapes.append(
                '<text x="640" y="360" text-anchor="middle" fill="#94a3b8" '
                'font-family="sans-serif" font-size="32" font-weight="600">PRIVACY MODE ACTIVE</text>'
            )
        else:
            scene_shapes.append(f'<rect width="1280" height="410" fill="url(#skyGrad)"/>')
            scene_shapes.append(f'<rect y="410" width="1280" height="310" fill="url(#floorGrad)"/>')
            # Architectural lines & perspective floor grid
            scene_shapes.append(
                f'<line x1="0" y1="410" x2="1280" y2="410" stroke="{accent_fill}" stroke-opacity="0.35" stroke-width="2"/>'
            )
            for gx in range(-200, 1500, 160):
                scene_shapes.append(
                    f'<line x1="{gx}" y1="720" x2="{640 + (gx - 640) * 0.42:.1f}" y2="410" '
                    f'stroke="{accent_fill}" stroke-opacity="0.14" stroke-width="1.5"/>'
                )

            if scene_kind == "parking":
                # Parking lot bays + parked vehicle silhouette
                scene_shapes.append(
                    f'<rect x="180" y="330" width="320" height="125" rx="18" fill="{pillar_fill}" stroke="{accent_fill}" stroke-opacity="0.5"/>'
                )
                scene_shapes.append(
                    f'<rect x="220" y="346" width="180" height="44" rx="8" fill="{wall_fill}" fill-opacity="0.7"/>'
                )
                scene_shapes.append('<circle cx="250" cy="455" r="24" fill="#0f172a"/><circle cx="430" cy="455" r="24" fill="#0f172a"/>')
                # Headlights or IR glow
                if is_night:
                    scene_shapes.append('<ellipse cx="520" cy="400" rx="90" ry="28" fill="#fde68a" fill-opacity="0.22"/>')
            elif scene_kind == "server":
                # Server racks with LED indicators
                for i, rx in enumerate((190, 410, 630, 850)):
                    scene_shapes.append(
                        f'<rect x="{rx}" y="130" width="160" height="350" rx="6" fill="{pillar_fill}" stroke="{accent_fill}" stroke-opacity="0.35"/>'
                    )
                    for ly in range(160, 440, 34):
                        led_color = "#22c55e" if (i + ly) % 3 else "#38bdf8"
                        if is_ir_bw:
                            led_color = "#cbd5e1"
                        scene_shapes.append(f'<rect x="{rx + 18}" y="{ly}" width="124" height="14" rx="2" fill="#0b1220" fill-opacity="0.55"/>')
                        scene_shapes.append(f'<circle cx="{rx + 128}" cy="{ly + 7}" r="3.5" fill="{led_color}"/>')
            elif scene_kind == "cafe":
                # Cafeteria counter, tables & seating
                scene_shapes.append(
                    f'<rect x="120" y="250" width="520" height="190" rx="10" fill="{wall_fill}" stroke="{accent_fill}" stroke-opacity="0.3"/>'
                )
                scene_shapes.append(
                    f'<rect x="120" y="242" width="520" height="22" rx="4" fill="{pillar_fill}"/>'
                )
                for tx_pos in (740, 960):
                    scene_shapes.append(f'<ellipse cx="{tx_pos}" cy="460" rx="86" ry="24" fill="{pillar_fill}"/>')
                    scene_shapes.append(f'<rect x="{tx_pos - 8}" y="460" width="16" height="80" fill="{wall_fill}"/>')
                    scene_shapes.append(f'<ellipse cx="{tx_pos}" cy="542" rx="42" ry="10" fill="{pillar_fill}"/>')
            else:
                # Lobby glass entrance doors & reception desk
                scene_shapes.append(
                    f'<rect x="440" y="120" width="400" height="290" rx="4" fill="{wall_fill}" fill-opacity="0.45" stroke="{accent_fill}" stroke-opacity="0.5" stroke-width="3"/>'
                )
                scene_shapes.append(
                    f'<line x1="640" y1="120" x2="640" y2="410" stroke="{accent_fill}" stroke-opacity="0.5" stroke-width="3"/>'
                )
                scene_shapes.append(
                    f'<rect x="110" y="340" width="240" height="120" rx="8" fill="{pillar_fill}" stroke="{accent_fill}" stroke-opacity="0.3"/>'
                )

            # Person silhouette + optional AI detection bounding box
            px, py = (780, 325) if scene_kind != "cafe" else (670, 320)
            scene_shapes.append(f'<circle cx="{px}" cy="{py}" r="22" fill="{person_fill}"/>')
            scene_shapes.append(
                f'<rect x="{px - 26}" y="{py + 26}" width="52" height="92" rx="14" fill="{person_fill}"/>'
            )
            scene_shapes.append(
                f'<rect x="{px - 22}" y="{py + 114}" width="18" height="68" rx="6" fill="{person_fill}"/>'
                f'<rect x="{px + 4}" y="{py + 114}" width="18" height="68" rx="6" fill="{person_fill}"/>'
            )
            if bboxes_on:
                box_color = "#e2e8f0" if is_ir_bw else "#22c55e"
                scene_shapes.append(
                    f'<rect x="{px - 36}" y="{py - 32}" width="72" height="224" rx="4" fill="none" stroke="{box_color}" stroke-width="2.5" stroke-dasharray="6 3"/>'
                )
                scene_shapes.append(
                    f'<rect x="{px - 36}" y="{py - 56}" width="114" height="22" rx="3" fill="{box_color}"/>'
                    f'<text x="{px - 30}" y="{py - 40}" fill="#05130a" font-family="monospace" font-size="13" font-weight="bold">PERSON 96%</text>'
                )

            # Night / IR / Spotlight lighting cones
            if is_ir_bw:
                scene_shapes.append('<rect width="1280" height="720" fill="url(#irVignette)"/>')
            elif spotlight_on:
                scene_shapes.append('<polygon points="640,0 160,720 1120,720" fill="url(#spotGlow)"/>')

            # WDR subtle dynamic boost indicator
            if wdr_on:
                scene_shapes.append(
                    '<rect x="24" y="64" width="130" height="26" rx="6" fill="#000000" fill-opacity="0.55"/>'
                    '<text x="36" y="81" fill="#e2e8f0" font-family="monospace" font-size="13">WDR ACTIVE</text>'
                )

            # Privacy masks are only applied in Zone mode, as on a real camera
            # (camera_api SETTINGS_API_GUIDE "Privacy Mode": zone = blank out configured mask zones).
            zone_mode = state["feature_values"].get("getPrivacyMode", {}).get("mode") == "Zone"
            for mask in state["masks"]["masks"] if zone_mode else []:
                if not mask.get("enabled", True):
                    continue
                poly = mask.get("polygon", [])
                if len(poly) == 4:
                    xs = [(p["x"] + 1.0) * 640.0 for p in poly]
                    ys = [(1.0 - p["y"]) * 360.0 for p in poly]
                    mx, my = min(xs), min(ys)
                    mw, mh = max(xs) - mx, max(ys) - my
                    fill = "#000000" if mask.get("type") == "Color" else "#1e293b"
                    scene_shapes.append(f'<rect x="{mx:.1f}" y="{my:.1f}" width="{mw:.1f}" height="{mh:.1f}" fill="{fill}" stroke="#38bdf8" stroke-width="2"/>')

        # Active OSD Overlays (rendered upright even if image is flipped, or aligned with scene)
        osd_shapes: list[str] = []
        if include_osd:
            pos_coords = {
                "UpperLeft": (28, 44, "start"),
                "UpperRight": (1252, 44, "end"),
                "BottomLeft": (28, 686, "start"),
                "BottomRight": (1252, 686, "end"),
            }
            for o in state["osd"]:
                pos = o.get("position", "UpperLeft")
                if pos in pos_coords:
                    ox, oy, anchor = pos_coords[pos]
                else:
                    ox = max(28.0, min(1252.0, ((o.get("position_x") or 0.0) + 1.0) * 640.0))
                    oy = max(36.0, min(696.0, (1.0 - (o.get("position_y") or 0.0)) * 360.0))
                    anchor = "start" if ox < 360 else "end" if ox > 920 else "middle"
                fc = o.get("font_color")
                if isinstance(fc, dict) and all(k in fc for k in ("x", "y", "z")):
                    fill_hex = "#" + "".join(
                        f"{max(0, min(255, round(float(fc[k]) * 255))):02x}" for k in ("x", "y", "z")
                    )
                else:
                    fill_hex = "#ffffff"
                label = now_str if o.get("osd_type") == "DateAndTime" else (o.get("plain_text") or cam.name)
                fsize = int(o.get("font_size") or 24)
                osd_shapes.append(
                    f'<text x="{ox:.1f}" y="{oy:.1f}" text-anchor="{anchor}" fill="{fill_hex}" '
                    f'stroke="#000000" stroke-width="3" paint-order="stroke" '
                    f'font-family="monospace" font-size="{fsize}" font-weight="bold">{escape(label)}</text>'
                )

        hud_badge = (
            f'<g>'
            f'<rect x="420" y="18" width="440" height="32" rx="16" fill="{badge_bg}" fill-opacity="0.88" stroke="{badge_fg}" stroke-opacity="0.45"/>'
            f'<text x="640" y="39" text-anchor="middle" fill="{badge_fg}" font-family="monospace" font-size="14" font-weight="bold">{escape(mode_badge)}</text>'
            f'</g>'
        )

        filter_str = f"brightness({bright:.2f}) contrast({contrast:.2f}) saturate({sat:.2f})"
        # Clamp mild extreme filter values so 0 isn't pitch-black accidentally unless set to 0
        if math.isnan(bright):
            filter_str = ""

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <defs>
    <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{sky_top}"/>
      <stop offset="100%" stop-color="{sky_bot}"/>
    </linearGradient>
    <linearGradient id="floorGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{floor_top}"/>
      <stop offset="100%" stop-color="{floor_bot}"/>
    </linearGradient>
    <radialGradient id="irVignette" cx="50%" cy="48%" r="65%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.06"/>
      <stop offset="70%" stop-color="#000000" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.62"/>
    </radialGradient>
    <linearGradient id="spotGlow" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fef08a" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#fef08a" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <g style="filter: {filter_str}" transform="{flip_transform}">
    {"".join(scene_shapes)}
  </g>
  {"".join(osd_shapes)}
  {hud_badge}
</svg>'''
        return svg.encode("utf-8")


SIM_CAMERAS = SimCameraManager()
