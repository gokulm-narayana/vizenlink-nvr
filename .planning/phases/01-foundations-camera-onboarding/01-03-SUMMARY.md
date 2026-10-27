# Plan 01-03 Summary: Complete CLI to migrated database tracer

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Complete CLI to migrated database tracer**
   - Created `src/vizenlink_nvr/cli/exitcodes.py` with `ExitCode` IntEnum.
   - Created `src/vizenlink_nvr/cli/options.py` with `JsonOpt` and `DataDirOpt`.
   - Created `src/vizenlink_nvr/cli/output.py` with `emit` (clean JSON on stdout, rich table human format), `err_console` (stderr), and `fail` (clean JSON error or stderr formatting).
   - Created `src/vizenlink_nvr/cli/cameras.py` defining `cameras_app = typer.Typer(no_args_is_help=True)` and callback.
   - Created registration seam modules `src/vizenlink_nvr/cli/cameras_scan.py`, `src/vizenlink_nvr/cli/cameras_onboard.py`, and `src/vizenlink_nvr/cli/cameras_registry.py`.
   - Created `src/vizenlink_nvr/cli/app.py` registering `cameras_app` and providing `status` command (`--json`, `--data-dir`).
   - Created `tests/conftest.py` with autouse environment isolation (`NVR_SECRETS_BACKEND=file`, `NVR_DATA_DIR=<tmp>/data`), `settings`, `fake_clock`, and `cli` runner fixtures.
   - Created `tests/integration/test_cli_status.py` verifying `nvr status --json` creates DB, applies migrations, returns valid JSON, and is idempotent.
   - Created `tests/unit/test_bootstrap_listeners.py` with `socket.bind` and `socket.listen` guards in-process and via isolated subprocess, proving zero network listeners are opened on import or during `status`.

### Verification Evidence:
- `uv run pytest tests/integration/test_cli_status.py tests/unit/test_bootstrap_listeners.py -x -q`: Exit code 0, 4 passed.
- `uv run pytest -q`: Exit code 0, 7 passed across all tests.
- `uv run ruff check src tests` & `uv run ruff format --check src tests`: Exit code 0.
- `uv run mypy src`: Exit code 0, 22 source files verified.
- `git commit`: `360aa67 feat(01-03): complete CLI to migrated database tracer`.
