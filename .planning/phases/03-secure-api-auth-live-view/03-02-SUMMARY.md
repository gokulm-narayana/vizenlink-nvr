# Plan 03-02 Summary: Setup Wizard, Session Auth & Brute-Force Rate Limiting

**Execution Date:** 2026-11-03
**Status:** Complete
**Requirements:** `AUTH-01`, `AUTH-02`

## What Was Accomplished

1. **FastAPI & Uvicorn Integration:**
   - Added `fastapi~=0.115` and `uvicorn[standard]~=0.34` dependencies in `pyproject.toml`.
   - Created `src/vizenlink_nvr/api/app.py` providing `create_app()` factory with `/api/v1` router mount and OpenAPI 3.1 configuration.
   - Implemented dependency injection in `src/vizenlink_nvr/api/dependencies.py` (`DbSession`, `CurrentUser`, `CurrentUserOptional`).

2. **First-Run Setup Wizard Service (`AUTH-01`):**
   - Implemented `src/vizenlink_nvr/services/setup.py` (`SetupService`):
     - `is_initialized`: checks whether any user exists in the `users` table.
     - `initialize_nvr`: creates initial Owner account (minimum 8 characters, Argon2id hashed; strictly zero default credentials like `admin/admin`), configures site timezone in `AppSetting`, and verifies storage directory with disk safeguards.
     - Enforces permanent lockout once initialized (subsequent `/setup` calls return HTTP 400).

3. **Session Lifecycle & Cookie Management (`AUTH-02`):**
   - Implemented `src/vizenlink_nvr/services/session_manager.py` (`SessionManager`):
     - Cryptographically secure 256-bit random session tokens (`secrets.token_hex(32)`).
     - Persists sessions in `sessions` table with 7-day TTL and sliding window activity updates.
     - Sets secure, `HTTP-only`, `SameSite=Lax` cookies on authentication responses.
     - Provides session invalidation on logout and user-wide session purging on password changes.

4. **Brute-Force Rate Limiting (`AUTH-02`):**
   - Implemented `src/vizenlink_nvr/services/rate_limiter.py` (`RateLimiter`):
     - In-memory thread-safe sliding window rate limiter.
     - Tracks failed attempts per username and IP.
     - Reaching 5 failures within 15 minutes triggers a 15-minute temporary lockout.
     - Probes during lockout are rejected with HTTP 429 Too Many Requests.
     - Clears failed attempts and lockouts upon successful login.

5. **Authentication REST Router (`/api/v1/auth`):**
   - `GET /api/v1/auth/status`: reports initialization status and current caller profile.
   - `POST /api/v1/auth/setup`: first-run wizard endpoint; sets initial Owner session cookie.
   - `POST /api/v1/auth/login`: authenticates with local credentials, checks rate limits, sets session cookie.
   - `POST /api/v1/auth/logout`: invalidates session token and clears cookie.
   - `GET /api/v1/auth/me`: returns authenticated caller profile, role, and camera permissions.
   - `POST /api/v1/auth/password`: updates password, purges older sessions, and re-issues current session.

## Verification Artifacts

- `uv run ruff check src tests`: Clean (0 errors).
- `uv run mypy src`: Success (no issues found in 90 source files).
- `tests/unit/test_rate_limiter.py`: 3 passed.
- `tests/integration/test_auth_setup_wizard.py`: 1 passed.
- `tests/integration/test_auth_sessions.py`: 1 passed.
- `tests/integration/test_auth_rate_limiting.py`: 1 passed.
