# Plan 01-02 Summary: Migrated SQLite, runtime and shared status service

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Build migrated SQLite and runtime**
   - Created `src/vizenlink_nvr/db/types.py` with `UtcDateTime` column type (rejecting naive datetimes, serializing to epoch microseconds, and returning aware UTC datetimes).
   - Created `src/vizenlink_nvr/db/models.py` with `Base` and `AppSetting` model.
   - Created `src/vizenlink_nvr/db/engine.py` with `sync_url`, `async_url`, `create_engine_for` (configuring WAL mode, foreign keys, synchronous normal, busy timeout 5000), `upgrade_to_head`, `current_revision`, `head_revision`, and `alembic_config`.
   - Set up Alembic migration environment:
     - `src/vizenlink_nvr/db/migrations/env.py` (with `render_item` for `UtcDateTime` as `sa.BigInteger()` and fallback URL resolution).
     - `src/vizenlink_nvr/db/migrations/script.py.mako`
     - `src/vizenlink_nvr/db/migrations/versions/0001_initial.py` (creates `app_setting` table).
     - `alembic.ini`
   - Created `src/vizenlink_nvr/services/runtime.py` with `Runtime` dataclass and `open_runtime` async context manager (auto-creates directories, runs migrations, enforces 0o600 permissions on POSIX, creates session factory, and disposes engine on exit).
   - Created `src/vizenlink_nvr/services/status.py` with `StatusReport` model and `get_status` function.
   - Created `tests/integration/test_migrations.py` validating:
     - Idempotent upgrade and schema drift check via `alembic check`.
     - File permission checks (0o600 on POSIX).
     - Epoch microsecond storage, round-trip fidelity (at epoch and 999999 µs), aware timezone conversion, and rejection of naive datetimes.
     - Runtime initialization and healthy status report.

### Verification Evidence:
- `uv run pytest tests/integration/test_migrations.py -x -q`: Exit code 0, 3 passed.
- `uv run ruff check src tests`: Exit code 0, all checks passed.
- `uv run mypy src`: Exit code 0, 13 source files verified with no issues.
- `git commit`: `e72cc96 feat(01-02): build migrated SQLite and runtime`.
