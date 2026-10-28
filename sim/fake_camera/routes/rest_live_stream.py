"""REST live stream URI route for fake camera."""

import json
from typing import Any

from fake_camera.routes import route
from fake_camera.routes.rest_session import rest_settings
from fake_camera.state import CameraState

PROFILE_MAP: dict[str, tuple[int, str]] = {
    "Profile_1": (554, "/high"),
    "Profile_2": (555, "/medium"),
    "Profile_3": (556, "/mobile"),
}


@route("POST", "/nuraeye/live-stream-uri")
async def handle_live_stream_uri(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /nuraeye/live-stream-uri."""
    from fake_camera.server import require_bearer

    acc, err = require_bearer(state, headers, "/nuraeye/live-stream-uri")
    if err is not None:
        return err

    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return 400, {"error_code": 400, "error_msg": "Invalid JSON body"}

    profile_token = data.get("profile_token")
    if profile_token not in PROFILE_MAP:
        return 400, {"error_code": 400, "error_msg": "Unknown profile token"}

    host = "127.0.0.1"
    for name, val in headers:
        if name.lower() == b"host":
            host = val.decode("latin1").split(":")[0]
            break

    settings = rest_settings(state)
    if settings.live_stream_mode == "webrtc":
        return 200, {
            "error_code": 0,
            "error_msg": "Success",
            "output": {
                "transport": "webrtc",
                "port": 8444,
                "path": "/webrtc",
                "url": f"http://{host}:8444/webrtc",
            },
        }

    port, path = PROFILE_MAP[str(profile_token)]
    return 200, {
        "error_code": 0,
        "error_msg": "Success",
        "output": {
            "transport": "rtsp",
            "port": port,
            "path": path,
            "url": f"rtsps://{host}:{port}{path}",
        },
    }
