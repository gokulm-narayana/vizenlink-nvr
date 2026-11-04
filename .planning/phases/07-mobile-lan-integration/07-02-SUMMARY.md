# Plan 07-02 Summary: Mobile Pairing Models, Database Migration 0007 & MobileAuthService (MOB-03)

## Outcome
Implemented the database models (`PairedDevice`, `QRPairingSession`), Alembic migration `0007_mobile_pairing`, and the complete `MobileAuthService` handling QR code enrollment, direct credential enrollment, token rotation, administrative device revocation, and Bearer token dependency authentication.

## Deliverables
1. **Database Schema & Models (`src/vizenlink_nvr/db/models.py`, `src/vizenlink_nvr/db/migrations/versions/0007_mobile_pairing.py`):**
   - Added `PairedDevice` capturing `device_id`, `device_name`, `platform`, `user_id`, `access_token`, `refresh_token`, expiration timestamps, and `is_revoked`.
   - Added `QRPairingSession` capturing `pairing_code`, `user_id`, `expires_at`, and `claimed`.
   - Migration 0007 passes Alembic upgrade and schema drift check with 0 warnings.
2. **Mobile Authentication Service (`src/vizenlink_nvr/services/mobile_auth.py`):**
   - `create_qr_pairing_session`: Generates single-use 32-hex pairing code with 5-minute TTL and URI payload.
   - `pair_via_qr`: Validates pairing code, claims session, creates/updates paired device record, and issues access & refresh tokens.
   - `pair_via_credentials`: Validates user password against Argon2id hash, records audit logs, and issues device tokens.
   - `refresh_token`: Rotates access token for active, unrevoked devices.
   - `validate_mobile_token`: Validates access token and expiration, respecting revocation and inactive accounts with sliding last-seen tracking.
   - `revoke_device`: Marks device `is_revoked=True`, immediately invalidating access across all endpoints.
   - `list_devices`: Lists paired devices with user scoping.
3. **Dependency Integration (`src/vizenlink_nvr/api/dependencies.py`):**
   - Updated `get_current_user_optional` to authenticate mobile Bearer tokens via `MobileAuthService.validate_mobile_token`.
4. **Unit Verification (`tests/unit/test_mobile_auth.py`):**
   - 5 unit tests covering QR pairing, TTL expiration, credential pairing, refresh rotation, revocation enforcement, and device listing.

## Verification
- `uv run alembic upgrade head && uv run alembic check`: Upgrade passed, 0 drift.
- `uv run pytest tests/unit/test_mobile_auth.py -v`: 5 passed in 0.75s.
- `uv run ruff check` & `uv run mypy`: All checks passed.
