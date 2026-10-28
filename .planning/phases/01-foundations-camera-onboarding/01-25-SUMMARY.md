# Plan 01-25 Summary: Serial-Bound Configured-Camera Onboarding and Local CLI

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Register configured camera after blank serial binding**
   - Implemented `src/vizenlink_nvr/services/onboarding.py`:
     - `AddRequest` (host, port, allow_public validation).
     - `AddOutcomeKind` and `AddOutcome` covering all specified states (OK, ADDRESS_UPDATED, ALREADY_REGISTERED, UNREACHABLE, WRONG_CREDENTIALS, UNSUPPORTED_DEVICE, NEEDS_NEW_PASSWORD, BLOCKED, NO_SERIAL, STREAMS_UNAVAILABLE, FORBIDDEN, TLS_CHANGED, INVALID_INPUT, GENERIC_FAILURE).
     - `PasswordProvider` protocol.
     - `FactoryProbe` and `VerifyKind` outcome models.
     - `OnboardingService` coordinating:
       - Host/port validation (ensuring safe private/loopback/link-local address unless `allow_public`).
       - Blank connection identity probe with retry (`are_you_nuraeye_device_with_retry`).
       - Blank connection serial number retrieval (`get_serial_number()`) immediately after identity; missing serial yields `NO_SERIAL` before any credential attempt.
       - TLS fingerprint retrieval (`fetch_certificate_sha256`) and certificate pin binding.
       - Binding serial to connection so all subsequent credential-bearing calls carry exact-cased `X-VizenLink-Camera-Id`.
       - Factory credential probe (`probe_factory`) using `admin` / `"password"` with session clearing.
       - Current password prompt and credential verification (`verify_credentials`) via authenticated `GET /nuraeye/capabilities`.
       - Authenticated reads with verified connection (re-verifying serial matches bound serial, best-effort device info, MAC, name/location).
       - Duplicate detection by serial (same address -> `ALREADY_REGISTERED`; re-IP -> `ADDRESS_UPDATED` with session cleared).
       - Stream resolution via NuraEye live URI and ONVIF fallback.
       - Vault encryption of administrator password and single-transaction registration in database.
     - `run_add` wrapper managing runtime and vault lifecycles.
   - Implemented `src/vizenlink_nvr/cli/prompts.py`:
     - `read_secret` supporting stderr interactive prompts and stdin piping.
     - `CliPasswordProvider` and `PasswordMismatch`.
   - Implemented `src/vizenlink_nvr/cli/outcomes.py`:
     - `present` mapping `AddOutcome` to `ExitCode` and human messages.
     - `blocked_message` formatting temporary lockout durations.
   - Implemented CLI commands:
     - `src/vizenlink_nvr/cli/cameras_onboard.py`: `nvr cameras add` (rejecting `--password`).
     - `src/vizenlink_nvr/cli/cameras_registry.py`: `nvr cameras list` and `nvr cameras show --serial` (with localized timestamps).
   - Created integration tests in `tests/integration/test_add_manual.py` (tracer, marked `ONB-03`):
     - Configured camera onboarded with blank serial binding, verified capabilities, and stored rows across all 4 database tables.
     - `cameras show` returns the registered camera.
     - Simulator verifies exactly two login attempts for admin, pre-verification `GetDeviceInformation` read using blank credentials, and exact-case `X-VizenLink-Camera-Id` header on all credential-bearing requests.
     - Verification that `--password` is rejected as an unknown CLI option.
     - Missing blank serial yields `NO_SERIAL` with zero login attempts.
     - Swapped simulator serial yields 421 before owner authentication with no stored credential disclosure and zero rows.
     - Wrong password fails via authenticated capabilities check.

### Verification Evidence:
- `uv run pytest tests/integration/test_add_manual.py -x -q`: 4 passed in 0.29s.
- `uv run mypy src`: Success: no issues found in 64 source files.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed.
- No writes outside repository; passwords never appear in command options, logs, or unencrypted storage; all listeners bind 127.0.0.1.
