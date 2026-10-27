"""REST identity verification route for fake camera."""

import json
from typing import Any

from fake_camera.routes import route
from fake_camera.state import CameraState
from vizenlink_nvr.camera.wsse import compute_digest


@route("POST", "/nuraeye/identity")
async def handle_identity(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, dict[str, Any]]:
    """Handle /nuraeye/identity verification challenge."""
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return 400, {"error_code": 400, "error_msg": "Bad Request", "output": {}}

    nonce = data.get("nonce", "")
    created = data.get("created", "")
    digest = data.get("digest", "")

    expected_challenge = compute_digest(
        "are-you-onchip-nuraeye",
        nonce_b64=nonce,
        created=created,
    )

    if digest != expected_challenge:
        return 401, {"error_code": 401, "error_msg": "Unauthorized challenge", "output": {}}

    if state.genuine:
        reply_digest = compute_digest(
            "yes-i-am-onchip-nuraeye",
            nonce_b64=nonce,
            created=created,
        )
    else:
        reply_digest = "wrong-reply-digest"

    return 200, {
        "error_code": 0,
        "error_msg": "Success",
        "output": {"reply": reply_digest},
    }
