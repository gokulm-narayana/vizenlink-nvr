"""NuraEye REST client for proprietary camera settings (SET-01, SET-03, SET-08).

Covers:
- Night Vision Type (grey, color, smart)
- Mirror / Flip mode (off, mirror, flip, both)
- Anti-Flicker / Power-line frequency (50Hz, 60Hz, Auto)
- Supported Timezones catalog
"""

from __future__ import annotations

from dataclasses import dataclass

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.sessions import NuraeyeSessionCache
from vizenlink_nvr.camera.result import CameraResult, Failure, FailureKind, Success
from vizenlink_nvr.timeutil import Clock

NIGHT_VISION_TYPES = {"grey", "color", "smart"}
MIRROR_FLIP_MODES = {"off", "mirror", "flip", "both"}
ANTI_FLICKER_MODES = {"50Hz", "60Hz", "Auto", "None"}

FALLBACK_TIMEZONES = [
    {"code": "UTC", "label": "UTC (Coordinated Universal Time)"},
    {"code": "GMT", "label": "GMT (Greenwich Mean Time)"},
    {"code": "EST5EDT", "label": "America/New_York (Eastern Time)"},
    {"code": "CST6CDT", "label": "America/Chicago (Central Time)"},
    {"code": "MST7MDT", "label": "America/Denver (Mountain Time)"},
    {"code": "PST8PDT", "label": "America/Los_Angeles (Pacific Time)"},
    {"code": "IST-5:30", "label": "Asia/Kolkata (Indian Standard Time)"},
    {"code": "CST-8", "label": "Asia/Shanghai (China Standard Time)"},
    {"code": "JST-9", "label": "Asia/Tokyo (Japan Standard Time)"},
    {"code": "AEST-10AEDT", "label": "Australia/Sydney (Eastern Time)"},
    {"code": "CET-1CEST", "label": "Europe/Berlin (Central European Time)"},
    {"code": "WET-0WEST", "label": "Europe/London (Western European Time)"},
]


@dataclass(frozen=True)
class NightVisionStatus:
    current_type: str
    color_capable: bool = False
    smart_capable: bool = False


class NuraeyeSettingsClient:
    """Client for NuraEye proprietary REST settings endpoints."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
        sessions: NuraeyeSessionCache | None = None,
    ) -> None:
        self.conn, self.http, self.clock = conn, http, clock
        self.client = NuraeyeClient(conn, http, clock, sessions=sessions)

    async def get_night_vision_type(self, timeout: float = 8.0) -> CameraResult[NightVisionStatus]:
        result = await self.client.request("GET", "/nuraeye/video/night-vision-type", timeout=timeout)
        if not isinstance(result, Success):
            return result
        value = result.value.get("type")
        if not isinstance(value, str) or value.lower() not in NIGHT_VISION_TYPES:
            return Failure(FailureKind.BAD_RESPONSE, "Camera did not report a valid night vision type")
        caps = await self.client.get_capabilities(timeout=timeout)
        return Success(
            NightVisionStatus(
                value.lower(),
                color_capable=caps.value.night_vision_color_capable if isinstance(caps, Success) else False,
                smart_capable=caps.value.night_vision_smart_capable if isinstance(caps, Success) else False,
            )
        )

    async def set_night_vision_type(self, nv_type: str, timeout: float = 8.0) -> CameraResult[bool]:
        value = nv_type.lower().strip()
        if value not in NIGHT_VISION_TYPES:
            return Failure(FailureKind.GENERIC, f"Invalid night vision type '{nv_type}'")
        result = await self.client.request(
            "POST", "/nuraeye/video/night-vision-type", {"type": value.title()}, timeout
        )
        return Success(True) if isinstance(result, Success) else result

    async def get_mirror_flip(self, timeout: float = 8.0) -> CameraResult[str]:
        result = await self.client.request("GET", "/nuraeye/video/mirror-flip", timeout=timeout)
        if not isinstance(result, Success):
            return result
        mode = result.value.get("mode")
        if not isinstance(mode, str) or mode.lower() not in MIRROR_FLIP_MODES:
            return Failure(FailureKind.BAD_RESPONSE, "Camera did not report a valid mirror/flip mode")
        return Success(mode.lower())

    async def set_mirror_flip(self, mode: str, timeout: float = 8.0) -> CameraResult[bool]:
        value = mode.lower().strip()
        if value not in MIRROR_FLIP_MODES:
            return Failure(FailureKind.GENERIC, f"Invalid mirror/flip mode '{mode}'")
        result = await self.client.request(
            "POST", "/nuraeye/video/mirror-flip", {"mode": value.title()}, timeout
        )
        return Success(True) if isinstance(result, Success) else result

    async def get_anti_flicker(self, timeout: float = 8.0) -> CameraResult[str]:
        result = await self.client.request("GET", "/nuraeye/video/anti-flicker", timeout=timeout)
        if not isinstance(result, Success):
            return result
        mode = result.value.get("mode")
        if mode not in ANTI_FLICKER_MODES:
            return Failure(FailureKind.BAD_RESPONSE, "Camera did not report a valid anti-flicker mode")
        return Success(mode)

    async def set_anti_flicker(self, mode: str, timeout: float = 8.0) -> CameraResult[bool]:
        value = next((m for m in ANTI_FLICKER_MODES if m.lower() == mode.lower().strip()), None)
        if value is None:
            return Failure(FailureKind.GENERIC, f"Invalid anti-flicker mode '{mode}'")
        result = await self.client.request("POST", "/nuraeye/video/anti-flicker", {"mode": value}, timeout)
        return Success(True) if isinstance(result, Success) else result

    async def get_supported_timezones(self, timeout: float = 8.0) -> CameraResult[list[dict[str, str]]]:
        result = await self.client.request("GET", "/nuraeye/timezones", timeout=timeout)
        if isinstance(result, Success):
            zones = result.value.get("timezones")
            if isinstance(zones, list) and zones:
                return Success(
                    [
                        {"code": str(z["code"]), "label": str(z.get("name", z.get("label", z["code"])))}
                        for z in zones
                        if isinstance(z, dict) and isinstance(z.get("code"), str)
                    ]
                )
        if isinstance(result, Failure) and result.http_status == 404:
            return Success(FALLBACK_TIMEZONES)
        return (
            result
            if not isinstance(result, Success)
            else Failure(FailureKind.BAD_RESPONSE, "Camera returned an empty timezone catalog")
        )
