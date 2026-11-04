# Plan 08-03 Summary: SQLite Database Backup & Restore

## Achievements
- Implemented `src/vizenlink_nvr/services/backup.py`:
  - `create_backup(db_file, output_dir)` executing online atomic snapshot via SQLite `VACUUM INTO`.
  - Microsecond timestamping and collision prevention.
  - Generates `.meta.json` manifest with SHA-256 checksum, file size, creation timestamp, and Alembic schema revision.
  - `verify_backup(backup_db_path)` validating SHA-256 integrity and running SQLite `PRAGMA integrity_check`.
  - `restore_backup(backup_db_path, target_db_path)` creating safe rollback `.rollback` copy, clearing stale WAL/SHM artifacts, atomic replacement, and verification.
  - `list_backups(backup_dir)` listing and inspecting available backups.
- Implemented `src/vizenlink_nvr/cli/backup_cmd.py` with commands:
  - `nvr backup create [--out path] [--json] [--data-dir path]`
  - `nvr backup restore --file path [--force] [--json] [--data-dir path]`
  - `nvr backup list [--dir path] [--json] [--data-dir path]`
- Mounted `backup_app` into `src/vizenlink_nvr/cli/app.py`.
- Unit tested in `tests/unit/test_backup_restore.py` (5 passed in 0.34s).

## Verification
- `uv run pytest tests/unit/test_backup_restore.py -v` (5 passed).
- `uv run ruff check` and `uv run mypy` passed 100% green.

