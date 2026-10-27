# mirrors: mobile_app/packages/camera_api/lib/src/lan/wsse_digest.dart@103b118108cc
"""WS-Security UsernameToken password digest and nonce generation."""

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime

from vizenlink_nvr.timeutil import UTC, Clock


def created_from(dt: datetime) -> str:
    """Format datetime into ISO-8601 string ending in .000Z."""
    aware_utc = dt.astimezone(UTC)
    return aware_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def new_nonce_b64() -> str:
    """Generate 16 random cryptographically secure bytes base64 encoded."""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def compute_digest(plaintext: str, *, nonce_b64: str, created: str) -> str:
    """Compute WS-UsernameToken PasswordDigest: Base64(SHA-1(raw_nonce + created_utf8 + password_utf8))."""
    raw_nonce = base64.b64decode(nonce_b64)
    raw = raw_nonce + created.encode("utf-8") + plaintext.encode("utf-8")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")  # noqa: S324


@dataclass(frozen=True)
class WsseToken:
    """A generated WS-UsernameToken authentication tuple."""

    nonce_b64: str
    created: str
    digest: str


def make_token(plaintext: str, clock: Clock) -> WsseToken:
    """Create a fresh WSSE token using current time from the provided Clock."""
    nonce_b64 = new_nonce_b64()
    created = created_from(clock.now())
    digest = compute_digest(plaintext, nonce_b64=nonce_b64, created=created)
    return WsseToken(nonce_b64=nonce_b64, created=created, digest=digest)
