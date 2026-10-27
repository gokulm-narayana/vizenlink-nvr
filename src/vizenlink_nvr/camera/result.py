# mirrors: mobile_app/packages/camera_api/lib/src/camera_result.dart@eaa81aa28a68
"""Typed result union and failure classifications for camera operations."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class FailureKind(StrEnum):
    """Categorized root causes of camera operation failures."""

    GENERIC = "generic"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    BLOCKED = "blocked"
    PASSWORD_CHANGE_REQUIRED = "password_change_required"  # noqa: S105
    CREDENTIALS_MISSING = "credentials_missing"
    ID_MISMATCH = "id_mismatch"
    UNREACHABLE = "unreachable"
    BAD_RESPONSE = "bad_response"
    TLS_CHANGED = "tls_changed"


@dataclass(frozen=True)
class Success(Generic[T]):
    """Successful camera outcome wrapping payload value."""

    value: T


@dataclass(frozen=True)
class Failure:
    """Classified failure outcome with reason and optional metadata."""

    kind: FailureKind
    reason: str
    http_status: int | None = None
    retry_after: timedelta | None = None
    fault_subcode: str | None = None


@dataclass(frozen=True)
class Timeout:
    """Distinct outcome for connection or read timeouts."""

    reason: str = "timeout"


CameraResult = Success[T] | Failure | Timeout

_RETRY_REGEX = re.compile(r"retry in (\d+)\s*s", re.IGNORECASE)


def parse_retry_after(body: Mapping[str, Any] | None, message: str) -> timedelta | None:
    """Parse lockout delay from body dictionary or error message regex."""
    if body and "retry_after_seconds" in body:
        try:
            sec = int(body["retry_after_seconds"])
            return timedelta(seconds=sec)
        except (ValueError, TypeError):
            pass

    match = _RETRY_REGEX.search(message)
    if match:
        try:
            return timedelta(seconds=int(match.group(1)))
        except (ValueError, TypeError):
            pass

    return None
