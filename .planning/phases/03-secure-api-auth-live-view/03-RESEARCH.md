# Phase 3: Secure API, Auth & Live View - Research

**Date:** 2026-11-03
**Status:** Approved

## Executive Summary

Phase 3 transitions the VizenLink NVR from an isolated, headless CLI daemon to a secure, networked NVR appliance accessible over the LAN via a modern web interface and REST API. This document establishes the technical foundations, security architecture, protocol flows, and verification strategies required to deliver Phase 3.

---

## 1. Security Architecture & Threat Model

### 1.1 Threat Model for LAN Exposure
- **Threat:** Unauthorized LAN actors accessing video feeds or camera control.
  - **Mitigation:** Default-deny posture. MediaMTX video endpoints reject all anonymous connections. All WebRTC, HLS, and RTSP requests require signed ephemeral media tokens validated via an internal loopback authentication webhook.
- **Threat:** Credential stuffing and brute-force password guessing.
  - **Mitigation:** Rate-limiting middleware (5 failed attempts per username or IP in 15 minutes triggers a 15-minute lockout). Argon2id password hashing with randomized per-user salts.
- **Threat:** Session hijacking or cross-site scripting (XSS) credential theft.
  - **Mitigation:** HTTP-only, `SameSite=Lax`, cryptographically random 256-bit session tokens stored in secure cookies. No sensitive credentials or passwords stored in browser `localStorage`.
- **Threat:** Privilege escalation or unauthorized camera access.
  - **Mitigation:** Strict 3-tier server-side RBAC (`owner`, `operator`, `viewer`). Viewer accounts are restricted to whitelisted camera serials verified on every API and media stream request.

### 1.2 Password Hashing (Argon2id)
Argon2id (`argon2-cffi`) provides state-of-the-art resistance to GPU cracking and side-channel attacks:
```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

def hash_password(password: str) -> str:
    return hasher.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
```

### 1.3 Media Authorization Protocol (MediaMTX HTTP Auth)
MediaMTX supports external authentication via HTTP POST:
- **MediaMTX Configuration:**
  ```yaml
  authMethod: http
  authHTTPAddress: http://127.0.0.1:8000/api/v1/auth/mediamtx
  ```
- **MediaMTX Request Format:**
  When a client requests a stream (e.g. `GET /cam/SN123/sub/whep?token=XYZ`):
  ```json
  {
    "ip": "192.168.1.50",
    "user": "",
    "password": "",
    "path": "cam/SN123/sub",
    "protocol": "webrtc",
    "id": "conn-uuid",
    "action": "read",
    "query": "token=XYZ"
  }
  ```
- **Webhook Response:**
  - HTTP `200 OK`: Access granted.
  - HTTP `401 Unauthorized` or `403 Forbidden`: Access denied.
- **Token Signing & Verification:**
  - Token payload: `{"sub": user_id, "serial": "SN123", "stream": "sub", "exp": 1730630000}`.
  - Signed using HMAC-SHA256 with the NVR instance secret (stored in encrypted vault or generated per NVR lifecycle).
  - Validation: checks signature, expiration, matches path to `cam/{token.serial}/{token.stream}`, and verifies user is active with access permissions.

---

## 2. API Design & OpenAPI 3.1 Contract

### 2.1 Router Structure (`/api/v1`)
- `/api/v1/auth`:
  - `GET /status`: Returns setup status (`initialized: bool`, `authenticated: bool`).
  - `POST /setup`: First-run wizard: create Owner account, set timezone, configure storage path.
  - `POST /login`: Session login; sets HTTP-only session cookie.
  - `POST /logout`: Invalidates session.
  - `GET /me`: Returns current user identity, role, and camera permissions.
  - `POST /password`: Change own password.
  - `POST /mediamtx`: Loopback HTTP auth webhook for MediaMTX.
- `/api/v1/users`:
  - `GET /`: List all users (Owner/Admin only).
  - `POST /`: Create new user with role and camera whitelist.
  - `GET /{id}`: User details and camera permissions.
  - `PATCH /{id}`: Update user role, status (active/disabled), and camera permissions.
  - `POST /{id}/reset-password`: Reset user password.
- `/api/v1/cameras`:
  - `GET /`: List registered cameras (filtered by caller permissions).
  - `GET /{serial}`: Camera details, streams, and capabilities.
  - `POST /`: Onboard a new camera (re-uses existing onboarding engine).
  - `DELETE /{serial}`: Remove camera with `keep_recordings: bool`.
  - `POST /{serial}/reprobe`: Refresh capabilities and streams.
  - `POST /{serial}/media-token`: Issue 15-minute signed media token for main or sub stream.
