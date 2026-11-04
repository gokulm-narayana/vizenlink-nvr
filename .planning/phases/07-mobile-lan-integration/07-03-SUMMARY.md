# Plan 07-03 Summary: Mobile REST API Endpoints & OpenAPI Baseline (MOB-03 through MOB-07)

## Outcome
Implemented the Mobile REST API router under `/api/v1/mobile` covering pairing, live streaming relay, recorded history, health telemetry, and camera management, while maintaining full backward compatibility with the OpenAPI 3.1 baseline.

## Deliverables
1. **Mobile REST API Router (`src/vizenlink_nvr/api/v1/mobile.py`):**
   - **Device Pairing & Tokens (`MOB-03`):**
     - `POST /api/v1/mobile/pair`: Direct credential pairing issuing 256-bit access and refresh tokens.
     - `POST /api/v1/mobile/pair-qr`: Single-use ephemeral QR pairing claim.
     - `POST /api/v1/mobile/refresh`: Access token rotation using unrevoked refresh token.
     - `POST /api/v1/mobile/qr/init`: Web session QR initiation.
     - `GET /api/v1/mobile/devices`: List paired devices (all for Owner, self for other users).
     - `POST /api/v1/mobile/devices/{device_id}/revoke` & `DELETE`: Immediate device access invalidation.
   - **Live Streaming Relay (`MOB-04`):**
     - `GET /api/v1/mobile/cameras/{camera_id}/live-stream`: Defaults to lightweight `sub` stream profile (with `main` option), generating signed HMAC media tokens in WHEP WebRTC, HLS, and RTSP stream URLs.
   - **Recorded History (`MOB-05`):**
     - `GET /api/v1/mobile/cameras/{camera_id}/recording-dates`: Delivers dates with recorded footage for calendar timeline.
     - `GET /api/v1/mobile/cameras/{camera_id}/recordings`: Returns daily clip list with timestamps, size, duration, trigger classification (`continuous` vs `event`), and byte-range stream URLs.
   - **Health & Storage Status (`MOB-06`):**
     - `GET /api/v1/mobile/status`: Consolidated system health, storage telemetry (total, used, free, retention days), and per-camera recording and connectivity status.
   - **Camera Management & RBAC (`MOB-07`):**
     - `POST /api/v1/mobile/cameras`: Onboard camera (Owner only).
     - `DELETE /api/v1/mobile/cameras/{camera_id}`: Remove camera (Owner only).
     - `PUT /api/v1/mobile/cameras/{camera_id}/recording-mode`: Change recording policy (Operator/Owner only, Viewers receive HTTP 403 Forbidden).
2. **FastAPI Application Wiring (`src/vizenlink_nvr/api/app.py`):**
   - Included `mobile_router` under `/api/v1/mobile`.
3. **OpenAPI 3.1 Baseline Update (`contracts/openapi_v1_baseline.json`):**
   - Updated OpenAPI contract baseline via `tools/check_api_breaking_changes.py --update`.
4. **Integration Verification (`tests/integration/test_mobile_api.py`):**
   - 4 integration tests verifying pairing lifecycle, token rotation, live streaming sub-stream defaults, recordings calendar, mobile health telemetry, and strict RBAC enforcement.

## Verification
- `uv run pytest tests/integration/test_mobile_api.py -v`: 4 passed in 0.97s.
- `uv run ruff check src/vizenlink_nvr/api/v1/mobile.py`: All checks passed.
- `uv run mypy src/vizenlink_nvr/api/v1/mobile.py`: All checks passed.
- `uv run python tools/check_api_breaking_changes.py`: Success, backward-compatible.

