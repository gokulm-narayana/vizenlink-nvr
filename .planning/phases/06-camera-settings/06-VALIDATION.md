# Phase 06: Camera Settings - Validation Strategy

**Date:** 2026-11-04  
**Status:** In Planning

## Validation Strategy Overview
Phase 06 validates that camera settings can be inspected, configured, and managed through standardized ONVIF and NuraEye wire protocols matching `camera_api` specifications:
1. Low-level ONVIF & NuraEye clients model and execute requests for identity, encoder configurations, imaging, OSD, reboot, and factory reset.
2. Settings Service validates requested changes against the camera's actual capability options, rejecting out-of-range values.
3. REST API endpoints (`/api/v1/cameras/{serial}/settings/*`) expose settings with RBAC enforcement and audit logging.
4. React UI renders capability-gated tabs and controls with confirmation dialogs for destructive actions.
5. End-to-end tracer validates the complete cycle and verifies against an expanded 13-step phase gate.

---

## Requirements Validation Matrix

| Requirement | Description | Test Type | Automated Test Target | Status |
|:---|:---|:---|:---|:---:|
| **SET-01** | Edit device identity (name, location, time zone, password) and view device information | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-02** | Edit video encoder settings per stream within camera's allowed ranges | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-03** | Edit imaging settings (brightness, contrast, day/night, IR, WDR, anti-flicker, mirror/flip) | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-04** | Configure OSD name and timestamp overlays | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-05** | Reboot a camera and handle reconnection | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-06** | Factory-reset camera with double confirmation (Soft and Hard) | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-07** | View camera health (uptime, reboot reason, clock sync, firmware) | Integration | `tests/integration/test_camera_settings_api.py` | Pending |
| **SET-08** | Settings screens only show options supported by camera capabilities | Unit / UI | `tests/unit/test_camera_settings_service.py` | Pending |
