# Plan 01-01 Summary: Bootstrap reviewed packages and portable runtime primitives

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Supply-chain gate: approve the dependency list before anything is fetched**
   - User reviewed and approved exact dependency manifest (`approved`).
2. **Task 2: Bootstrap reviewed packages and portable runtime primitives**
   - Configured `.python-version` with `3.13`.
   - Generated `pyproject.toml` with approved runtime and dev dependencies, hatchling wheel config, pytest settings, ruff and mypy rules.
   - Configured `.gitignore` for standard Python/virtualenv/database/cache artifacts.
   - Configured `.github/workflows/ci.yml` matrix workflow.
   - Implemented `src/vizenlink_nvr/__init__.py`.
   - Implemented `src/vizenlink_nvr/config.py` (`NvrSettings`, `load_settings`).
   - Implemented `src/vizenlink_nvr/paths.py` (`ensure_data_dir`, `db_path`, `secrets_dir`, `mediamtx_dir`).
   - Implemented `src/vizenlink_nvr/timeutil.py` (`Clock`, `SystemClock`, `FakeClock`, `to_epoch_us`, `from_epoch_us`, `validate_zone`, `default_site_zone_name`, `format_local`, `local_day_bounds_utc`).
   - Locked dependencies via `uv lock` into `uv.lock`.
   - Installed 53 packages into virtual environment via `uv sync --locked`.
   - Verified compilation via `uv run python -m compileall -q src`.

### Verification Evidence:
- `uv sync --locked`: Exit code 0, 53 packages installed.
- `uv run python -m compileall -q src`: Exit code 0, cleanly compiled.
- `git commit`: `49d81ee feat(01-01): bootstrap reviewed packages and portable runtime primitives`.
