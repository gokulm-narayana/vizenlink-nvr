# Plan 01-28 Summary: Silent Serial-Based Re-IP Recovery

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Tracer - `nvr cameras reprobe` heals a camera that moved address**
   - Created `src/vizenlink_nvr/services/recovery.py`:
     - Enums `HealTrigger` (`ID_MISMATCH`, `UNREACHABLE`, `EXPLICIT`) and `HealKind` (`HEALED`, `VERIFIED_IN_PLACE`, `AMBIGUOUS`, `NOT_FOUND`, `SKIPPED_BACKOFF`, `SKIPPED_IN_FLIGHT`, `IGNORED`).
     - Models `HealOutcome` with serial, old/new addresses, claimants, next_attempt_at.
     - `AddressHealer` class managing discovery (multicast first, fallback to unicast sweep), candidate matching with blank credentials only (D-12), excluding stored address, updating registry host/port in a single transaction, and clearing the old host's bearer session cache.
     - `make_healer` factory configuring production `WsDiscoveryClient` and 4-second blank serial probe via `OnvifDeviceClient.get_serial_number()`.
   - Created `src/vizenlink_nvr/services/reprobe.py`:
     - Enum `ReprobeKind` (`OK`, `HEALED`, `AMBIGUOUS`, `NOT_FOUND`, `UNREACHABLE`, `NOT_FOUND_SERIAL`).
     - Model `ReprobeReport` containing serial, kind, address, heal outcome, and warnings list.
     - `reprobe_camera` coordinates serial verification using blank credentials with `X-VizenLink-Camera-Id` header:
       - 421 HTTP response (`ID_MISMATCH`) or timeout/unreachable -> triggers `healer.heal()`.
       - Firmware with `camera_id_check=False` -> serial comparison detects mismatch and triggers heal, attaching DHCP reservation warning.
       - Matching serial -> returns `ReprobeKind.OK`.
     - `run_reprobe` high-level entrypoint opening runtime, layer, and healer context.
   - Updated `src/vizenlink_nvr/cli/cameras_registry.py`:
     - Added `nvr cameras reprobe --serial SERIAL [--json] [--data-dir]` command.
     - Human mode prints:
       - "Camera <serial> is at <host>:<port>"
       - "Address updated from <old> to <new>"
       - "N devices claim serial <serial>; nothing was changed."
       - "Could not find camera <serial> on the network."
       - Warnings on `err_console` (e.g. DHCP reservation advice).
     - Standardized exit codes: 0 (OK/HEALED), 10 (UNREACHABLE/NOT_FOUND), 22 (NOT_FOUND_SERIAL), 1 (AMBIGUOUS).
   - Created integration tracer in `tests/integration/test_reip.py` (marked `HEAL-05`):
     - Moved camera A's address pointing at B; reprobe receives 421, re-discovers A by serial, updates registry, leaves single row in database, and ensures 0 credentialed requests reach either camera during healing.

2. **Task 2: Healer rules, backoff sequence, event bus attach, and Pitfall 16**
   - Enhanced `AddressHealer`:
     - In-flight deduplication via `_in_flight` set returning `SKIPPED_IN_FLIGHT`.
     - Non-forced heals during backoff return `SKIPPED_BACKOFF` with `next_attempt_at`; `force=True` bypasses backoff.
     - `UNREACHABLE` pre-check: if stored address answers with matching serial, returns `VERIFIED_IN_PLACE` without scanning network.
     - 60-second verified window: subsequent unreachable reports within 60 seconds return `VERIFIED_IN_PLACE` without reading serial.
     - Placeholder hosts (`0.0.0.0` or `cloud-*`) bypass stored pre-check straight to network search.
     - Candidate filtering: excludes stored address even if still responding.
     - Ambiguity: multiple candidates matching serial returns `AMBIGUOUS` with claimant count without changing DB.
     - Exponential backoff sequence: consecutive `NOT_FOUND` results schedule retries at 30, 60, 120, 240, 480, 600, 600 seconds (`min(base * 2^(n-1), max)`). Reset on success.
     - `attach(events)`: subscribes to `CameraEventBus` to handle `CameraIdMismatchEvent` and `CameraUnreachableEvent`, tracking tasks with graceful `aclose()`.
   - Created unit tests in `tests/unit/test_healer_rules.py` (marked `HEAL-01`, `HEAL-02`, `HEAL-03`, `HEAL-04`, `HEAL-05`):
     - `test_healer_ignore_unknown_serial_and_differing_host` (HEAL-01)
     - `test_healer_in_flight_deduplication_and_backoff_bypass` (HEAL-01)
     - `test_healer_unreachable_verified_in_place_and_60s_window` (HEAL-02)
     - `test_healer_placeholder_host_skips_precheck` (HEAL-02)
     - `test_healer_match_ambiguity_and_stored_exclusion` (HEAL-03)
     - `test_healer_exponential_backoff_sequence` (HEAL-04)
     - `test_healer_healed_updates_db_clears_session_and_uses_blank_credentials` (HEAL-05)
     - `test_healer_attach_event_bus` (HEAL-01)
   - Extended integration tests in `tests/integration/test_reip.py` (marked `HEAL-05`):
     - `test_reprobe_heals_when_camera_id_check_is_false_and_warns`: Pitfall 16 verified with two simulated cameras with `camera_id_check=False`; reprobe compares GetDeviceInformation serial, heals moved address, includes DHCP reservation warning, and preserves D-12 credential isolation.

### Verification Evidence:
- `uv run pytest tests/unit/test_healer_rules.py tests/integration/test_reip.py -x -q`: 10 passed in 10.62s.
- `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`: All checks passed, 111 files formatted, 0 mypy issues.
- Invariants maintained: only declared files written, all listeners bind loopback (`127.0.0.1`), credentials never logged or leaked to arguments or plain outputs.
