# Plan 01-18 Summary: REST Login and Authenticated Capabilities Tracer

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Tracer: authenticated GET /nuraeye/capabilities end-to-end (login -> bearer -> typed Capabilities)**
   - Created `src/vizenlink_nvr/camera/nuraeye/sessions.py` implementing `Session` and `NuraeyeSessionCache` with TTL expiry checks, 15s leeway, idle extension, and `single_flight` login deduplication (SES-01..06).
   - Created `src/vizenlink_nvr/camera/nuraeye/models.py` defining `LoginInfo` without exposing the raw bearer token (D-14).
   - Updated `src/vizenlink_nvr/camera/layer.py` to equip `CameraLayer` with `sessions: NuraeyeSessionCache`.
   - Updated `src/vizenlink_nvr/camera/nuraeye/rest.py` with `failure_from_rest` mapping 403 (FORBIDDEN), 428 (PASSWORD_CHANGE_REQUIRED), 429 (BLOCKED with parsed `retry_after`), 401 (UNAUTHORIZED), and general status codes (RES-03..05, D-10).
   - Created `src/vizenlink_nvr/camera/nuraeye/capabilities.py` implementing `RecordingMode` (StrEnum), frozen `Capabilities` (pydantic), and `parse_capabilities(output, strict=...)` defaulting missing fields and dropping unknown recording modes (CAP-01..06, CAM-05).
   - Implemented in `src/vizenlink_nvr/camera/nuraeye/client.py`:
     - `are_you_nuraeye_device_with_retry` (IDN-03, D-02: 3 attempts of 8s, 1s apart).
     - `login(timeout=8.0)` via single-flight returning `LoginInfo`.
     - `_authed` managing transparent single-flight session acquisition, header construction, session extension, and single 401 retry (SES-04, D-09).
     - `get_capabilities(timeout=8.0, strict=...)` returning parsed `Capabilities`.
   - Created simulator routes:
     - `sim/fake_camera/routes/rest_session.py` (`POST /nuraeye/session/login` with lockout handling and bearer token issuance) and `RestSimSettings`/`rest_settings`.
     - `sim/fake_camera/routes/rest_capabilities.py` (`GET /nuraeye/capabilities` with `require_bearer`).
   - Created golden fixture `contracts/fixtures/nuraeye/capabilities_full.json` (source: `contracts/camera_api/docs/external-api/camera-rest-api.md` lines 417-446).
   - Created `tests/contract/test_capabilities.py` covering:
     - Tracer test asserting `login_attempts["admin"] == 1` after one `get_capabilities()` call with `Authorization` and `X-VizenLink-Camera-Id` headers.
     - D-14 token-persistence guard.
     - Session caching, expiry leeway, extension on activity, 401 single retry, single-flight deduplication, and host cache clearing.
     - Strict vs. default capabilities parsing and invalid event shapes handling.

### Verification Evidence:
- `uv run pytest tests/contract/test_capabilities.py -x -q`: 14 passed in 0.11s.
- `uv run mypy src/vizenlink_nvr/camera`: Success: no issues found in 14 source files.
- `uv run python tools/drift_check.py --self`: All vendored contract files match `camera_api.lock.json` (exit 0).
- `uv run pytest -q`: 95 passed, 1 skipped, 6 deselected in 3.15s.
- Reference repositories remained untouched.
