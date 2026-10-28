# Plan 01-27 Summary: One-Shot Factory Flow, Error Taxonomy, and Atomic Add

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Tracer - Factory-password camera -> forced new password -> SetUser -> verify -> registered**
   - Created `src/vizenlink_nvr/services/passwords.py`:
     - `MIN_PASSWORD_LENGTH = 8`, `MAX_PASSWORD_LENGTH = 32`, `FACTORY_PASSWORD_LOWER = "password"`.
     - `PasswordRuleError` exception with exact user messages ("Use 8 to 32 characters." / "Choose a password other than the factory password.").
     - `validate_new_camera_password` validating character length 8..32 and case-insensitive check against "password".
   - Updated `src/vizenlink_nvr/cli/prompts.py`:
     - `CliPasswordProvider.new_password()` prompts on stderr with warning: `"This camera still uses its factory password. Set a new password to continue."`.
     - In interactive mode: validates confirmation match and candidate password rules, re-prompting up to 3 times on stderr.
     - In stdin mode: reads two lines and raises `PasswordMismatch` or `PasswordRuleError` immediately.
   - Updated `src/vizenlink_nvr/services/onboarding.py`:
     - `AddOutcome` gains `notice: str | None = None`.
     - On `FactoryProbe.FACTORY_PASSWORD`: prompts for new password, validates rules without camera I/O, issues `OnvifDeviceClient.set_user_password("admin", new_pw)`, handles timeout gracefully with guidance message, clears sessions, and continues verification with `new_pw`.
     - On successful registration after password change, sets notice: `"Use this new password in the VizenLink mobile app too."`.
     - Routes `VerifyKind.NEEDS_NEW_PASSWORD` (HTTP 428) through the same password change flow using entered credentials.
   - Updated `src/vizenlink_nvr/cli/cameras_onboard.py`:
     - Renders `outcome.notice` on stdout following camera details table in human mode, and includes `notice` field in JSON output.
   - Created unit tests in `tests/unit/test_password_rules.py` (marked `ONB-04`):
     - Validates 8 and 32 characters accepted; 7 and 33 rejected; "password", "PASSWORD", "PassWord" rejected.
   - Created integration tests in `tests/integration/test_factory_flow.py` (marked `ONB-01`):
     - Factory-fresh camera onboarded with exactly one login attempt with factory password, SetUser called once, verification with new password, gate cleared, and notice printed.
     - Confirmation mismatch and rule violation abort without calling SetUser.
     - Dev build camera with gate False treated as factory (F13).
     - SetUser timeout reports UNREACHABLE with owner guidance and no second login.

2. **Task 2: Failure taxonomy with exact messages, exit codes and lockout-safe attempt counts**
   - Updated `src/vizenlink_nvr/services/onboarding.py`:
     - Verification HTTP 503 ("Firmware upgrade in progress") mapped to `UNREACHABLE` with detail `"The camera is upgrading its firmware. Try again in about a minute."`.
     - Login failures never make subsequent automatic login attempts.
   - Updated `src/vizenlink_nvr/cli/cameras_onboard.py`:
     - `--json` mode emits clean JSON object containing `kind`, `message`, `code`, and optional `detail` on stdout, with human message on stderr.
     - Preserves stable exit codes for all failure outcomes.
   - Created integration tests in `tests/integration/test_add_error_taxonomy.py` (marked `CAM-03`, `ONB-02`):
     - Connect to unused port -> UNREACHABLE exit 10.
     - Identity probe timeout -> UNREACHABLE exit 10.
     - Non-genuine, 404, or malformed identity -> UNSUPPORTED_DEVICE exit 12.
     - Wrong password -> WRONG_CREDENTIALS exit 11, exactly 2 admin login attempts (1 factory probe + 1 verification).
     - 429 during verification or factory probe -> BLOCKED exit 14 with formatted retry delay.
     - 403 during verification -> FORBIDDEN exit 18.
     - 503 firmware upgrade -> UNREACHABLE exit 10 with detail.
     - Missing serial -> NO_SERIAL exit 15.
     - Missing/failing Media2 -> STREAMS_UNAVAILABLE exit 16.
     - Duplicate same address -> ALREADY_REGISTERED exit 17.
     - Duplicate new port -> ADDRESS_UPDATED exit 0 with host/port updated.

3. **Task 3: Atomic add - zero rows on failure at any step**
   - Updated `src/vizenlink_nvr/services/onboarding.py`:
     - All camera I/O and vault sealing complete before database transaction opens.
     - DB commit wrapped in rollback block mapping exceptions to `GENERIC_FAILURE` with detail `"Could not save the camera. Nothing was stored; try again."`.
   - Created integration tests in `tests/integration/test_atomic_add.py` (marked `CAM-06`):
     - Parametrized over all 9 failure points (identity, factory probe login, verification login, GetCapabilities, reread serial, GetProfiles, live stream Profile_1, live stream Profile_2, DB exception after partial camera flush).
     - Verifies 0 rows in `camera`, `camera_credential`, `camera_capabilities`, and `camera_stream` on each failure.
     - Verifies immediate retry after clearing fault succeeds with 1 camera, 1 credential, 1 capabilities, 2 streams.
     - Verifies factory password changed then later step failing leaves 0 rows and simulator keeps new password; retry asks for configured password and succeeds.
     - Verifies best-effort reads failing (`GetNetworkInterfaces`, `GetDeviceIdentity`) do not abort the add.

### Verification Evidence:
- `uv run pytest tests/unit/test_password_rules.py tests/integration/test_factory_flow.py tests/integration/test_add_error_taxonomy.py tests/integration/test_atomic_add.py -x -q`: 33 passed in 11.37s.
- `uv run mypy src`: Success: no issues found in 65 source files.
- `uv run ruff check src tests && uv run ruff format --check src tests`: All checks passed, 107 files already formatted.
- Invariants maintained: only declared files written, all listeners bind loopback (`127.0.0.1`), credentials never logged or leaked to arguments or plain outputs.
