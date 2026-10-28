# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/live_stream_uri_client.dart@1540cb0
"""Live stream URI models and parser for NuraEye cameras."""

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from vizenlink_nvr.camera.result import Failure, FailureKind

MAIN_PROFILE_TOKEN = "Profile_1"  # noqa: S105
SUB_PROFILE_TOKEN = "Profile_2"  # noqa: S105
MOBILE_ONLY_PROFILE_TOKEN = "Profile_3"  # noqa: S105


@dataclass(frozen=True)
class LiveStreamUri:
    """Resolved live stream target for a video profile."""

    transport: Literal["rtsp", "webrtc"]
    port: int
    url: str
    scheme: str
    path: str


def parse_live_stream_uri(output: dict[str, Any]) -> LiveStreamUri | Failure:
    """Validate and parse /nuraeye/live-stream-uri output payload."""
    transport = output.get("transport")
    port = output.get("port")
    raw_url = output.get("url")

    if not isinstance(transport, str) or not isinstance(port, int) or not isinstance(raw_url, str):
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"GetLiveStreamUri response missing transport/port/url fields: {output}",
        )

    if transport not in ("rtsp", "webrtc"):
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"GetLiveStreamUri response has unknown transport: {transport}",
        )

    if raw_url.startswith("::"):
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"Unparseable media url: {raw_url}",
        )

    try:
        parsed = urlsplit(raw_url)
    except Exception as exc:
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"Unparseable media url: {raw_url} ({exc})",
        )

    if not parsed.scheme or parsed.scheme not in ("rtsp", "rtsps", "http", "https"):
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason=f"Unparseable media url: {raw_url}",
        )

    url_path = parsed.path
    if not url_path and isinstance(output.get("path"), str):
        url_path = str(output["path"])

    return LiveStreamUri(
        transport=transport,  # type: ignore[arg-type]
        port=port,
        url=raw_url,
        scheme=parsed.scheme,
        path=url_path,
    )
