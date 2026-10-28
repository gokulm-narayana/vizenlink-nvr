"""REST capabilities route for fake camera."""

from typing import Any

from fake_camera.routes import route
from fake_camera.routes.rest_session import rest_settings
from fake_camera.state import CameraState


@route("GET", "/nuraeye/capabilities")
async def handle_capabilities(
    state: CameraState,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /nuraeye/capabilities endpoint."""
    from fake_camera.server import require_bearer

    acc, err = require_bearer(state, headers, "/nuraeye/capabilities")
    if err is not None:
        return err

    settings = rest_settings(state)
    return 200, {
        "error_code": 0,
        "error_msg": "Success",
        "output": settings.capabilities,
    }
