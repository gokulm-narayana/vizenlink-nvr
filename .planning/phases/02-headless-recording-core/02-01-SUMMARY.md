# Plan 02-01 Summary: Recording Core Schema Migration 0003 & ORM Models

## Status: COMPLETE

### Overview
Plan 02-01 implemented the core schema migration `0003_recording_core` and the corresponding SQLAlchemy ORM models (`RecordingSettings`, `Segment`, and `StorageSettings`), laying the database foundation for headless 24/7 recording, storage limits, and segment indexing in Phase 02.

### Tasks Completed:

1. **Task 1: Add SQLAlchemy ORM models and Alembic revision 0003_recording_core**
   - In `src/vizenlink_nvr/db/models.py`:
     - Defined `RecordingSettings`:
       - `camera_serial` (PK, FK -> `camera.serial` ON DELETE CASCADE)
       - `mode` (`continuous`, `scheduled`, `event`, `off`) with check constraint `ck_recording_settings_mode`
       - `schedule_json` (7x24 weekly schedule)
       - `audio_enabled` (boolean toggle)
       - `retention_days` and `retention_max_gb` (nullable limits)
       - `created_at` and `updated_at` (UtcDateTime)
     - Defined `Segment`:
       - `id` (autoincrement PK)
       - `camera_serial` (indexed FK -> `camera.serial` ON DELETE CASCADE)
       - `stream_type` (default `main`)
       - `file_path` (unique, indexed)
       - `start_time` and `end_time` (indexed UtcDateTime)
       - `duration_seconds` (Float)
       - `file_size_bytes` (BigInteger)
       - `status` (`active`, `missing`, `truncated`) with check constraint `ck_segment_status`
       - `is_protected` and `protection_reason` (for retention protection ranges)
       - `created_at` (UtcDateTime)
     - Defined `StorageSettings`:
       - `id` (PK)
       - `storage_path` (recording directory root)
       - `allow_system_disk` (boolean safety override)
       - `reserve_bytes` (default 10 GB = 10737418240 bytes)
       - `created_at` and `updated_at` (UtcDateTime)
     - Added relationships from `Camera` to `RecordingSettings` (1-to-1) and `Segment` (1-to-many) with cascading deletes.
   - Authored `src/vizenlink_nvr/db/migrations/versions/0003_recording_core.py`:
     - Upgrades SQLite database from `0002_camera_registry` to `0003_recording_core`.
     - Creates tables, foreign key constraints with `ON DELETE CASCADE`, check constraints, and indexes.
     - Implemented full clean `downgrade()` back to `0002_camera_registry`.
   - Verified zero schema drift with `uv run alembic check`.

2. **Task 2: Migration integration and model unit tests**
   - Created `tests/unit/test_recording_models.py`:
     - Verified model instantiations, field types, defaults, and bidirectional relationships.
   - Created `tests/integration/test_recording_migrations.py`:
     - Verified upgrade to `0003_recording_core`, alembic check, downgrade to `0002_camera_registry`, and re-upgrade.
     - Verified foreign key cascading deletes (`PRAGMA foreign_keys = ON`): deleting a camera automatically cascades and deletes its `recording_settings` and `segments` rows, while leaving `storage_settings` untouched.
   - Updated `tests/integration/test_migrations.py` and `tests/integration/test_cli_status.py` head revision expectations to `"0003_recording_core"`.

### Verification Results:
- `uv run alembic upgrade head && uv run alembic check`: PASS (Zero drift detected).
- `uv run pytest tests/unit/test_recording_models.py tests/integration/test_recording_migrations.py tests/integration/test_cli_status.py tests/integration/test_migrations.py -x -q`: 11 passed in 0.41s.
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 69 source files.
- Full default pytest suite: 246 passed, 1 skipped, 20 deselected in 87s.
