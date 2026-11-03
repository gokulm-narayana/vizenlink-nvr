# Phase 3: Secure API, Auth & Live View - Discussion Log

**Date:** 2026-11-03
**Status:** Complete

## User Alignment & Decisions

An interactive alignment discussion was conducted covering the 4 primary architecture and design areas for Phase 3. The user approved all recommended options.

---

### 1. Setup Wizard & Local Authentication (AUTH-01, AUTH-02)

- **Decision:** Web Setup Wizard on first visit to uninitialized NVR.
- **Workflow:**
  - When the NVR has no users configured, all requests redirect to `/setup`.
  - The wizard walks the user through:
    1. Creating the initial **Owner** account (username + password; minimum 8 characters; hashed with Argon2id; strictly no default credentials).
    2. Confirming/selecting the site timezone (e.g., `UTC` or `America/New_York`).
    3. Setting/confirming the storage directory path and confirming disk safeguards.
  - Subsequent requests require authentication via HTTP-only, `SameSite=Lax` secure session cookies.
  - Brute-force protection: 5 consecutive failed login attempts for a given username or IP triggers a 15-minute temporary lockout.
  - Password change endpoint allows authenticated users to update their credentials.

---

### 2. Media Authorization & Stream Security (AUTH-03, AUTH-05, LIVE-01)

- **Decision:** Ephemeral signed media tokens with MediaMTX HTTP authentication webhook.
- **Workflow:**
  - MediaMTX is configured with `authMethod: http` pointing to the NVR's internal authentication endpoint: `http://127.0.0.1:<PORT>/api/v1/auth/mediamtx`.
  - Authenticated clients request a short-lived (15-minute) signed media token for a camera stream via `/api/v1/cameras/{serial}/media-token?stream={main|sub}`.
  - When the browser or media player connects to MediaMTX over WebRTC (WHEP), HLS, or RTSP, it passes the media token in the query string (`?token=...`).
  - MediaMTX invokes `/api/v1/auth/mediamtx`. The endpoint validates:
    1. Token signature and timestamp validity.
    2. User role and camera permission (ensuring Viewer accounts can only access permitted cameras per AUTH-05).
    3. Internal control API actions (`user=nvr-control`) originate from loopback.
  - Any unauthorized access attempt receives HTTP 401/403 and is rejected.

---

### 3. Frontend Architecture & Multiview Video Grid (LIVE-01 to LIVE-06, AUTH-06)

- **Decision:** React + Vite + Tailwind CSS Single Page Application served directly by FastAPI.
- **Workflow:**
  - Frontend SPA is built with React, Vite, Tailwind CSS, Lucide icons, and TanStack Query.
  - Served statically by the FastAPI backend at `/` (static assets mounted at `/assets`).
  - Video player uses WebRTC WHEP client for sub-second latency, automatically falling back to HLS (`hls.js`) if WebRTC connection fails or UDP is blocked.
  - Grid layout supports 1×1, 2×2, 3×3, and 4×4 layouts with pagination.
  - Sub-stream is used by default for all grid tiles to preserve CPU and bandwidth (`LIVE-03`).
  - Clicking/maximizing a tile seamlessly switches from sub-stream to the high-resolution main stream.
  - Tile controls include: snapshot, maximize, mute, camera name overlay, and live/recording indicator badges.
  - Grid tile arrangement and layout preferences are persisted in browser `localStorage`.
  - Simple vs. Advanced view toggle in UI header (`AUTH-06`): Simple view hides technical bitrate, codec, and storage internals, while Advanced view exposes full telemetry.

---

### 4. RBAC, Audit Logging & Health Telemetry (AUTH-03, AUTH-04, AUTH-05, AUTH-07, AUTH-08, HLTH-02, HLTH-07, HLTH-08, MOB-01)

- **Decision:** 3-Tier RBAC with SQLite Audit Log and Health Telemetry.
- **Workflow:**
  - Roles:
    - `owner`: Full administrative privileges (add/edit/delete users, storage config, all cameras, system settings).
    - `operator`: Live view, playback, snapshot/PTZ controls, view recording settings. Cannot modify users or storage paths.
    - `viewer`: Live view only, strictly restricted to cameras assigned by the admin via `user_camera_permissions`.
  - Audit logging:
    - Events logged: `login_success`, `login_failed`, `camera_added`, `camera_removed`, `setting_changed`, `export_created`, `segment_deleted`, `user_created`, `user_updated`, `user_disabled`, `role_changed`.
    - Logged fields: timestamp, actor_id, actor_username, ip_address, action, resource_type, resource_id, details.
  - Data model includes nullable `cognito_sub` on `users` table for future cloud linking (`AUTH-08`).
  - Health Dashboard (`HLTH-02`, `HLTH-07`, `HLTH-08`):
    - System health summary: online cameras, recording cameras, storage used/free, active alerts.
    - Camera outage history table tracking start, end, and duration of offline events.
    - In-app alerts for offline cameras (> N minutes), disk nearly full (< reserve threshold), and recording gaps.
  - REST API & OpenAPI 3.1 (`MOB-01`):
    - Published at `/api/v1/openapi.json`.
    - Automated CI schema check verifies no breaking contract changes.