- `/api/v1/recording`:
  - `GET /status`: Recording status for all cameras.
  - `PATCH /{serial}`: Update mode, schedule, audio, retention.
- `/api/v1/storage`:
  - `GET /status`: Storage telemetry, mountpoint, disk space, retention estimate.
  - `POST /set-path`: Update storage directory path.
  - `POST /scan`: Trigger manual disk reconciliation scan.
- `/api/v1/health`:
  - `GET /`: Recorder health summary, active alerts.
  - `GET /outages`: Camera outage history.
- `/api/v1/audit-logs`:
  - `GET /`: Query audit log records with filtering and pagination.

### 2.2 Breaking Change Detection
To fulfill `MOB-01`:
1. Generate `openapi.json` from the FastAPI application.
2. In CI and local verification, run `tools/check_api_breaking_changes.py` comparing the generated schema against `contracts/openapi_v1_baseline.json`.
3. Breaking changes (removed endpoints, renamed query parameters, changed required request/response fields) fail CI.

---

## 3. WebRTC WHEP & HLS Player Integration

### 3.1 WebRTC HTTP Egress Protocol (WHEP)
- MediaMTX natively exposes WHEP endpoints at `http://127.0.0.1:8889/{path}/whep`.
- Browser flow:
  1. Frontend requests media token: `POST /api/v1/cameras/{serial}/media-token?stream=sub`.
  2. Frontend creates `RTCPeerConnection` with ICE servers (STUN/loopback).
  3. Frontend creates SDP offer with `addTransceiver("video", {direction: "recvonly"})`.
  4. Frontend sends `POST http://<nvr_host>:8889/cam/{serial}/{stream}/whep?token={token}` with `Content-Type: application/sdp`.
  5. MediaMTX verifies token via webhook, creates session, and replies with HTTP 201 and remote SDP answer.
  6. Frontend sets remote description; sub-second video stream starts immediately.

### 3.2 HLS Fallback Mechanism
- If the WHEP connection fails to negotiate or times out (e.g., corporate firewall blocking UDP), the video tile automatically falls back to HLS.
- MediaMTX HLS URL: `http://<nvr_host>:8888/cam/{serial}/{stream}/index.m3u8?token={token}`.
- Handled using `hls.js` or native `<video>` element on Safari/iOS.

### 3.3 Dynamic Sub/Main Stream Switching (LIVE-03)
- In the multiview grid (1×1, 2×2, 3×3, 4×4), all tiles default to the camera's sub-stream.
- When the user clicks the "Maximize" button on a tile or zooms into full view:
  1. The tile pauses the sub-stream connection.
  2. Requests a main-stream media token: `POST /api/v1/cameras/{serial}/media-token?stream=main`.
  3. Initiates WHEP connection to `cam/{serial}/main/whep?token={main_token}`.
- Restoring the grid reverses the process back to sub-stream, keeping resource consumption optimal.

---

## 4. Frontend Architecture & Technology Stack

- **Framework:** React 18 with TypeScript.
- **Build Tool:** Vite (fast compilation and minimal production bundle size).
- **Styling:** Tailwind CSS (responsive layouts, dark mode optimized for security monitoring).
- **Icons:** Lucide React (clean, accessible iconography).
- **State Management:** TanStack Query (React Query) for API caching, automatic background refetching, and real-time status polling.
- **Storage:** Browser `localStorage` stores:
  - Selected grid layout (1×1, 2×2, 3×3, 4×4).
  - Slot assignments (which camera serial is placed in which tile).
  - UI mode preference (Simple vs. Advanced).
- **Packaging:** The compiled frontend is placed in `src/vizenlink_nvr/web/dist` and served statically by FastAPI. In development mode, Vite's proxy forwards `/api` calls to FastAPI.

---

## 5. Database Schema Additions (Migration 0004)

- **`users`:**
  - `id` (INTEGER, PK, autoincrement)
  - `username` (TEXT, unique, not null)
  - `password_hash` (TEXT, not null)
  - `role` (TEXT, not null) - check `role IN ('owner', 'operator', 'viewer')`
  - `is_active` (BOOLEAN, not null, default True)
  - `cognito_sub` (TEXT, nullable)
  - `created_at` (UtcDateTime, not null)
  - `updated_at` (UtcDateTime, not null)
- **`user_camera_permissions`:**
  - `id` (INTEGER, PK, autoincrement)
  - `user_id` (INTEGER, FK users.id CASCADE, not null)
  - `camera_serial` (TEXT, FK camera.serial CASCADE, not null)
  - `created_at` (UtcDateTime, not null)
  - UniqueConstraint(`user_id`, `camera_serial`)
