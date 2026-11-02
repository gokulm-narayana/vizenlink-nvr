# Plan 02-02 Summary: Storage Service, System Drive Guard & Admin CLI

## Status: COMPLETE

### Overview
Plan 02-02 implemented the storage management service, cross-platform system root partition protection guard, filesystem disk usage telemetry, and the admin CLI commands `nvr storage status` and `nvr storage set-path` per decisions D-31, D-32, D-33, D-40, and requirements REC-08, HLTH-04, and HLTH-05.

### Tasks Completed:

1. **Task 1: Implement StorageService with system drive guard and health evaluation**
   - Created `src/vizenlink_nvr/services/storage.py`:
     - `is_system_drive(target_path: Path) -> bool`: Cross-platform root filesystem detection (comparing `st_dev` against `/` on POSIX walking up to existing ancestors, and comparing drive letters against `SystemDrive` on Windows).
     - `get_storage_telemetry(target_path: Path, reserve_bytes: int) -> StorageTelemetry | None`: Computes disk usage metrics (`total_bytes`, `used_bytes`, `free_bytes`, `reserve_bytes`) using `shutil.disk_usage`.
     - `evaluate_storage_health(target_path: Path, allow_system_disk: bool, reserve_bytes: int) -> tuple[StorageHealthState, str | None]`: Validates directory creation/existence, guards against system disk usage (returns `SYSTEM_DISK_REFUSED`), validates write permissions via canary file write/unlink (returns `READ_ONLY`), and checks free space against reserve limit (returns `FULL`).
     - `estimate_retention_days(telemetry, total_active_cameras, avg_bitrate_kbps) -> float | None`: Estimates recording retention span in days based on available disk space above reserve and camera bitrates.
     - `get_storage_config(session, default_path) -> StorageConfig` and `set_storage_path(session, target_path, allow_system_disk, reserve_bytes) -> StorageConfig`: Database persistence and retrieval with `StorageSettings`.
   - Created `tests/unit/test_system_drive_guard.py`:
     - Tested POSIX root filesystem detection, mock distinct mountpoint identification, and Windows `SystemDrive` matching.
   - Created `tests/unit/test_storage_service.py`:
     - Tested telemetry retrieval for existing and nested directories.
     - Tested health evaluation transitions (`SYSTEM_DISK_REFUSED`, `OK`, `READ_ONLY`, `FULL`, `UNMOUNTED`).
     - Tested retention estimation math.
     - Tested database persistence via SQLite async engine.

2. **Task 2: CLI storage commands (status, set-path)**
   - Created `src/vizenlink_nvr/cli/storage.py`:
     - `storage_app` with Typer commands `status` and `set-path`.
     - `nvr storage status`: Shows storage path, system disk allowance, health state, health reason, total/used/free space, reserve buffer, and retention estimate. Supports clean `--json` output.
     - `nvr storage set-path`: Accepts `--path` (required) and `--allow-system-disk` (flag). Validates target health; refuses system root partition with exit code 20 (`ExitCode.INVALID_INPUT`) unless `--allow-system-disk` is supplied.
     - Enforces D-16: all command arguments are Typer options, no positional parameters.
   - Registered `storage_app` in `src/vizenlink_nvr/cli/app.py`.
   - Created `tests/integration/test_cli_storage.py`:
     - Verified `nvr storage status` human table output and `--json` structured dictionary output.
     - Verified `nvr storage set-path` refusal on system disk with exit code 20 in both human and JSON modes.
     - Verified `nvr storage set-path --allow-system-disk` succeeds and persists settings.
     - Verified rejection of positional arguments.

### Verification Results:
- `uv run pytest tests/unit/test_storage_service.py tests/unit/test_system_drive_guard.py tests/integration/test_cli_storage.py -x -q`: 15 passed in 0.27s.
- `uv run pytest tests/unit/test_cli_password_options.py`: 2 passed (All CLI commands use TyperOption, no prohibited password options).
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 71 source files.
- Full default pytest suite: 261 passed, 1 skipped, 20 deselected in 87.00s.
