# Plan 01-04 Summary: UTC storage, site timezone and DST transitions

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Time model (FND-03): UTC storage, site zone setting and DST-correct rendering**
   - Created `src/vizenlink_nvr/services/settings.py` providing `get_setting`, `put_setting`, `get_site_timezone`, and `set_site_timezone` (using `SITE_TIMEZONE_KEY = "site_timezone"`).
   - Updated `src/vizenlink_nvr/services/status.py` to use `get_site_timezone(rt)`.
   - Created `src/vizenlink_nvr/cli/settings_cmd.py` with `settings_app` implementing `nvr settings set-timezone --zone <ZONE> [--json] [--data-dir <DIR>]`, validating with `validate_zone` and exiting with code 20 (`ExitCode.INVALID_INPUT`) on invalid zone name.
   - Registered `settings_app` in `src/vizenlink_nvr/cli/app.py`.
   - Finished `src/vizenlink_nvr/timeutil.py` implementing `local_day_bounds_utc` with nonexistent local midnight resolution and `format_local` rendering.
   - Created `tests/unit/test_timeutil.py` testing parametrized DST transitions (America/New_York, Europe/London, Australia/Lord_Howe, America/Santiago), fall-back, spring-forward, and microsecond epoch calculations.
   - Created `tests/integration/test_time_model.py` testing `UtcDateTime` on direct database tables, settings persistence round-trip, CLI `set-timezone` validation, exit codes, and status integration.

### Verification Evidence:
- `uv run pytest tests/integration/test_time_model.py tests/unit/test_timeutil.py -x -q`: Exit code 0, 16 passed.
- `uv run nvr settings set-timezone --zone Europe/London --json`: Output valid JSON with `site_timezone: Europe/London`.
- `uv run nvr settings set-timezone --zone Not/AZone --json`: Exit code 20, error returned cleanly.
- `uv run pytest -q`: Exit code 0, 23 passed.
- `uv run ruff check src tests` & `uv run ruff format --check src tests`: Exit code 0.
- `uv run mypy src`: Exit code 0, 24 source files checked.
- `git commit`: `22bd5e5 feat(01-04): UTC storage, site timezone and DST transitions`.