- **`sessions`:**
  - `id` (TEXT, PK) - 64-char hex token
  - `user_id` (INTEGER, FK users.id CASCADE, not null)
  - `created_at` (UtcDateTime, not null)
  - `expires_at` (UtcDateTime, not null)
  - `last_active_at` (UtcDateTime, not null)
  - `user_agent` (TEXT, nullable)
  - `ip_address` (TEXT, nullable)
- **`audit_logs`:**
  - `id` (INTEGER, PK, autoincrement)
  - `timestamp` (UtcDateTime, not null, index)
  - `actor_id` (INTEGER, nullable)
  - `actor_username` (TEXT, nullable)
  - `ip_address` (TEXT, nullable)
  - `action` (TEXT, not null, index)
  - `resource_type` (TEXT, not null)
  - `resource_id` (TEXT, nullable)
  - `details_json` (TEXT, nullable)
- **`camera_outages`:**
  - `id` (INTEGER, PK, autoincrement)
  - `camera_serial` (TEXT, FK camera.serial CASCADE, not null, index)
  - `started_at` (UtcDateTime, not null, index)
  - `ended_at` (UtcDateTime, nullable)
  - `duration_seconds` (FLOAT, nullable)
  - `reason` (TEXT, nullable)

---

## 6. Phase Execution Waves

We divide Phase 3 into 8 sequential, cohesive plans:
1. **03-01 (Wave 1): Database Migration 0004 & Data Models**
   - Migration script `0004_auth_and_audit.py`.
   - SQLAlchemy models: `User`, `UserCameraPermission`, `Session`, `AuditLog`, `CameraOutage`.
   - Argon2id password hashing helper (`src/vizenlink_nvr/services/auth_hasher.py`).
2. **03-02 (Wave 2): Authentication Service, Sessions & Rate Limiting**
   - Setup status checker, Owner creation logic.
   - Session manager (create, validate, expire, sliding window).
   - In-memory sliding window brute-force lockout (5 attempts -> 15 min lock).
   - Cookie management (HTTP-only, SameSite=Lax).
3. **03-03 (Wave 3): Server-Side RBAC & User Management Endpoints**
   - FastAPI dependencies: `get_current_user`, `require_role(min_role)`, `require_camera_access(serial)`.
   - User administration endpoints (`/api/v1/users`): list, create, edit, disable, reset password.
   - Enforce viewer camera whitelist.
4. **03-04 (Wave 4): MediaMTX HTTP Media Auth Webhook & Ephemeral Tokens**
   - Media token generation service (HMAC-SHA256, 15-minute TTL).
   - MediaMTX configuration update (`authMethod: http`, `authHTTPAddress`).
   - Webhook endpoint `/api/v1/auth/mediamtx` validating tokens and loopback control access.
   - Tests ensuring anonymous media requests are denied.
5. **03-05 (Wave 5): Core REST API Endpoints & OpenAPI Contract Guard**
   - Routers for `/api/v1/cameras`, `/api/v1/recording`, `/api/v1/storage`, `/api/v1/health`.
   - Publish OpenAPI 3.1 schema at `/api/v1/openapi.json`.
   - Tool `tools/check_api_breaking_changes.py` for CI breaking change detection.
6. **03-06 (Wave 6): Audit Logging Service & Outage Tracking**
   - Audit logger service recording auth, camera, user, and config actions.
   - Query endpoint `/api/v1/audit-logs` with pagination and filters.
   - Camera outage tracker recording disconnects, reconnects, and duration (HLTH-08).
   - In-app alert service evaluating offline duration, disk space, and gaps (HLTH-07).
7. **03-07 (Wave 7): React Web Application & Live Multiview Grid**
   - React + Vite SPA with Tailwind CSS.
   - Setup Wizard view and Login view.
   - Live Multiview Grid (1×1 to 4×4) with WHEP player and HLS fallback.
   - Sub-stream default with automatic main-stream switch on tile enlargement.
   - Tile controls: snapshot download, maximize, mute, name overlay, recording badge.
   - Persist layout and camera arrangement in `localStorage`.
8. **03-08 (Wave 8): Health Dashboard, View Toggles & End-to-End Tracer**
   - Health dashboard view: camera counts, storage meter, active alerts, outage history.
   - Simple vs. Advanced view toggle (AUTH-06).
   - End-to-end integration tracer testing the entire LAN workflow from setup wizard -> login -> camera permission check -> media token -> live video -> audit trail.
   - Phase 3 verification gate check.
