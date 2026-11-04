# Plan 06-02 Summary: Camera Settings Service & REST API

## Outcome
Implemented the business service `CameraSettingsService` and REST API endpoints (`/api/v1/cameras/{serial}/settings/*`, `/reboot`, `/factory-reset`, `/health`), enforcing capability gating, options bounds validation, RBAC authorization, and append-only audit logging.

## Deliverables
1. **CameraSettingsService (`src/vizenlink_nvr/services/camera_settings.py`):**
   - High-level coordinator that securely decrypts credentials via `Vault`, communicates with camera clients (`OnvifDeviceClient`, `OnvifMedia2Client`, `OnvifImagingClient`, `NuraeyeSettingsClient`).
   - Implemented strict capability and bounds validation:
     - Rejects unsupported codecs, resolutions, and out-of-range framerates, bitrates, quality, and GOV lengths.
     - Gates WDR toggle on `wdr_supported` flag.
     - Gates color/smart night vision on `color_capable`/`smart_capable` sensor support flags.
     - Enforces anti-flicker and mirror/flip valid sets.
   - Appends audit events for every setting change, reboot, and factory reset (`AuditLog`).
2. **REST API Router (`src/vizenlink_nvr/api/v1/camera_settings.py`):**
   - `GET /api/v1/cameras/{serial}/settings`: Returns full capability-gated settings state (Viewer access with camera scoping).
   - `PUT /api/v1/cameras/{serial}/settings/identity`: Updates name, location, timezone, password (Operator/Owner required).
   - `PUT /api/v1/cameras/{serial}/settings/encoder`: Updates stream video encoder configuration within validated capability options (Operator/Owner required).
   - `PUT /api/v1/cameras/{serial}/settings/imaging`: Updates Day/Night mode, WDR, ISP sliders, mirror/flip, anti-flicker (Operator/Owner required).
   - `PUT /api/v1/cameras/{serial}/settings/osd`: Updates timestamp and text overlays (Operator/Owner required).
   - `POST /api/v1/cameras/{serial}/reboot`: Initiates camera reboot (Operator/Owner required).
   - `POST /api/v1/cameras/{serial}/factory-reset`: Initiates Soft or Hard factory reset with confirmation keyword check (Operator/Owner required).
   - `GET /api/v1/cameras/{serial}/health`: Reports uptime, reboot reason, online state, and clock sync status.
3. **Application Registration & Contract Baseline (`src/vizenlink_nvr/api/app.py`, `contracts/openapi_v1_baseline.json`):**
   - Registered `camera_settings_router` in `/api/v1`.
   - Updated OpenAPI contract baseline via `tools/check_api_breaking_changes.py --update`.
4. **Integration Verification (`tests/integration/test_camera_settings_api.py`):**
   - 6 integration tests covering aggregated query, identity mutation & audit, encoder bounds validation, imaging WDR capability gate, reboot & factory reset, and RBAC isolation. All passed 100%.

## Verification
- `uv run pytest tests/integration/test_camera_settings_api.py -v`: 6 passed in 17.56s.
- `uv run python tools/check_api_breaking_changes.py`: Success: OpenAPI schema is backward-compatible with baseline.
- `uv run ruff check src/vizenlink_nvr/services/camera_settings.py src/vizenlink_nvr/api/v1/camera_settings.py src/vizenlink_nvr/api/app.py tests/integration/test_camera_settings_api.py`: All checks passed.
- `uv run mypy src/vizenlink_nvr/services/camera_settings.py src/vizenlink_nvr/api/v1/camera_settings.py src/vizenlink_nvr/api/app.py`: Success: no issues found.
