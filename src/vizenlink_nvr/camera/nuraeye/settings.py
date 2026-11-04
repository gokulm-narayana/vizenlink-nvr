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
from vizenlink_nvr.camera.nuraeye.rest import (
    RestError,
    RestOk,
    failure_from_rest,
    get_json,
    post_json,
)
from vizenlink_nvr.camera.result import CameraResult, Failure, FailureKind, Success, Timeout
from vizenlink_nvr.timeutil import Clock

NIGHT_VISION_TYPES = {"grey", "color", "smart"}
MIRROR_FLIP_MODES = {"off", "mirror", "flip", "both"}
ANTI_FLICKER_MODES = {"50Hz", "60Hz", "Auto"}

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
    color_capable: bool = True
    smart_capable: bool = True


class NuraeyeSettingsClient:
    """Client for NuraEye proprietary REST settings endpoints."""

    def __init__(
        self,
        conn: CameraConnection,
        http: CameraHttp,
        clock: Clock,
    ) -> None:
        self.conn = conn
        self.http = http
        self.clock = clock

    async def get_night_vision_type(self, timeout: float = 8.0) -> CameraResult[NightVisionStatus]:
        """Fetch current night vision rendering type and capabilities."""
        res = await get_json(self.http, self.conn, "/nuraeye/video/night-vision", timeout=timeout)
        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)

        output = res.output
        curr = output.get("type") or output.get("night_vision_type") or "grey"
        color_cap = bool(output.get("color_capable", True))
        smart_cap = bool(output.get("smart_capable", True))

        return Success(
            NightVisionStatus(
                current_type=curr,
                color_capable=color_cap,
                smart_capable=smart_cap,
            )
        )

    async def set_night_vision_type(self, nv_type: str, timeout: float = 8.0) -> CameraResult[bool]:
        """Set night vision rendering type (grey, color, smart)."""
        clean = nv_type.lower().strip()
        if clean not in NIGHT_VISION_TYPES:
            return Failure(
                kind=FailureKind.GENERIC,
                reason=f"Invalid night vision type '{nv_type}'. Must be one of {NIGHT_VISION_TYPES}",
            )

        payload = {"type": clean}
        res = await post_json(self.http, self.conn, "/nuraeye/video/night-vision", payload, timeout=timeout)
        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)
        return Success(True)

    async def get_mirror_flip(self, timeout: float = 8.0) -> CameraResult[str]:
        """Fetch current video mirror/flip mode (off, mirror, flip, both)."""
        res = await get_json(self.http, self.conn, "/nuraeye/video/mirror-flip", timeout=timeout)
        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)

        mode = res.output.get("mode") or "off"
        return Success(str(mode).lower())

    async def set_mirror_flip(self, mode: str, timeout: float = 8.0) -> CameraResult[bool]:
        """Update video mirror/flip mode."""
        clean = mode.lower().strip()
        if clean not in MIRROR_FLIP_MODES:
            return Failure(
                kind=FailureKind.GENERIC,
                reason=f"Invalid mirror/flip mode '{mode}'. Must be one of {MIRROR_FLIP_MODES}",
            )

        payload = {"mode": clean}
        res = await post_json(self.http, self.conn, "/nuraeye/video/mirror-flip", payload, timeout=timeout)
        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)
        return Success(True)

    async def get_anti_flicker(self, timeout: float = 8.0) -> CameraResult[str]:
        """Fetch anti-flicker frequency mode (50Hz, 60Hz, Auto)."""
        res = await get_json(self.http, self.conn, "/nuraeye/video/anti-flicker", timeout=timeout)
        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)

        mode = res.output.get("mode") or "Auto"
        return Success(str(mode))

    async def set_anti_flicker(self, mode: str, timeout: float = 8.0) -> CameraResult[bool]:
        """Update anti-flicker frequency mode (50Hz, 60Hz, Auto)."""
        # Case-insensitive match to accepted modes
        matched = next((m for m in ANTI_FLICKER_MODES if m.lower() == mode.lower().strip()), None)
        if matched is None:
            return Failure(
                kind=FailureKind.GENERIC,
                reason=f"Invalid anti-flicker mode '{mode}'. Must be one of {ANTI_FLICKER_MODES}",
            )

        payload = {"mode": matched}
        res = await post_json(self.http, self.conn, "/nuraeye/video/anti-flicker", payload, timeout=timeout)
        if isinstance(res, (Timeout, Failure)):
            return res
        if isinstance(res, RestError):
            return failure_from_rest(res)
        return Success(True)

    async def get_supported_timezones(self, timeout: float = 8.0) -> CameraResult[list[dict[str, str]]]:
        """Fetch catalog of supported timezones from camera or fallback catalog."""
        res = await get_json(self.http, self.conn, "/nuraeye/network/timezones", timeout=timeout)
        if isinstance(res, RestOk) and "timezones" in res.output:
            raw_list = res.output["timezones"]
            if isinstance(raw_list, list) and raw_list:
                return Success(raw_list)

        # Graceful fallback to standard Olson list if camera firmware lacks dedicated catalog endpoint
        return Success(FALLBACK_TIMEZONES)
