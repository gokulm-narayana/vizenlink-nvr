"""Permissive negative-control MediaMTX configuration builder for testing."""

from __future__ import annotations

from typing import Any

from vizenlink_nvr.media.config import MediaMtxPorts, build_config


def build_permissive_config(ports: MediaMtxPorts) -> dict[str, Any]:
    """Build MediaMTX configuration with default open 'any' users (negative control)."""
    cfg = build_config(ports, "sha256:dummy", auth_method="internal")
    cfg["authInternalUsers"] = [
        {
            "user": "any",
            "pass": "",
            "ips": [],
            "permissions": [
                {"action": "publish"},
                {"action": "read"},
                {"action": "playback"},
            ],
        },
        {
            "user": "any",
            "pass": "",
            "ips": ["127.0.0.1/32", "::1/128"],
            "permissions": [
                {"action": "api"},
                {"action": "metrics"},
                {"action": "pprof"},
            ],
        },
    ]
    return cfg
