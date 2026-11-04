"""Unit tests for mobile pairing and device management UI formatting logic (MOB-03)."""

from __future__ import annotations

import re


def format_pairing_code(code: str) -> str:
    """Mirrors MobilePairingModal formatCode helper."""
    chunks = re.findall(r".{1,4}", code)
    return "-".join(chunks) if chunks else code


def parse_qr_uri(uri: str) -> dict[str, str]:
    """Parse vizenlink://pair QR payload."""
    assert uri.startswith("vizenlink://pair?")
    query = uri.split("?", 1)[1]
    params: dict[str, str] = {}
    for part in query.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v
    return params


def get_platform_icon(platform: str) -> str:
    """Mirrors PairedDevicesView platform icon helper."""
    return "🍏" if platform.lower() == "ios" else "🤖"


def test_pairing_code_chunking() -> None:
    """Ensure 32-hex pairing code splits cleanly into 8 4-char groups."""
    raw = "0123456789abcdef0123456789abcdef"
    formatted = format_pairing_code(raw)
    assert formatted == "0123-4567-89ab-cdef-0123-4567-89ab-cdef"
    assert len(formatted.split("-")) == 8


def test_qr_payload_parsing() -> None:
    """Ensure QR payload adheres to vizenlink://pair schema with code and expires."""
    code = "abcdef1234567890abcdef1234567890"
    exp = 1793788000
    uri = f"vizenlink://pair?code={code}&expires={exp}"
    params = parse_qr_uri(uri)
    assert params["code"] == code
    assert params["expires"] == str(exp)


def test_platform_icon_resolution() -> None:
    """Ensure platform icon resolution returns expected emojis."""
    assert get_platform_icon("ios") == "🍏"
    assert get_platform_icon("iOS") == "🍏"
    assert get_platform_icon("android") == "🤖"
    assert get_platform_icon("unknown") == "🤖"

