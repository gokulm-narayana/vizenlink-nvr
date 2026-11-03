# Plan 03-01 Summary: Schema Migration 0004, Auth Models & Argon2id Hasher

**Execution Date:** 2026-11-03
**Status:** Complete
**Requirements:** `AUTH-02`, `AUTH-08`

## What Was Accomplished

1. **Argon2id Password Hasher Service (`AUTH-02`):**
   - Added `argon2-cffi~=23.1` dependency in `pyproject.toml`.
   - Created `src/vizenlink_nvr/services/auth_hasher.py` implementing `hash_password`, `verify_password`, and `check_needs_rehash` using OWASP-recommended parameters (3 iterations, 64 MiB memory, 4 parallel threads, 32-byte hash length, 16-byte random salt).
   - Created `tests/unit/test_argon2_hashing.py` confirming `$argon2id$` format, per-call randomized salt, accurate matching, rejection of mismatches, and safe handling of tampered or empty hashes without leaking plaintext.

2. **Database Migration 0004 (`0004_auth_and_audit.py`):**
   - Created Alembic migration `0004_auth_and_audit.py` with `down_revision = "0003_recording_core"`.
   - Added tables:
     - `users`: ID, username (unique indexed), password_hash, role (`owner`, `operator`, `viewer`), is_active, cognito_sub (nullable, `AUTH-08`), created_at, updated_at.
     - `user_camera_permissions`: ID, user_id (FK users CASCADE), camera_serial (FK camera CASCADE), created_at, unique constraint on (user_id, camera_serial).
     - `sessions`: ID (64-char hex token), user_id (FK users CASCADE), created_at, expires_at (indexed), last_active_at, user_agent, ip_address.
     - `audit_logs`: ID, timestamp (indexed), actor_id, actor_username, ip_address, action (indexed), resource_type, resource_id, details_json.
     - `camera_outages`: ID, camera_serial (FK camera CASCADE), started_at (indexed), ended_at, duration_seconds, reason.

3. **SQLAlchemy ORM Models (`src/vizenlink_nvr/db/models.py`):**
   - Defined `User`, `UserCameraPermission`, `Session`, `AuditLog`, and `CameraOutage` models mapped to custom `UtcDateTime` columns.
   - Configured cascading relationships on `Camera` for `user_permissions` and `outages`.

4. **Automated Verification:**
   - Created `tests/unit/test_user_model.py` testing model instantiation, relationship navigation, and `cognito_sub` nullable support (`AUTH-08`).
   - Created `tests/integration/test_auth_migrations.py` validating upgrade to `0004_auth_and_audit`, zero schema drift with `alembic check`, downgrade to `0003_recording_core`, and re-upgrade to head.
   - Proved cascading deletes: deleting a `User` cascades to their `sessions` and `user_camera_permissions`; deleting a `Camera` cascades to its `camera_outages` and `user_camera_permissions`.
   - Updated existing tests (`test_migrations.py`, `test_cli_status.py`, `test_recording_migrations.py`) to align with the new head schema revision `0004_auth_and_audit`.

## Verification Artifacts
- `uv run ruff check src tests`: Clean (0 errors).
- `uv run mypy src`: Success (no issues found in 82 source files).
- `tests/unit/test_argon2_hashing.py`: 5 passed.
- `tests/unit/test_user_model.py`: 2 passed.
- `tests/integration/test_auth_migrations.py`: 2 passed.
