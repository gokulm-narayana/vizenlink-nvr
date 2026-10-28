# mirrors: mobile_app/packages/camera_api/lib/src/lan/nuraeye/rest_identity_discovery_client.dart@49ec7db1d149
"""Data models for NuraEye REST operations and authenticated sessions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoginInfo:
    """Authentication result metadata without exposing raw bearer token."""

    username: str
    role: str | None
    password_change_required: bool
    expires_in_sec: int
