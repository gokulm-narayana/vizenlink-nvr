# Plan 01-31 Summary: Local Phase Gate, OS Matrix, Leaks & Packaging Guards

## Status: COMPLETE

### Overview
Plan 01-31 is the final plan in Phase 01: Foundations & Camera Onboarding. It integrates and enforces all overarching Phase 01 invariants, automated verification gates, secret-leak protections, contract traceability, and wheel packaging requirements across the repository.

### Tasks Completed:

1. **Task 1: Tracer — Local Phase Gate and 3-OS CI Matrix**
   - Updated `.github/workflows/ci.yml`:
     - Added MediaMTX binary cache using `actions/cache@v6.1.0` keyed by `mediamtx-v1.21.3-${{ runner.os }}-${{ runner.arch }}`.
     - Added steps: `tools/fetch_mediamtx.py`, `pytest -m mediamtx` (with 10-minute step timeout), and `tools/drift_check.py --self`.
     - Matrix configured for `ubuntu-latest`, `macos-latest`, `windows-latest` with Python 3.13, plus `ubuntu-latest` with Python 3.11.
     - Explicitly specified `NVR_SECRETS_BACKEND: file` across runners.
   - Created `tools/phase_gate.py`:
     - Executes 7 verification steps sequentially:
       1. Default pytest suite (`uv run pytest -q`)
       2. Fetch MediaMTX binary (`uv run python tools/fetch_mediamtx.py`)
       3. MediaMTX integration tests (`uv run pytest -m mediamtx -q`)
       4. Contract drift verification (`uv run python tools/drift_check.py --self`)
       5. Alembic migrations & schema drift check (`alembic upgrade head` and `alembic check` against isolated temp database)
       6. Ruff linter check (`uv run ruff check src tests sim tools`)
       7. Mypy static type check (`uv run mypy src`)
     - Supports `--keep-going` flag and strict fail-fast exit codes.
   - Created `tests/unit/test_ci_workflow.py`:
     - Validates GitHub Actions workflow structure, 3 OS runners, Python 3.13/3.11 matrix, and required verification commands.
   - *Note on remote CI:* Local execution passed all 7 steps; remote 3-OS CI matrix remains pending until the repository is pushed to a remote host.

2. **Task 2: Secret-Leak Sweep & CLI Password Option Guards (D-14, D-16)**
   - Created `tests/unit/test_cli_password_options.py`:
     - Traverses Typer/Click command hierarchy starting from `vizenlink_nvr.cli.app.app`.
     - Asserts all command parameters are options (`TyperOption`), rejecting any positional arguments.
     - Asserts no parameter contains the name "password" except `--password-stdin`.
   - Created `tests/unit/test_no_secrets_leak.py`:
     - Drives 10 CLI workflows with DEBUG logging and redaction filter enabled:
       - `cameras add` (configured camera with sentinel password `Sentinel-Pa55word!`)
       - `cameras add` (factory camera with sentinel new password `Sentinel-N3w-Pass!`)
       - `cameras set-password`
       - `cameras rename`
       - `cameras reprobe`
       - `cameras list`
       - `cameras show`
       - `cameras status`
       - `cameras scan --json`
       - `cameras add` (wrong password failure path)
       - Database failure exception injection path during onboarding
     - Asserts sentinels NEVER appear in:
       - `stdout` or `stderr`
       - `caplog` captured log text at DEBUG level
       - Exception tracebacks or message text
       - Raw database bytes across `nvr.db`, `nvr.db-wal`, and `nvr.db-shm`.

3. **Task 3: Behaviour-Catalogue Coverage, Mirror-Header Integrity & Wheel Contents (FND-05, D-17)**
   - Created `tests/contract/test_behavior_coverage.py`:
     - Parses all `tests/**/*.py` files using Python's `ast` module.
     - Extracts all `@pytest.mark.behavior(...)` decorator arguments.
     - Asserts all 70 rule IDs defined in `contracts/behaviors.yaml` are covered (70/70 covered, 0 missing).
     - Asserts all cited rule IDs are recognized.
   - Created `tests/contract/test_mirror_headers.py`:
     - Direction 1 (Header -> Lock): Validates all `# mirrors: <path>@<sha12>` headers in `src/vizenlink_nvr/camera/` match valid entries and 12-char SHA-256 prefixes in `contracts/camera_api.lock.json` (22 headers verified).
     - Direction 2 (Lock -> Header): Validates all entries in `contracts/camera_api.lock.json` with `mirrored_by` paths under `src/vizenlink_nvr/camera/` exist and contain the required mirror header (19 mirrored_by references verified).
   - Created `tests/unit/test_wheel_contents.py`:
     - Executes `uv build --wheel --out-dir <tmp>` and verifies the package archive includes:
       - `vizenlink_nvr/db/migrations/versions/0001_initial.py`
       - `vizenlink_nvr/db/migrations/versions/0002_camera_registry.py`
       - `vizenlink_nvr/db/migrations/env.py`
       - `vizenlink_nvr/media/pins.json`
   - Fixed migration head assertions in `test_cli_status.py` and `test_migrations.py` to match current schema `0002_camera_registry`.
   - Updated upstream mirror headers across camera modules for full bidirectional parity.

### Verification Results:
- `tools/phase_gate.py`: 7/7 steps passed.
  ```
  ==> Step 1/7: Default pytest suite ... PASS
  ==> Step 2/7: Fetch MediaMTX binary ... PASS
  ==> Step 3/7: MediaMTX integration tests ... PASS
  ==> Step 4/7: Drift check against camera_api.lock.json ... PASS
  ==> Step 5/7a: Alembic upgrade head on temporary database ... PASS
  ==> Step 5/7b: Alembic schema drift check ... PASS
  ==> Step 6/7: Ruff linter check ... PASS
  ==> Step 7/7: Mypy type check ... PASS
  Phase Gate Result: 7/7 steps passed.
  ```
- Pytest default suite: 240 passed, 1 skipped, 20 deselected in 63s.
- Ruff lint check: All checks passed.
- Mypy static analysis: Success, no issues found in 68 source files.
