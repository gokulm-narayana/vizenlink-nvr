# Plan 02-06 Summary: Retention Janitor, Disk Protection & Camera Removal (CAM-09)

## Executive Summary
Plan 02-06 implemented the Retention Janitor service, low-water mark disk full protection, storage footprint estimation, and camera removal with explicit keep vs. delete recordings choice per requirements REC-05, REC-06, REC-07, and CAM-09.

## Completed Tasks

### Task 1: Retention Janitor & Low-Water Mark Disk Full Protection (REC-05, REC-06, REC-07)
- **`src/vizenlink_nvr/services/janitor.py`**:
  - `enforce_camera_retention`: checks `retention_days` and `retention_max_gb`; queries oldest segments where `is_protected = False`; deletes physical files then deletes database records.
  - `enforce_disk_low_water_mark`: inspects free space via `shutil.disk_usage`; if below reserve (10 GB or 5% disk capacity), proactively prunes oldest unprotected segments across all cameras until free space >= reserve + hysteresis (1 GB buffer).
  - `estimate_retention`: calculates daily footprint from camera bitrate and predicts retention span in days.
  - `delete_camera_recordings`: removes physical files and segment records for a specific camera and cleans up directory hierarchy.
- **`tests/unit/test_retention_janitor.py`**: Unit tests verifying oldest-first pruning, retention days cutoff, size-based quota enforcement, and protected segment immunity (`is_protected = True`).
- **`tests/unit/test_retention_estimation.py`**: Unit tests verifying daily storage footprint and retention span calculations.
- **`tests/integration/test_disk_full_protection.py`**: Integration tests proving low-water mark trigger proactively prunes oldest unprotected segments before disk exhaustion.

### Task 2: Camera Removal with Keep vs Delete Recordings Choice (CAM-09)
- **`src/vizenlink_nvr/cli/cameras_registry.py`**:
  - Implemented `nvr cameras remove --serial <SERIAL> (--keep-recordings | --delete-recordings)` command.
  - Strict input validation requires either `--keep-recordings` or `--delete-recordings` (fails with `ExitCode.INVALID_INPUT` if neither or both are provided).
  - `--keep-recordings` removes camera entity from registry while keeping video segments intact on disk.
  - `--delete-recordings` purges all video files from disk, removes segment records, and deletes camera entity.
  - Supports `--json` flag emitting structured metadata.
- **`tests/integration/test_camera_removal_recordings.py`**: Integration tests testing flag enforcement, non-existent camera rejection, `--keep-recordings` file retention, `--delete-recordings` file purge, and JSON output.

## Verification
- `uv run pytest tests/unit/test_retention_janitor.py tests/unit/test_retention_estimation.py tests/integration/test_disk_full_protection.py tests/integration/test_camera_removal_recordings.py -v`: 10 passed in 0.53s.
- `uv run pytest tests/unit/test_cli_password_options.py`: 2 passed (Password safety rules enforced).
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 77 source files.
- Full test suite: 297 passed, 1 skipped, 22 deselected.
