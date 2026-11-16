"""Capability-gated access to the camera's complete documented LAN REST surface."""

from __future__ import annotations

import asyncio
import copy
import json
import math
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.media2 import MEDIA2_NAMESPACE, OnvifMedia2Client
from vizenlink_nvr.camera.onvif.soap import parse_xml, post_soap
from vizenlink_nvr.camera.result import CameraResult, Failure, Success, Timeout
from vizenlink_nvr.secrets.vault import CredentialsUnreadable, Vault
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.camera_settings import CameraSettingsService
from vizenlink_nvr.services.registry import load_connection

CATALOG = json.loads((Path(__file__).parent.parent / "camera/nuraeye/operation_catalog.json").read_text())
OPERATIONS = CATALOG["operations"]
INTERNAL = {
    "identityChallenge": "Device identification during onboarding",
    "sessionLogin": "Server-side camera session management",
    "sessionLogout": "Server-side camera session management",
    "getPreviewKey": "Encryption key stays on the server; never returned to the browser",
    "getCloudParameters": "Cloud connection credentials stay on the server",
}
GROUPS: dict[str, dict[str, Any]] = {
    "privacy": {
        "title": "Privacy",
        "description": "Pause capture or use privacy zones.",
        "operations": ["getPrivacyMode", "setPrivacyMode"],
    },
    "detection": {
        "title": "Detection & alerts",
        "description": "Choose detected events and automatic responses.",
        "operations": [
            "getEventPreferences",
            "setEventPreferences",
            "getEventResponseActions",
            "setEventResponseActions",
            "getLoiteringDuration",
            "setLoiteringDuration",
            "getBboxOverlay",
            "setBboxOverlay",
            "queryAlertRule",
            "setAlertRule",
        ],
    },
    "audio": {
        "title": "Audio",
        "description": "Microphone gain, speaker volume and audio recording.",
        "operations": [
            "getAudioSettings",
            "setAudioSettings",
            "getAudioRecording",
            "setAudioRecording",
            "getTestSoundStatus",
            "setTestSound",
            "getBuzzerStatus",
            "setBuzzer",
        ],
    },
    "camera-storage": {
        "title": "Camera SD card",
        "description": "Manage storage inside the camera, separately from NVR recording.",
        "operations": [
            "getLocalStorage",
            "setLocalStorage",
            "getRecordingMode",
            "setRecordingMode",
            "getRecordingClipDuration",
            "setRecordingClipDuration",
            "getRecordings",
            "getRecordingDates",
            "deleteRecordings",
        ],
    },
    "deterrence": {
        "title": "Siren & spotlight",
        "description": "Control deterrence actions and their automatic stop times.",
        "operations": [
            "getDeterrenceStatus",
            "setDeterrence",
            "getDeterrenceDurations",
            "setDeterrenceDurations",
            "getDeterrenceDurationOptions",
        ],
    },
    "movement": {
        "title": "Movement protection",
        "description": "Detect camera movement and calibrate its normal position.",
        "operations": [
            "getMovementProtection",
            "setMovementProtectionSensitivity",
            "calibrateMovementProtection",
        ],
    },
    "network": {
        "title": "Network",
        "description": "Inspect Wi-Fi and configure the camera's wireless network.",
        "operations": ["getWifi", "setWifi", "getWifiSignal", "getTimezones"],
    },
    "connections": {
        "title": "Camera connections",
        "description": "Inspect live and talk transport details, night vision state and device health.",
        "operations": [
            "getCapabilities",
            "getDeviceHealth",
            "getVideoMode",
            "getImageDefaults",
            "getNightVisionType",
            "setNightVisionType",
            "getMirrorFlip",
            "setMirrorFlip",
            "getAntiFlickerMode",
            "setAntiFlickerMode",
            "getLiveStreamUri",
            "getTalkUri",
            "getCloudStreamingStatus",
            "stopCloudStreaming",
        ],
    },
}
READ_COMMANDS = {"queryAlertRule", "getLiveStreamUri", "getTalkUri"}
OWNER_ONLY = {
    "setWifi",
    "deleteRecordings",
    "stopCloudStreaming",
    "setLocalStorage",
    "setRecordingMode",
    "setRecordingClipDuration",
}
CONFIRM = {
    "setWifi",
    "deleteRecordings",
    "setDeterrence",
    "setTestSound",
    "setBuzzer",
    "calibrateMovementProtection",
    "setPrivacyMode",
    "stopCloudStreaming",
}
CAPABILITY = {
    **dict.fromkeys(
        [
            "getLocalStorage",
            "setLocalStorage",
            "getRecordingMode",
            "setRecordingMode",
            "getRecordingClipDuration",
            "setRecordingClipDuration",
            "getRecordings",
            "getRecordingDates",
            "deleteRecordings",
        ],
        "local_storage_capable",
    ),
    **dict.fromkeys(
        ["getMovementProtection", "setMovementProtectionSensitivity", "calibrateMovementProtection"],
        "accelerometer_capable",
    ),
    **dict.fromkeys(["getBboxOverlay", "setBboxOverlay"], "bbox_overlay_capable"),
}
SENSITIVE = {"password", "psk", "token", "secret", "preview_key", "access_key", "secret_key", "authorization"}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not any(word in k.lower() for word in SENSITIVE)}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and "://" in value:
        parsed = urlsplit(value)
        if parsed.username or parsed.password:
            host = f"[{parsed.hostname}]" if ":" in (parsed.hostname or "") else parsed.hostname or ""
            return urlunsplit(
                (parsed.scheme, host + (f":{parsed.port}" if parsed.port else ""), parsed.path, "", "")
            )
    return value


