# Plan 01-19 Summary: REST Sessions, Failure Taxonomy, and Identity Retry

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Session semantics, status mapping and identity retry (SES-01..07, RES-03..05, IDN-03)**
   - Updated `src/vizenlink_nvr/camera/nuraeye/sessions.py` to scale effective leeway down for short sessions (`expires_in_sec <= 60`) so that 50s advancing intervals over 60s sessions extend without prematurely refreshing (SES-03).
   - Created four verified golden error fixtures with strict provenance in `contracts/fixtures/nuraeye/`:
     - `error_403.json`: Forbidden response from `contracts/camera_api/docs/external-api/camera-rest-api.md` L136-141.
     - `error_428.json`: Password change required response from `contracts/camera_api/docs/external-api/camera-rest-api.md` L97-102.
     - `error_429_retry_field.json`: Rate limited response with `retry_after_seconds` field from `contracts/camera_api/docs/external-api/camera-rest-api.md` L124-130.
     - `error_429_message_only.json`: Rate limited response with message-only countdown from `contracts/camera_api/mobile_app/packages/camera_api/lib/src/lan/nuraeye/nuraeye_client.dart` L408-410.
   - Verified fixture provenance against contracts with `tests/contract/test_fixtures_provenance.py` (passed).
   - Created `tests/contract/test_nuraeye_sessions.py` validating:
     - SES-01: Ten `get_capabilities()` calls result in exactly 1 login request.
     - SES-02: `expires_in_sec = 0` forces fresh login before every call without 401s seen by the simulator.
     - SES-03: `expires_in_sec = 60` with 50s idle advances produces 1 login (calls extend idle window).
     - SES-04: Token invalidation triggers 1 401, 1 re-login, 1 retry, succeeding; changed password produces Failure(UNAUTHORIZED) with login attempts growing by exactly 1.
     - SES-05: 5 concurrent `get_capabilities()` callers on an empty cache trigger exactly 1 login request.
     - SES-06: `clear_session_for("host")` clears all accounts for that host while preserving sessions for other hosts.
     - SES-07: Login without token yields specific error reason; role and password_change_required parsed.
   - Created `tests/contract/test_rest_failures.py` validating:
     - RES-03: `parse_retry_after` precedence rules (`retry_after_seconds` > regex match in error message > None).
     - RES-04: HTTP 403 maps to `FailureKind.FORBIDDEN` with zero additional login attempts.
     - RES-04: HTTP 428 maps to `FailureKind.PASSWORD_CHANGE_REQUIRED`.
     - RES-04: HTTP 429 maps to `FailureKind.BLOCKED` with parsed `retry_after`.
     - RES-04: HTTP 500 maps to `FailureKind.GENERIC` with `HTTP 500: <msg>`.
     - RES-05: HTTP 401 failure reason contains "401" and the camera error message.
   - Created `tests/contract/test_identity_retry.py` validating:
     - IDN-03: `are_you_nuraeye_device_with_retry` succeeds on the 3rd attempt after first 2 time out (2 injected 1s sleeps, under 1s wall time).
     - IDN-03: All 3 attempts timing out returns the last `Timeout` result.

### Verification Evidence:
- `uv run pytest tests/contract/test_nuraeye_sessions.py tests/contract/test_rest_failures.py tests/contract/test_identity_retry.py -x -q`: 15 passed in 0.50s.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 87 files already formatted.
- `uv run mypy src/vizenlink_nvr/camera`: Success: no issues found in 14 source files.
- `uv run pytest -q`: 110 passed, 1 skipped, 6 deselected in 3.91s.
- Reference repositories remained untouched.
