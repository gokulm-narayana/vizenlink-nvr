# Plan 02-07 Summary: Gap Watchdog, Stream Reconnect & Dual Health Badges

## Executive Summary
Plan 02-07 implemented the recording gap watchdog, stream reconnect exponential backoff coordinator, dual independent health badges, and overall recorder health evaluation and CLI reporting per requirements REC-10, HLTH-01, HLTH-03, and HLTH-06.

## Completed Tasks

### Task 1: Gap Watchdog and Exponential Backoff Stream Reconnect Coordinator (REC-10, HLTH-03)
- **`src/vizenlink_nvr/services/watchdog.py`**:
  - `check_camera_gaps`: queries `MAX(Segment.end_time)` per camera where `status != 'missing'`. If elapsed time since last segment > 150s (`2 * 60s + 30s` tolerance), raises `gap_alarm = True` and transitions `recording_state` to `NOT_RECORDING`.
  - Proves the key prohibition: online green badge never masks a recording failure (HLTH-01).
  - Handles startup grace period for newly added cameras without false alarms.
  - `get_reconnect_backoff`: implements binary exponential backoff `1s, 2s, 4s, 8s, 16s, 32s` with a strict `60s` maximum ceiling.
  - `WatchdogService`: exposes class-level interface for gap analysis and reconnect calculations.
- **`tests/unit/test_gap_watchdog.py`**: Unit tests verifying gap detection after elapsed segment window, healthy recording state, disabled mode handling, and new camera startup grace period.
- **`tests/unit/test_stream_reconnect_backoff.py`**: Unit tests verifying backoff progression (1s to 60s), negative/zero handling, and custom bounds.

### Task 2: Dual Health Badges, Recorder Health Aggregation & CLI Status (HLTH-01, HLTH-06)
- **`src/vizenlink_nvr/services/health.py`**:
  - `OnlineState`: `ONLINE`, `OFFLINE`, `AUTH_FAILED`.
  - `RecordingState`: `RECORDING`, `NOT_RECORDING`, `DISABLED`.
  - `RecorderHealthStatus`: `HEALTHY`, `DEGRADED`, `CRITICAL`.
  - `CameraHealth` dataclass with independent reachability and recording badges.
  - `RecorderHealthService.get_recorder_status`: evaluates overall recorder health across DB, MediaMTX process, storage volume, and camera gap alarms.
- **`src/vizenlink_nvr/cli/recording.py`**:
  - Added `nvr recording status` CLI subcommand displaying Rich table with per-camera reachability, recording badges, mode, segment age, and gap alarms.
  - Supports `--json` flag emitting structured telemetry.
- **`src/vizenlink_nvr/cli/status.py`**:
  - Added `evaluate_system_recorder_health` and `render_recorder_status_table` for overall recorder subsystem health inspection.
- **`tests/unit/test_camera_health_badges.py`**: Unit tests proving dual independent badges across the full state matrix and verifying recorder health states (HEALTHY, DEGRADED on media/storage down or gap alarm, CRITICAL on DB failure).
- **`tests/integration/test_recorder_health.py`**: Integration tests proving degraded state and dual badge accuracy in human table and JSON outputs.

## Verification
- `uv run pytest tests/unit/test_gap_watchdog.py tests/unit/test_stream_reconnect_backoff.py tests/unit/test_camera_health_badges.py tests/integration/test_recorder_health.py -v`: 12 passed in 0.42s.
- `uv run pytest tests/unit/test_cli_password_options.py`: 2 passed (Password safety rules enforced).
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 80 source files.
