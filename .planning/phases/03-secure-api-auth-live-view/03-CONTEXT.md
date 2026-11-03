# Phase 3: Secure API, Auth & Live View - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 is the **first exposure of the NVR to the Local Area Network (LAN)**:
- First-run Web Setup Wizard walks the owner through creating the Owner account (Argon2id, min 8 chars, no default credentials), selecting the site timezone, and setting/confirming the storage location;
- Session-based authentication with HTTP-only, `SameSite=Lax` secure cookies, password change, and brute-force rate-limiting (5 failed attempts -> 15 min lock);
- Three-tier server-side RBAC (`owner`, `operator`, `viewer`) enforced across all `/api/v1` endpoints;
- Per-user camera restrictions (`user_camera_permissions`) restricting Viewer accounts to specific camera serials;
- User management by Owner/Admin: add, edit, disable users, and reset passwords;
- Signed media tokens and MediaMTX HTTP authentication webhook (`authMethod: http`) enforcing stream authorization for WebRTC, HLS, and RTSP;
- Versioned REST API under `/api/v1` with published OpenAPI 3.1 schema and breaking-change verification in CI (MOB-01);
- User data model with nullable `cognito_sub` field for future cloud linking (AUTH-08);
- Audit logging table recording logins, failures, camera operations, setting changes, user management, and exports;
- Responsive React + Vite + Tailwind CSS Single Page Application served directly by FastAPI;
- Live Multiview Grid supporting 1×1, 2×2, 3×3, and 4×4 layouts with pagination;
- Sub-stream by default in grid tiles, auto-switching to main stream on zoom/fullscreen (LIVE-03);
- WebRTC WHEP video player with automatic HLS fallback;
- True tile connection state indicators (connecting, live, offline) with auto-reconnection (LIVE-04);
- Tile controls: snapshot download, maximize, mute/unmute, camera name overlay, and recording indicator badge (LIVE-05);
- Layout persistence in browser `localStorage` (LIVE-06);
- Simple vs. Advanced view toggle (AUTH-06);
- Health Dashboard summarizing cameras online, recording, storage telemetry, active alerts, and camera outage history (HLTH-02, HLTH-07, HLTH-08).

Requirements: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06, MOB-01, HLTH-02, HLTH-07, HLTH-08.

Out of this phase:
- Camera events ingestion (ONVIF PullPoint) and event-triggered recording belong to Phase 4.
- Timeline scrubbing, historical playback, MP4 clip export, and recordings search belong to Phase 5 (LIVE-07 belongs to Phase 5).
- Capability-gated camera imaging/encoding settings belong to Phase 6.
- Mobile mDNS discovery and mobile app pairing belong to Phase 7.
- Cross-platform daemon packaging and 16-camera soak belong to Phase 8.

</domain>

<decisions>
## Implementation Decisions

The user approved the core defaults and architectures established in the discussion. Every decision below locks Phase 3 behavior.

### 1. Setup Wizard & Local Auth (AUTH-01, AUTH-02)
- **D-41: First-run setup wizard and session authentication.**
  - If no users exist in the database, any API request or web visit returns/redirects to `/setup`.
  - The wizard requires:
    1. Initial `owner` username and password (validated: minimum 8 characters; password hashed with Argon2id using `argon2-cffi`).
    2. Site timezone selection (validated against `zoneinfo`).
    3. Storage root confirmation or update (with system disk safeguard check).
  - Once setup is complete, setup endpoints are permanently locked.
  - Authentication uses HTTP-only, `SameSite=Lax` session cookies storing a cryptographically random session token (32 bytes hex).
  - Brute-force rate limiting: 5 consecutive failed login attempts within a 15-minute sliding window triggers a 15-minute temporary lockout for that username/IP.
  - Authenticated users can update their own password via `/api/v1/auth/password`.

### 2. Media Authorization & Stream Security (AUTH-03, AUTH-05, LIVE-01)
- **D-42: MediaMTX HTTP media auth webhook & signed media tokens.**
  - MediaMTX configuration is updated to set:
    - `authMethod: http`
    - `authHTTPAddress: http://127.0.0.1:<PORT>/api/v1/auth/mediamtx`
  - When a user views a camera, the frontend requests an ephemeral signed media token:
    - `POST /api/v1/cameras/{serial}/media-token?stream={main|sub}`
    - Returns a signed token (HMAC-SHA256) encoding `sub` (user_id), `serial`, `stream`, and `exp` (15 minutes).
  - WebRTC (WHEP) and HLS requests to MediaMTX pass the media token in query parameter `?token=<TOKEN>`.
  - MediaMTX calls `/api/v1/auth/mediamtx` with payload `{"ip": "...", "user": "...", "password": "...", "path": "cam/{serial}/{stream}", "protocol": "...", "action": "read", "query": "token=..."}`.
  - The webhook verifies:
    1. If `action == "api"` and `user == "nvr-control"`, allows loopback access using the internal control secret.
    2. If `action == "read"`, parses and verifies the signed token, checking expiration and ensuring `token.serial == path.serial` and `token.stream == path.stream`.
    3. Checks that the user is active and has access to the camera (via `user_camera_permissions` if role is `viewer`).
  - Unauthorized or expired access attempts are rejected with HTTP 401/403.

