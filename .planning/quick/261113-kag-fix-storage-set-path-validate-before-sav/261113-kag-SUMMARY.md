---
quick_id: 261113-kag
status: complete
date: 2026-11-13
commit: none (working tree only; see "Not committed")
---

# Summary: storage set-path validates before saving

## Changed
- `src/vizenlink_nvr/api/v1/storage.py`: `POST /storage/set-path` now rejects a non-absolute path with 422 and runs `evaluate_storage_health` before saving. `SYSTEM_DISK_REFUSED`, `UNMOUNTED` and `READ_ONLY` return 400 and nothing is written. `FULL` is still accepted (same as the CLI; the janitor frees space).
- `src/vizenlink_nvr/services/storage.py`: `evaluate_storage_health` checks the system-disk guard before creating the folder, so a refused path leaves no empty directory.
- `tests/integration/test_api_storage.py`: `test_refused_storage_path_leaves_settings_unchanged` (system-disk refusal, relative path, uncreatable path; settings, folders and audit log all unchanged).

## Why
Before the fix a refused request still overwrote the working storage row. Live repro on 2026-11-13: `relative/dir` got 400, yet `/health` then showed `storage_ok: false` / `system_disk_refused` and the NVR had created `relative/dir` in its working directory.

## Behaviour change to know about
- The API now refuses unwritable or uncreatable paths (400). Before, they were saved and reported unhealthy afterwards.
- A path that is on the system disk and cannot be created now reports `SYSTEM_DISK_REFUSED` instead of `UNMOUNTED` when the override is off (order of checks changed).

## Left alone on purpose
- `services/setup.py::initialize_nvr` has the same save-without-check pattern, but there is no earlier working config to destroy at first run, and the web setup form does not send `allow_system_disk`. Refusing there would block first-run setup on any single-disk machine. Health already reports the refused state honestly (`test_health_honest_storage.py`). Needs an owner decision: add an "allow system disk" choice to the setup form, then refuse.
- Other findings from the same smoke test (timeline returns 200 for an unknown camera and for end before start; 47 ruff errors in `sim_camera.py` / `assistant.py`; mobile live URL on 127.0.0.1) are not touched.

## Verified
- Storage, CLI storage, health and setup tests: 18 passed.
- Full backend suite: 565 passed, 1 skipped, 23 deselected (was 564; +1 new test).
- `ruff check` clean on the three files.

## Not committed
The two source files and the test file already carry the owner's uncommitted changes, so a commit of this fix would sweep those in. Left in the working tree with the rest, like quick task 261112-9kw. No planner/executor subagents or worktree were used: a worktree forks from HEAD and would not contain the uncommitted work this fix sits on.
