---
quick_id: 261113-kag
mode: quick
date: 2026-11-13
---

# Plan: storage set-path must validate before saving

## Problem (found by the 2026-11-13 live API smoke test)
`POST /api/v1/storage/set-path` called `set_storage_path()` (which commits) and only then checked for `SYSTEM_DISK_REFUSED`. A request answered with 400 had already overwritten the working storage settings. Reproduced live: path `relative/dir` returned 400, the stored row became `<cwd>/relative/dir` with `allow_system_disk=0`, `/health` turned `storage_ok: false`, and an empty `relative/dir` folder was created in the process working directory. This breaks the core value (never miss footage): the recorder treats storage as unhealthy after a request the API rejected.

## Tasks
1. `src/vizenlink_nvr/api/v1/storage.py`: in `set_storage_path_endpoint`, reject non-absolute paths with 422, then call `evaluate_storage_health` and refuse `SYSTEM_DISK_REFUSED`, `UNMOUNTED` and `READ_ONLY` with 400 before `set_storage_path` is called. Same order the CLI (`cli/storage.py::set_path`) already uses.
2. `src/vizenlink_nvr/services/storage.py`: in `evaluate_storage_health`, run the system-disk guard before `mkdir`, so a refused path leaves no folder behind.
3. `tests/integration/test_api_storage.py`: new test proving that a system-disk refusal, a relative path and an uncreatable path each leave the stored settings unchanged, create no folder, and write no `storage.update_path` audit entry.

## Verify
- `uv run pytest -q tests/integration/test_api_storage.py tests/unit/test_storage_service.py tests/integration/test_cli_storage.py`
- `uv run pytest -q` (full suite)
- `uv run ruff check` on the three files

## Out of scope
- `services/setup.py::initialize_nvr` also saves without checking. Left as is on purpose: see SUMMARY.
