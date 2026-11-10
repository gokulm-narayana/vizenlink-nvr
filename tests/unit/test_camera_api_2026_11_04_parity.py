"""camera_api 2026-11-04 drop: parity of the NVR's Python mirrors (pulled 2026-11-10)."""

from __future__ import annotations

from vizenlink_nvr.camera.nuraeye.capabilities import Capabilities, parse_capabilities


def _base() -> dict:
    return {"wan_command_capable": True, "wan_live_view_capable": True}


def test_new_capability_fields_parse_like_dart() -> None:
    caps = parse_capabilities(
        {
            **_base(),
            "accelerometer_capable": True,
            "kvs_e2e_encryption": True,
            "supported_movement_sensitivities": ["low", "medium", 3, "high"],
            "movement_sensitivity_descriptions": ["Big moves", "Medium moves", "Small moves"],
        }
    )
    assert isinstance(caps, Capabilities)
    assert caps.accelerometer_capable is True
    assert caps.kvs_e2e_encryption is True
    # whereType<String>() drops non-strings
    assert caps.supported_movement_sensitivities == ["low", "medium", "high"]
    assert caps.movement_sensitivity_descriptions == ["Big moves", "Medium moves", "Small moves"]


def test_new_capability_fields_default_on_older_firmware() -> None:
    caps = parse_capabilities(
        {**_base(), "accelerometer_capable": "yes", "supported_movement_sensitivities": "low"}
    )
    assert isinstance(caps, Capabilities)
    assert caps.accelerometer_capable is False  # only a real boolean true counts
    assert caps.kvs_e2e_encryption is False
    assert caps.supported_movement_sensitivities == []
    assert caps.movement_sensitivity_descriptions == []


def _probe(scopes: str) -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        b'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
        b"<s:Body><d:ProbeMatches><d:ProbeMatch>"
        b"<d:XAddrs>https://192.168.1.50/onvif/device_service</d:XAddrs>"
        b"<d:Scopes>" + scopes.encode() + b"</d:Scopes>"
        b"</d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>"
    )


def test_discovery_mac_scope_matches_camera_api_normalize_mac() -> None:
    from vizenlink_nvr.camera.discovery.ws_discovery import parse_probe_matches

    for raw in ("00:E0:4C:0D:BB:59", "00-e0-4c-0d-bb-59", "00e04c0dbb59"):
        (dev,) = parse_probe_matches(_probe(f"onvif://www.onvif.org/MAC/{raw}"), "192.168.1.50")
        assert dev.mac_hint == "00:E0:4C:0D:BB:59"
    # Not 12 hex digits -> no hint (Dart normalizeMac returns null)
    (dev,) = parse_probe_matches(_probe("onvif://www.onvif.org/MAC/not-a-mac"), "192.168.1.50")
    assert dev.mac_hint is None