def validate(value: Any, schema: dict[str, Any], path: str = "settings") -> None:
    """Validate the finite JSON-schema vocabulary used by the pinned camera contract."""
    kind = schema.get("type")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in (int, float),
    }
    if kind and not valid.get(kind, False):
        raise HTTPException(422, f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise HTTPException(422, f"{path}: choose one of {schema['enum']}")
    if type(value) in (int, float):
        if (
            not math.isfinite(value)
            or value < schema.get("minimum", -math.inf)
            or value > schema.get("maximum", math.inf)
        ):
            raise HTTPException(422, f"{path}: value outside the supported range")
    if isinstance(value, str) and len(value) > schema.get("maxLength", 4096):
        raise HTTPException(422, f"{path}: text is too long")
    if isinstance(value, list):
        if len(value) > 500:
            raise HTTPException(422, f"{path}: too many items")
        for i, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(value, dict):
        if len(value) < schema.get("minProperties", 0):
            raise HTTPException(422, f"{path}: provide at least one setting")
        for key in schema.get("required", []):
            if key not in value:
                raise HTTPException(422, f"{path}: {key} is required")
        for key, item in value.items():
            field = schema.get("properties", {}).get(key, schema.get("additionalProperties", False))
            if field is False:
                raise HTTPException(422, f"{path}: unknown setting {key}")
            validate(item, field if isinstance(field, dict) else {}, f"{path}.{key}")


T = TypeVar("T")


def require_success(result: CameraResult[T]) -> T:
    if isinstance(result, Timeout):
        raise HTTPException(504, "The camera timed out. Check its connection and try again.")
    if isinstance(result, Failure):
        code = result.http_status if result.http_status in (401, 403, 404, 409, 422, 428, 429) else 502
        # A camera 401 must not be mistaken for an expired NVR login.
        if code == 401:
            code = 502
        raise HTTPException(code, result.reason)
    if not isinstance(result, Success):
        raise HTTPException(502, "The camera returned an unexpected response.")
    return result.value


async def camera_connection(db: AsyncSession, vault: Vault, serial: str) -> CameraConnection:
    """Return actionable setup errors without exposing encrypted credential details."""
    from vizenlink_nvr.db.models import Camera

    if await db.get(Camera, serial) is None:
        raise HTTPException(404, "Camera not found")
    try:
        return await load_connection(db, vault, serial)
    except (NoResultFound, CredentialsUnreadable) as exc:
        raise HTTPException(
            503, "Camera credentials are unavailable. Reconnect this camera in Devices."
        ) from exc


class CameraFeaturesService:
    def __init__(self, settings: CameraSettingsService) -> None:
        self.settings = settings
        self.locks: dict[str, asyncio.Lock] = {}

    async def client(self, db: AsyncSession, vault: Vault, serial: str) -> NuraeyeClient:
        conn = await camera_connection(db, vault, serial)
        return NuraeyeClient(conn, self.settings.http, self.settings.clock, sessions=self.settings.sessions)

    async def hardware(self, client: NuraeyeClient) -> dict[str, bool]:
        media = OnvifMedia2Client(client.conn, self.settings.http, self.settings.clock)
        endpoint = require_success(await media.resolve_endpoint())
        flags = {}
        for operation, token, key in [
            ("GetAudioSourceConfigurations", "AudioSourceCfg_1", "has_microphone"),
            ("GetAudioOutputConfigurations", "AudioOutputCfg_1", "has_speaker"),
        ]:
            result = require_success(
                await post_soap(
                    self.settings.http,
                    client.conn,
                    endpoint,
                    f'<tr2:{operation} xmlns:tr2="{MEDIA2_NAMESPACE}">'
                    f"<tr2:ConfigurationToken>{token}</tr2:ConfigurationToken></tr2:{operation}>",
                    clock=self.settings.clock,
                    timeout=8,
                )
            )
            flags[key] = parse_xml(result).find(".//{*}Configurations") is not None
        return flags

    def catalog(self, group: str) -> dict[str, Any]:
        if group not in GROUPS:
            raise HTTPException(404, "Unknown camera settings section")
        return {
            **GROUPS[group],
            "group": group,
            "source": CATALOG["source"],
            "operations": [
                {
                    "id": op,
                    **copy.deepcopy(OPERATIONS[op]),
                    "read_only": OPERATIONS[op]["method"] == "GET" or op in READ_COMMANDS,
                    "owner_only": op in OWNER_ONLY,
                    "confirmation_required": op in CONFIRM,
                    "capability": CAPABILITY.get(op),
                }
                for op in GROUPS[group]["operations"]
            ],
        }

    async def state(self, db: AsyncSession, vault: Vault, serial: str, group: str) -> dict[str, Any]:
        catalog = self.catalog(group)
        client = await self.client(db, vault, serial)
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        async with self.locks.setdefault(serial, asyncio.Lock()):
            caps = require_success(await client.request("GET", "/nuraeye/capabilities"))
            if group == "audio":
                caps.update(await self.hardware(client))
            for op in catalog["operations"]:
                gate = CAPABILITY.get(op["id"])
                if gate and caps.get(gate) is not True:
                    continue
                if op["method"] != "GET" or op["query"] or op["id"] == "getCapabilities":
                    continue
                result = await client.request("GET", op["path"])
                if isinstance(result, Success):
                    values[op["id"]] = sanitize(result.value)
                else:
                    errors[op["id"]] = result.reason
        return {**catalog, "capabilities": sanitize(caps), "values": values, "errors": errors}

    async def execute(
        self,
        db: AsyncSession,
        vault: Vault,
        serial: str,
        operation: str,
        payload: dict[str, Any],
        query: dict[str, Any],
        user: Any,
        confirmation: str | None,
    ) -> dict[str, Any]:
        if operation in INTERNAL or operation not in {o for g in GROUPS.values() for o in g["operations"]}:
            raise HTTPException(404, "Camera operation is not exposed to the browser")
        op = OPERATIONS[operation]
        read_only = op["method"] == "GET" or operation in READ_COMMANDS
        if not read_only and user.role not in ("owner", "operator"):
            raise HTTPException(403, "Camera changes require Operator or Owner access")
        if operation in OWNER_ONLY and user.role != "owner":
            raise HTTPException(403, "This camera operation requires the NVR owner")
        if operation in CONFIRM and confirmation != serial:
            raise HTTPException(409, "Review and confirm this camera action first")
        validate(payload, op["schema"])
        validate(query, {"type": "object", "properties": op["query"]})
        client = await self.client(db, vault, serial)
        async with self.locks.setdefault(serial, asyncio.Lock()):
            caps = require_success(await client.request("GET", "/nuraeye/capabilities"))
            gate = CAPABILITY.get(operation)
            if gate and caps.get(gate) is not True:
                raise HTTPException(422, "This camera does not support the requested feature")
            self.validate_capabilities(operation, payload, caps)
            if operation == "setDeterrenceDurations":
                ranges = require_success(await client.request("GET", "/nuraeye/deterrence/durations/options"))
                for field, value in payload.items():
                    capability = field.split("_")[0] + "_capable"
                    if caps.get(capability) is not True:
                        raise HTTPException(422, "This camera does not support this deterrence output")
                    low, high = ranges.get(field + "_min"), ranges.get(field + "_max")
                    if type(low) is not int or type(high) is not int or not low <= value <= high:
                        raise HTTPException(
                            422, "Choose a camera-reported deterrence duration or repeat count"
                        )
            if operation in ("setAudioSettings", "setAudioRecording", "setTestSound"):
                flags = await self.hardware(client)
                if (
                    operation == "setAudioSettings"
                    and "mic_gain" in payload
                    or operation == "setAudioRecording"
                ) and not flags["has_microphone"]:
                    raise HTTPException(422, "This camera does not report a microphone")
                if (
                    operation == "setAudioSettings"
                    and "speaker_volume" in payload
                    or operation == "setTestSound"
                ) and not flags["has_speaker"]:
                    raise HTTPException(422, "This camera does not report a speaker")
            path = op["path"] + ("?" + urlencode(query) if query else "")
            result = require_success(await client.request(op["method"], path, payload, timeout=15))
        if not read_only:
            await AuditService.record_event(
                session=db,
                action=f"camera.api.{operation}",
                resource_type="camera",
                resource_id=serial,
                actor_id=user.id,
                actor_username=user.username,
                details={"fields": list(payload)},
                commit=True,
            )
        return {"status": "ok", "operation": operation, "output": sanitize(result)}

    @staticmethod
    def validate_capabilities(operation: str, payload: dict[str, Any], caps: dict[str, Any]) -> None:
        # Only an explicit `buzzer_capable: false` refuses: the flag is requested from the
        # camera_api owner and absent on current firmware (absent = unknown, allow).
        wants_buzzer = operation == "setBuzzer" or (
            operation == "setAlertRule" and payload.get("buzzer_activation") is True
        )
        if caps.get("buzzer_capable") is False and wants_buzzer:
            raise HTTPException(422, "This camera does not have a buzzer")
        for op, field, capability in [
            ("setMovementProtectionSensitivity", "sensitivity", "supported_movement_sensitivities"),
            ("setRecordingMode", "mode", "supported_recording_modes"),
        ]:
            if operation == op and payload.get(field) not in caps.get(capability, []):
                raise HTTPException(422, f"{field} is not supported by this camera")
        for op, field, prefix in [
            ("setLoiteringDuration", "loitering_duration_seconds", "loitering_duration"),
            ("setRecordingClipDuration", "clip_duration_seconds", "recording_clip_duration"),
        ]:
            if operation == op:
                low, high = caps.get(f"{prefix}_min_seconds"), caps.get(f"{prefix}_max_seconds")
                if not isinstance(low, int) or not isinstance(high, int) or not low <= payload[field] <= high:
                    raise HTTPException(422, "Value is outside the camera-reported supported range")
        if operation in ("setEventPreferences", "setEventResponseActions"):
            for event, value in payload.items():
                supported = (
                    caps.get("supported_event_types", [])
                    if operation == "setEventPreferences"
                    else caps.get("supported_event_deterrence_options", {})
                )
                if event not in supported:
                    raise HTTPException(422, f"Event type {event} is not supported by this camera")
                if operation == "setEventResponseActions" and any(
                    a not in caps.get("supported_event_deterrence_options", {}).get(event, []) for a in value
                ):
                    raise HTTPException(422, f"A response action is not supported for {event}")
        if operation == "setDeterrence" and caps.get(f"{payload['action']}_capable") is not True:
            raise HTTPException(422, "This deterrence action is not supported by the camera")
        if operation == "setNightVisionType" and payload["type"] in ("Color", "Smart"):
            if caps.get(f"night_vision_{payload['type'].lower()}_capable") is not True:
                raise HTTPException(422, "This night vision type is not supported by the camera")
        if (
            operation == "setBuzzer"
            and payload.get("active")
            and not 1 <= payload.get("duration_seconds", 0) <= 255
        ):
            raise HTTPException(422, "Provide a buzzer duration between 1 and 255 seconds")
        if operation == "deleteRecordings" and not payload.get("delete_all") and not payload.get("ids"):
            raise HTTPException(422, "Choose clips to delete or explicitly select delete all")
        if operation == "setRecordingMode" and payload.get("mode") == "scheduled":
            schedule = payload.get("schedule", [])
            if not schedule or len(schedule) > caps.get("max_recording_schedule_windows", 14):
                raise HTTPException(422, "Provide a supported number of recording schedule windows")
            for window in schedule:
                if (
                    not {"day_of_week", "start_minute", "end_minute"} <= window.keys()
                    or window["end_minute"] <= window["start_minute"]
                ):
                    raise HTTPException(422, "Each schedule needs a day and an end minute after its start")
