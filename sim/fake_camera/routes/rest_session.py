"""REST session login route and settings for fake camera."""

import json
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fake_camera.routes import route
from fake_camera.state import CameraState


def _load_default_capabilities() -> dict[str, Any]:
    fixture_path = (
        Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "nuraeye" / "capabilities_full.json"
    )
    if fixture_path.exists():
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        output = data.get("data", {}).get("output", {})
        return dict(output)
    return {}


@dataclass
class RestSimSettings:
    """Configurable REST behavior settings per simulated camera instance."""

    capabilities: dict[str, Any] = field(default_factory=_load_default_capabilities)
    live_stream_mode: Literal["rtsp", "webrtc"] = "rtsp"
    expires_in_sec: int = 1800


_SETTINGS: weakref.WeakKeyDictionary[Any, RestSimSettings] = weakref.WeakKeyDictionary()


def rest_settings(camera: Any) -> RestSimSettings:
    """Retrieve or initialize RestSimSettings for a FakeCamera or CameraState."""
    state = getattr(camera, "state", camera)
    settings = getattr(state, "_rest_settings", None)
    if settings is None:
        try:
            settings = _SETTINGS.get(camera)
        except TypeError:
            settings = None

    if settings is None:
        settings = RestSimSettings()

    try:
        _SETTINGS[camera] = settings
    except TypeError:
        pass

    try:
        state._rest_settings = settings
    except (AttributeError, TypeError):
        pass

    return settings


@route("POST", "/nuraeye/session/login")
async def handle_login(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, dict[str, Any]]:
    """Handle /nuraeye/session/login authentication request."""
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return 400, {"error_code": 400, "error_msg": "Bad Request", "output": {}}

    if not isinstance(data, dict) or "auth_credentials" not in data:
        return 400, {"error_code": 400, "error_msg": "Bad Request", "output": {}}

    creds = data["auth_credentials"]
    if not isinstance(creds, dict):
        return 400, {"error_code": 400, "error_msg": "Bad Request", "output": {}}

    username = str(creds.get("username", ""))
    digest = str(creds.get("password_digest") or creds.get("digest") or "")
    nonce = str(creds.get("nonce", ""))
    created = str(creds.get("created", ""))

    blocked_sec = state.blocked_for(username)
    if blocked_sec is not None:
        return 429, {
            "error_code": 429,
            "error_msg": f"Too many failed sign-in attempts (retry in {blocked_sec} s)",
            "retry_after_seconds": blocked_sec,
            "reason": "too_many_attempts",
            "output": {},
        }

    from vizenlink_nvr.camera.wsse import compute_digest

    acc = state.accounts.get(username)
    expected_digest = compute_digest(acc.password, nonce_b64=nonce, created=created) if acc else ""
    factory_digest = compute_digest("password", nonce_b64=nonce, created=created)

    if "digest" not in creds:
        acc, _ = state.verify_rest_login(
            username=username,
            digest=digest,
            nonce=nonce,
            created=created,
        )
    else:
        # server.py line 219 already ran verify_rest_login for credential classification
        if not digest or (digest != expected_digest and digest != factory_digest):
            acc = None

    if acc is None:
        blocked_now = state.blocked_for(username)
        if blocked_now is not None:
            return 429, {
                "error_code": 429,
                "error_msg": f"Too many failed sign-in attempts (retry in {blocked_now} s)",
                "retry_after_seconds": blocked_now,
                "reason": "too_many_attempts",
                "output": {},
            }
        return 401, {"error_code": 401, "error_msg": "Invalid credentials", "output": {}}

    settings = rest_settings(state)
    # If simulator configured expires_in_sec == 0, keep token active in sim state so bearer check passes
    sim_token_expires = 1800 if settings.expires_in_sec == 0 else settings.expires_in_sec
    token = state.issue_token(
        username=username,
        role=acc.role,
        expires_in_sec=sim_token_expires,
    )

    role_str = acc.role.name.capitalize() if hasattr(acc.role, "name") else str(acc.role)

    return 200, {
        "error_code": 0,
        "error_msg": "Success",
        "output": {
            "token": token,
            "expires_in_sec": settings.expires_in_sec,
            "username": username,
            "role": role_str,
            "password_change_required": state.first_password_gate,
        },
    }
