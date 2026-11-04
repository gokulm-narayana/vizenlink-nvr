# Plan 03-04: MediaMTX HTTP Media Auth Webhook & Signed Media Tokens Summary

**Execution Date:** 2026-11-04  
**Status:** Completed  
**Requirements:** AUTH-03, AUTH-05, LIVE-01

---

## 1. Summary of Delivered Capabilities

1. **HMAC-SHA256 Signed Ephemeral Media Tokens (`src/vizenlink_nvr/services/media_token.py`):**
   - Implemented `MediaTokenService` with URL-safe base64 encoding and HMAC-SHA256 signatures.
   - Bound tokens cryptographically to `user_id`, `camera_serial`, and `stream` (`main` or `sub`).
   - Default TTL of 900 seconds (15 minutes) with cryptographic replay nonce.
   - Robust verification rejecting expired tokens, tampered signatures, or mutated payloads.

2. **MediaMTX Configuration Update (`src/vizenlink_nvr/media/config.py`):**
   - Configured `authMethod: "http"` and `authHTTPAddress: "http://127.0.0.1:8000/api/v1/auth/mediamtx"`.
   - Maintained strict default-deny and explicit loopback address binding.

3. **Camera Media Token Endpoint (`src/vizenlink_nvr/api/v1/cameras.py`):**
   - `POST /api/v1/cameras/{serial}/media-token?stream={main|sub}`.
   - Enforces user authentication and camera-level authorization via `verify_camera_access(serial, user)`.
   - Returns `{token, expires_in, stream, path}`.

4. **MediaMTX HTTP Authentication Webhook (`src/vizenlink_nvr/api/v1/auth.py`):**
   - `POST /api/v1/auth/mediamtx`:
     - Case 1 (`action == "api"`): Requires loopback IP and control credentials (`nvr-control`).
     - Case 2 (`action == "read"`): Validates query param `token=...`, path alignment (`cam/{serial}/{stream}`), active user status, and RBAC camera whitelist permissions.
     - Case 3 (all other external actions, including `publish`): Rejected with HTTP 403 Forbidden.

5. **Automated Verification:**
   - `tests/unit/test_media_token.py`: 5 passed.
   - `tests/unit/test_mediamtx_config.py`: 3 passed.
   - `tests/integration/test_media_auth_webhook.py`: 5 passed.
   - `tests/integration/test_mediamtx_http_auth.py`: 1 passed.

---

## 2. Key Decisions & Architecture Alignment
- Anonymous stream access is strictly prohibited across all protocols (WebRTC, HLS, RTSP).
- Media tokens are ephemeral, reducing exposure risk without maintaining state in a central session database for every frame or stream packet.
- Fast, local HMAC verification occurs inside the NVR auth webhook before database checks for active user status and permission grants.
