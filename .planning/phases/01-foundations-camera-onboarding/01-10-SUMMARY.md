# Plan 01-10 Summary: Live MediaMTX Rejection Probes and Process Cleanup

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Live default-deny probes with negative control, `--probe`, and no-leftover-process guard**
   - Created `src/vizenlink_nvr/media/process.py`:
     - `MediaMtxProcess` context manager (supporting both sync and async usage).
     - Streaming log collector with ready detection (`[API] started` line).
     - Safe process termination and cleanup with SIGTERM and fallback SIGKILL.
     - `live_processes()` registry tracking running instances.
   - Created `src/vizenlink_nvr/media/check.py`:
     - `ProbeResult` data model.
     - `REFUSED_PORTS` list: `(1935, 1936, 8890, 8892, 8893, 8322, 9998, 9999)`.
     - `listener_lines_ok` inspecting process logs to ensure all listener lines name `127.0.0.1` and no unused protocols start.
     - `run_probes` executing exact status checks across RTSP (ANNOUNCE, DESCRIBE, api-only user), HLS (anonymous and api-only user), WebRTC (WHEP, WHIP), Playback (/list, /get), API (anonymous, wrong password, control credentials), and refused connection checks on disabled ports.
   - Updated `src/vizenlink_nvr/services/mediamtx.py`:
     - Integrated `MediaMtxProcess` and `run_probes` in `run_check` when `probe=True`.
     - Added test port override support via `NVR_MEDIAMTX_TEST_PORTS`.
   - Created `tests/mediamtx/permissive.py`:
     - Negative-control configuration builder providing open `any` users.
   - Created `tests/mediamtx/test_default_deny.py`:
     - `test_live_default_deny_probes`: Asserts all 21 default-deny probes pass against live instance on random ports.
     - `test_negative_control_fails_probes`: Asserts that under permissive configuration, probes fail (anonymous ANNOUNCE returns 200, anonymous API returns 200), proving sensitivity.
   - Updated `tests/mediamtx/test_cli_mediamtx.py`:
     - Added `test_cli_mediamtx_check_probe_json` testing `nvr mediamtx check --probe --json`.
   - Updated `tests/conftest.py`:
     - Added session-scoped `clean_mediamtx_processes` fixture asserting `live_processes()` is empty and cleaning up any survivors.

### Verification Evidence:
- `uv run pytest -m mediamtx tests/mediamtx -x -q`: 6 passed in 9.52s.
- `uv run pytest -x -q`: 76 passed, 1 skipped, 6 deselected in 2.08s.
- `uv run nvr mediamtx check --probe --json`: Exits 0 with all 21 probes OK.
- `pgrep -f mediamtx`: No processes running.
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run ruff format --check src tests sim tools`: 77 files already formatted.
- `uv run mypy src`: Success: no issues found in 47 source files.
