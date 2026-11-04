# Phase 06: Camera Settings - Context & Architectural Boundaries

## Purpose
Phase 06 enables complete configuration and management of cameras connected to the VizenLink NVR directly from the web interface and API, adhering to `camera_api` semantics, capability-gated options, and audit trail compliance (SET-01 through SET-08).

## In Scope Requirements
- **SET-01**: Device Identity (name, location, time zone, password) and read-only Device Information (model, firmware, serial number, hardware ID).
- **SET-02**: Per-stream Video Encoder Settings (bitrate, frame rate, resolution, codec H.264/H.265, encoding profile, CBR/VBR, quality) within camera-advertised ranges.
- **SET-03**: Imaging & ISP Settings (brightness, contrast, saturation, sharpness, Day/Night IrCutFilter mode, Night Vision type, WDR, Anti-Flicker, Mirror/Flip).
- **SET-04**: OSD Overlays (timestamp and plain text overlay configuration).
- **SET-05**: Remote Camera Reboot with connectivity gap handling and automatic reconnect.
- **SET-06**: Factory Reset (Soft reset of user configuration, Hard reset of configuration and network) gated by Owner/Admin role with double confirmation.
- **SET-07**: Camera Health monitoring (uptime, reboot reason, clock sync status, firmware version).
- **SET-08**: Dynamic Capability Gating: only expose controls and option choices supported by the camera's hardware/firmware capabilities according to `contracts/camera_api/mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md`.

## Architectural Boundaries & Principles
1. **Source of Truth for Settings Semantics:**
   - All wire formats, parameter naming, and option boundaries match `contracts/camera_api/mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md`.
2. **Capability-Gated Controls:**
   - Controls are never hardcoded with assumptions (e.g. WDR is only rendered if `wdrSupported` is true; Night Vision type choices depend on `colorCapable`/`smartCapable`; encoder resolutions depend on `getProfiles()` and `getVideoEncoderConfigurationOptions()`).
3. **Safety & Destructive Gate:**
   - Reboot requires confirmation; Factory Reset requires double confirmation (mode selection, then explicit destructive warning) and is restricted to `owner` and `operator` (`RequireOperator`).
4. **Audit Trail Invariant:**
   - Every modification to camera settings (identity, encoder, imaging, OSD, password, reboot, reset) writes an immutable record to `audit_logs` table (`AUTH-04`).
