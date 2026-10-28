# Plan 01-29 Summary: Camera Rename, Reprobe, Credentials and Certificate Recovery

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Tracer - `nvr cameras rename` writes name/location to the camera, keeps group NVR-only, and `show` reflects it**
   - Updated `src/vizenlink_nvr/services/registry.py`:
     - Added `MAX_GROUP_LENGTH = 64`.
     - Added `update_identity(session, serial, *, name, location, group, at)` updating identity fields and recording `identity_synced_at`.
     - Added `set_tls_fingerprint(session, serial, sha256_hex, at)`.
   - Created `src/vizenlink_nvr/services/manage.py`:
     - Models `RenameRequest`, `ManageKind`, `ManageOutcome`.
     - Implemented `rename_camera`: validates lengths (name/location <= 32 chars, group <= 64 chars); short-circuits with `AUTH_FAILED` or `TLS_CHANGED` when in those states without camera I/O; sends `set_device_name` and `set_device_location` via ONVIF SetScopes; reads back actual identity from camera; updates group tag strictly in NVR database without sending over the wire; group-only renames perform zero camera network requests.
     - Implemented `run_rename`.
   - Updated `src/vizenlink_nvr/services/onboarding.py`:
     - Added optional `name`, `location`, `group` to `AddRequest`.
     - In `OnboardingService.add`: applies name and location to the camera via SetScopes before single DB transaction; on failure aborts with `GENERIC_FAILURE` leaving zero rows across all camera tables; stores group tag in registry.
   - Updated `src/vizenlink_nvr/cli/cameras_onboard.py`:
     - Added `--name`, `--location`, `--group` options to `nvr cameras add`.
   - Updated `src/vizenlink_nvr/cli/cameras_registry.py`:
     - Added `nvr cameras rename --serial SERIAL [--name N] [--location L] [--group G] [--json]` with exit code mappings (OK 0, INVALID_INPUT 20, NOT_FOUND 22, AUTH_FAILED 23, TLS_CHANGED 19, FORBIDDEN 18, UNREACHABLE 10).
   - Created integration tests in `tests/integration/test_rename.py` (marked `CAM-08`):
     - `test_rename_writes_name_location_to_camera_and_group_is_nvr_only`: verifies name/location synced, group never appears in wire request bodies.
     - `test_rename_group_only_makes_zero_simulator_requests`: verifies 0 requests on group-only rename.
     - `test_rename_33_chars_refused_as_invalid_input_exit_20`: rejects >32 chars with exit 20 before I/O.
     - `test_rename_unicode_special_chars_cafe`: UTF-8/non-ASCII characters ("Café 1") round-trip through camera and DB.
     - `test_add_with_name_location_group_and_failure_leaves_zero_rows`: SetScopes failure rolls back atomically to 0 rows.
     - `test_rename_on_auth_failed_camera_returns_exit_23_with_zero_requests`: short-circuits with exit 23 and 0 requests.

2. **Task 2: Reprobe refresh of capabilities and streams, with certificate-change handling (CAM-05, D-25)**
   - Updated `src/vizenlink_nvr/services/reprobe.py`:
     - Extended `ReprobeKind` with `AUTH_FAILED`, `TLS_CHANGED`, `FORBIDDEN`.
     - Extended `ReprobeReport` with `refreshed: bool = False`, `camera: CameraView | None = None`.
     - Enhanced `reprobe_camera` to re-read capabilities, resolve streams, device identity, and firmware; replaces capabilities and streams in a single atomic transaction; when stream resolution or profile reads fail, retains existing DB records without partial replacement; supports `--accept-new-certificate` flow (checks unauthenticated serial header, fetches new certificate pin, verifies authenticated capabilities, re-pins fingerprint in DB, and restores state to `active`).
     - Added reachability check refusal when camera is in `auth_failed` or `tls_changed` state.
   - Updated `src/vizenlink_nvr/cli/cameras_registry.py`:
     - Added `--accept-new-certificate` option to `reprobe` command.
     - Output surfaces exact owner guidance: `"The camera's certificate has changed since it was added. If you replaced or updated this camera, run: nvr cameras reprobe <serial> --accept-new-certificate"`.
   - Updated `sim/fake_camera/pytest_plugin.py`:
     - Added `ControllableFakeCamera` subclass with `restart_with_new_certificate()` on same port.
   - Created integration tests in `tests/integration/test_reprobe.py` (marked `CAM-05`):
     - `test_reprobe_refreshes_capabilities_streams_and_name`: verifies full capability, stream, and name refresh.
     - `test_reprobe_partial_failure_leaves_previous_capabilities_and_streams_unchanged`: Media2 failure keeps existing records byte-identical.
     - `test_reprobe_after_heal_also_refreshes`: verifies re-IP heal followed by refresh at new address.
   - Created integration tests in `tests/integration/test_tls_changed.py` (marked `CAM-05`):
     - `test_tls_changed_returns_exit_19_and_marks_state`: verifies exit 19, `tls_changed` state, exact message, zero credentialed requests.
     - `test_reprobe_accept_new_certificate_success`: verifies serial check, new pin stored, state restored to active.
     - `test_reprobe_accept_new_certificate_fails_if_serial_mismatch`: serial mismatch stops without updating pin.
     - `test_automated_wording_guard_no_false_tls_claims`: automated regex scan ensuring no code claims certificate fingerprints authenticate camera identity or provide MITM protection.

3. **Task 3: auth_failed after a password change elsewhere, and `nvr cameras set-password` recovery (D-09)**
   - Updated `src/vizenlink_nvr/services/manage.py`:
     - Implemented `set_camera_password`: loads camera, prompts for current password, builds connection with stored pin and serial, runs `OnboardingService.verify_credentials` (fresh session login and authenticated GetCapabilities); on OK, seals password and updates `CameraCredential` and sets state to `active` in one transaction; on error returns outcome without storing anything.
   - Updated `src/vizenlink_nvr/cli/cameras_registry.py`:
     - Added `nvr cameras set-password --serial SERIAL [--password-stdin] [--json]` command.
   - Created integration tests in `tests/integration/test_auth_failed.py` (marked `CAM-08`):
     - `test_auth_failed_lifecycle_and_set_password_recovery`: asserts login attempt deltas sequence `[1, 0, 0, 1, 1]` across reprobe 1, reprobe 2, rename, wrong set-password, right set-password; verifies status CLI reports `cameras_by_state.auth_failed == 1`.
     - `test_set_password_429_returns_blocked_exit_14_and_stores_nothing`: verifies 429 lockout mapping and atomic preservation.
     - `test_reprobe_403_returns_forbidden_exit_18_and_does_not_mark_auth_failed`: verifies 403 Forbidden exit 18 without marking `auth_failed` (D-10).
     - `test_rename_setscopes_401_marks_auth_failed`: verifies SetScopes 401 transition to `auth_failed`.

### Verification Evidence:
- `uv run pytest tests/integration/test_rename.py tests/integration/test_reprobe.py tests/integration/test_tls_changed.py tests/integration/test_auth_failed.py -x -q`: 17 passed in 6.04s.
- `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`: All checks passed, 116 files formatted, 0 mypy issues.
- Invariants maintained: only declared files written, all listeners bind loopback (`127.0.0.1`), credentials never logged or leaked to arguments or plain outputs.
