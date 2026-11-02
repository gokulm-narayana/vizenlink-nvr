# Plan 02-04 Summary: Declarative MediaMTX Reconciler & Supervision

## Status: COMPLETE

### Overview
Plan 02-04 implemented the Declarative MediaMTX Reconciler, which synchronizes SQLite camera streams and recording policies with MediaMTX's REST control API over loopback (`127.0.0.1:9997`), configured 60s fMP4 recording (1s parts, 0s delete after) for main streams and on-demand streaming for sub streams, verified decoupled process supervision and Core restart survivability, and provided the local CLI command `nvr recording reconcile` per decisions D-34, D-38, D-40, and requirements FND-01, FND-02, and REC-01.

### Tasks Completed:

1. **Task 1: Declarative reconciler diff engine and MediaMTX API client**
   - Implemented `src/vizenlink_nvr/media/reconciler.py`:
     - `PathConfiguration`: Dataclass defining MediaMTX path options (`source`, `sourceOnDemand`, `record`, `recordFormat="fmp4"`, `recordPartDuration="1s"`, `recordSegmentDuration="60s"`, `recordDeleteAfter="0s"`, `recordPath`, `runOnRecordSegmentComplete`, `sourceFingerprint`).
     - `ReconcileResult`: Summary of added, patched, deleted, and unchanged paths.
     - `_normalize_duration`: Duration parser handling MediaMTX duration string normalizations (e.g. `60s` <-> `1m0s`, `0s` <-> `""`).
     - `_needs_patch`: Compares significant path fields (`record`, `source`, `sourceOnDemand`, `recordFormat`, `recordPath`, `sourceFingerprint`, durations) to prevent redundant API patches.
     - `compute_desired_paths`: Iterates active cameras, decrypts credentials via vault if available, builds RTSP/RTSPS stream URLs, queries recording policies and schedules (`should_record_now`), and generates desired `cam/<serial>/main` and `cam/<serial>/sub` path configurations. Suppresses recording if storage volume health is not OK.
     - `MediaMtxReconciler`: Communicates with MediaMTX REST API over loopback with basic authentication (`nvr-control`), diffing existing paths against desired paths, and executing `POST /v3/config/paths/add`, `PATCH /v3/config/paths/patch`, and `DELETE /v3/config/paths/delete` for managed (`cam/*`) paths.
   - Created unit tests `tests/unit/test_reconciler_logic.py`:
     - Tested `_needs_patch` behavior across all critical field variations.
     - Tested `compute_desired_paths` with active cameras, excluded inactive cameras, and forced `record=False` when `volume_ok=False`.
     - Tested `MediaMtxReconciler.reconcile` with mock client verifying diff calculation (added, patched, deleted, unchanged).
   - Created integration tests `tests/integration/test_reconciler_api.py`:
     - Tested live reconciliation against local MediaMTX daemon over loopback.
     - Verified path addition, idempotency (0 changes on subsequent run), dynamic patching (`record` toggle), and removal of deleted paths.

2. **Task 2: Independent process supervision and CLI reconcile command**
   - Added `nvr recording reconcile` subcommand to `src/vizenlink_nvr/cli/recording.py`:
     - Loads settings, discovers site timezone, opens vault, evaluates storage health, computes desired paths, calls `MediaMtxReconciler.reconcile()`, and emits human table or `--json` summary.
     - Follows D-16 TyperOption discipline (no positional arguments).
   - Created `tests/integration/test_supervision.py`:
     - Proved FND-01: Started MediaMTX daemon independently, registered camera, and reconciled path.
     - Simulated NVR Core process exit / crash; verified MediaMTX remains running (`poll() is None`) and retains path configuration.
     - Re-started Core, re-reconciled without duplicate additions (unchanged), and toggled recording mode cleanly via CLI.

### Verification Results:
- `uv run pytest tests/unit/test_reconciler_logic.py tests/integration/test_reconciler_api.py tests/integration/test_supervision.py -m "" -x -q`: 5 passed in 0.54s.
- `uv run pytest tests/unit/test_cli_password_options.py`: 2 passed (All CLI commands use TyperOption, no prohibited password options).
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 75 source files.
- All Phase 2 tests so far: 43 passed in 0.93s.
