"""Ephemeral signed media token service for MediaMTX authorization (AUTH-03, AUTH-05, LIVE-01)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

DEFAULT_TOKEN_TTL_SECONDS = 900  # 15 minutes


def _b64url_encode(data: bytes) -> str:
    """Encode bytes as base64 URL-safe without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Decode base64 URL-safe string with padding restoration."""
    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("ascii"))


class MediaTokenService:
    """Issues and verifies short-lived cryptographically signed tokens for camera streams."""

    def __init__(self, secret: bytes | None = None) -> None:
        # If no secret provided, generate a secure random 256-bit instance secret
        self._secret = secret or secrets.token_bytes(32)

    def generate_token(
        self,
        user_id: int,
        camera_serial: str,
        stream: str,
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> str:
        """Generate a signed ephemeral token bound to a user, camera serial, and stream type."""
        now = int(time.time())
        exp = now + ttl_seconds
        payload = {
            "sub": user_id,
            "serial": camera_serial,
            "stream": stream,
            "exp": exp,
            "nonce": secrets.token_hex(8),
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = _b64url_encode(payload_bytes)

        sig = hmac.new(self._secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
        sig_b64 = _b64url_encode(sig)

        return f"{payload_b64}.{sig_b64}"

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify signature, expiry, and payload format of a media token.
        
        Returns the decoded payload dict if valid, or None if invalid/expired.
        """
        if not token or "." not in token:
            return None

        parts = token.split(".")
        if len(parts) != 2:
            return None

        payload_b64, sig_b64 = parts
        try:
            expected_sig = hmac.new(
                self._secret,
                payload_b64.encode("ascii"),
                hashlib.sha256,
            ).digest()
            actual_sig = _b64url_decode(sig_b64)

            if not hmac.compare_digest(expected_sig, actual_sig):
                return None

            payload_bytes = _b64url_decode(payload_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            return None

        # Verify required keys
        if not isinstance(payload, dict):
            return None
        for key in ("sub", "serial", "stream", "exp"):
            if key not in payload:
                return None

        # Check expiration
        now = int(time.time())
        if now > payload["exp"]:
            return None

        return payload


# Global instance with process-wide secret
default_media_token_service = MediaTokenService()