### 3. REST API & User Data Model (AUTH-03, AUTH-04, AUTH-05, AUTH-08, MOB-01)
- **D-43: OpenAPI 3.1 REST API & RBAC data model.**
  - Database migration `0004_auth_and_audit.py` introduces:
    - `users`: `id`, `username`, `password_hash`, `role` (`owner`, `operator`, `viewer`), `is_active`, `cognito_sub` (nullable Text), `created_at`, `updated_at`.
    - `user_camera_permissions`: `id`, `user_id`, `camera_serial`, `created_at`.
    - `sessions`: `id`, `user_id`, `created_at`, `expires_at`, `last_active_at`, `user_agent`, `ip_address`.
    - `camera_outages`: `id`, `camera_serial`, `started_at`, `ended_at`, `duration_seconds`, `reason`.
  - REST API routes under `/api/v1/`:
    - `/auth`: login, logout, setup, me, password, mediamtx webhook.
    - `/users`: list, create, edit, disable, reset password (Owner/Admin only).
    - `/cameras`: list (filtered by user permissions), get, add, update, remove, reprobe.
    - `/cameras/{serial}/media-token`: issue stream token.
    - `/recording`: per-camera modes, schedules, audio toggle, retention.
    - `/storage`: disk status, retention estimates, set path, run scan.
    - `/health`: recorder status, active alerts, camera outages summary.
    - `/audit-logs`: query audit events with pagination and filters.
  - OpenAPI 3.1 document generated and exported at `/api/v1/openapi.json`.
  - Breaking-change detector tool (`tools/check_api_breaking_changes.py`) in CI ensures backward compatibility.

### 4. Audit Logging (AUTH-07)
- **D-44: Persistent SQLite audit log.**
  - Database table `audit_logs`:
    - `id`, `timestamp` (UTC), `actor_id`, `actor_username`, `ip_address`, `action`, `resource_type`, `resource_id`, `details_json`.
  - Audit events captured automatically via service hooks and FastAPI middleware:
    - `auth.login_success`, `auth.login_failed`, `auth.logout`, `auth.password_changed`
    - `camera.added`, `camera.removed`, `camera.updated`
    - `user.created`, `user.updated`, `user.disabled`, `user.password_reset`
    - `recording.mode_changed`, `recording.schedule_changed`, `recording.retention_changed`
    - `storage.path_changed`, `storage.scan_triggered`
  - Audit log query endpoint with pagination and filtering by actor, action, date range, and resource.

### 5. Frontend Web Application & Live Multiview Grid (LIVE-01 to LIVE-06, AUTH-06, HLTH-02, HLTH-07, HLTH-08)
- **D-45: React SPA, WebRTC WHEP player, and Live Grid.**
  - Single Page Application built with React 18, Vite, Tailwind CSS, Lucide icons, and TanStack Query.
  - Served statically by FastAPI at `/` (production build files copied or served from `web/dist` or bundled assets).
  - Video Player:
    - WebRTC WHEP client (`/cam/{serial}/{stream}/whep?token={token}`) for sub-second latency.
    - Automatic fallback to HLS (`/cam/{serial}/{stream}/index.m3u8?token={token}`) if WebRTC fails to establish peer connection.
  - Live Grid:
    - Supports 1×1, 2×2, 3×3, 4×4 grid layouts with pagination.
    - Uses sub-stream by default for all tiles to conserve system resources (`LIVE-03`).
    - Clicking/maximizing a tile auto-switches to the camera's high-resolution main stream.
    - Tile controls: snapshot frame grab, maximize/fullscreen, audio mute/unmute, camera name overlay, and dual health badges (online, recording).
    - True tile states: `connecting`, `live`, `offline`, `error` (never a frozen frame presented as live; auto-reconnects with backoff).
    - Grid layout and camera slot arrangements are persisted in browser `localStorage`.
  - Simple vs. Advanced view toggle in header:
    - Simple view hides low-level stream technical details (codecs, bitrates, disk sectors).
    - Advanced view reveals full operational telemetry, bitrates, segment stats, and low-water mark indicators.
  - Dashboard & Alerts:
    - Summary widgets: cameras online, cameras recording, storage consumed/free, estimated retention, active alerts.
    - In-app alerts banner/toast: camera offline > N minutes, disk space low, recording gaps.
    - Outage history drawer/dialog showing recent disconnects, duration, and recovery timestamps.

</decisions>
