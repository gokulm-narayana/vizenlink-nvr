# Phase 07: Mobile LAN Integration - Research & Technical Specifications

## 1. mDNS Discovery (python-zeroconf)
- **Standard Service Type:** `_vizenlink-nvr._tcp.local.`
- **Service Name:** `VizenLink-NVR-{nvr_id}._vizenlink-nvr._tcp.local.`
- **TXT Record Dictionary:**
  ```python
  properties = {
      "api_version": "v1",
      "nvr_id": nvr_id,
      "name": nvr_name,
      "model": "VizenLink-NVR",
      "port": str(port),
      "tls": "false",
      "version": "0.1.0",
  }
  ```
- **Lifecycle Integration:**
  - `zeroconf.Zeroconf` instance initialized on FastAPI startup (or background service).
  - Registers `ServiceInfo`.
  - Unregisters on shutdown (`zc.unregister_service(info)` and `zc.close()`).
  - Unit tests can mock socket/zeroconf networking to ensure deterministic execution in sandboxed environments.

## 2. Pairing & Device Token Architecture
- **Pairing Methods:**
  1. **Direct Credentials:**
     - Endpoint: `POST /api/v1/mobile/pair`
     - Request: `{ "username": "...", "password": "...", "device_id": "...", "device_name": "...", "platform": "ios"|"android" }`
     - Validates username and password via `UserManager.authenticate_user(...)`.
  2. **QR-Code Scan:**
     - Web UI endpoint: `POST /api/v1/mobile/qr/init` creates a `QRPairingSession` (valid for 5 minutes).
     - Returns QR code string: `vizenlink://pair?nvr_id=...&host=...&port=...&pairing_code=...`.
     - Mobile endpoint: `POST /api/v1/mobile/pair-qr`
     - Request: `{ "pairing_code": "...", "device_id": "...", "device_name": "...", "platform": "ios"|"android" }`
     - Validates pairing code, marks session claimed.
- **Tokens Issued:**
  - `access_token`: Cryptographic 256-bit token (hex) with 15-minute to 1-hour expiration.
  - `refresh_token`: Cryptographic 256-bit token (hex) with 30-day sliding expiration.
- **Revocation:**
  - Table `paired_devices` stores `is_revoked: bool` and `revoked_at`.
  - Admin endpoint `DELETE /api/v1/mobile/devices/{id}` or `POST /api/v1/mobile/devices/{id}/revoke`.
  - Session validation checks `paired_device.is_revoked` before accepting any mobile token; if revoked, returns HTTP 401.

## 3. Mobile Live Streaming Relay
- Endpoint: `GET /api/v1/mobile/cameras/{camera_id}/live-stream?profile=sub|main`
- Defaults to `profile="sub"` for lightweight mobile view.
- Generates MediaMTX media authorization token valid for read action on path `{serial}_{profile}`.
- Returns stream URLs:
  - `webrtc_url`: `http://{nvr_host}:{mediamtx_port}/{path}/whep?token={media_token}`
  - `hls_url`: `http://{nvr_host}:{mediamtx_port}/{path}/index.m3u8?token={media_token}`
  - `rtsp_url`: `rtsp://{nvr_host}:{rtsp_port}/{path}?token={media_token}`

## 4. Mobile Recordings History & Timeline
- Endpoint: `GET /api/v1/mobile/cameras/{camera_id}/recording-dates`
  - Returns list of dates that contain recorded segments: `["2026-11-03", "2026-11-04"]`.
- Endpoint: `GET /api/v1/mobile/cameras/{camera_id}/recordings?date=YYYY-MM-DD`
  - Returns structured clips matching `camera_api` timeline expectations:
    - `id`: unique segment or event-span id
    - `start_time`: ISO 8601 UTC string
    - `end_time`: ISO 8601 UTC string
    - `duration_seconds`: float
    - `size_bytes`: int
    - `trigger`: string (`continuous`, `motion`, `line_cross`, `tamper`)
    - `stream_url`: `/api/v1/playback/stream/{segment_id}`

## 5. Mobile Health & Storage Telemetry
- Endpoint: `GET /api/v1/mobile/status`
  - Consolidates system status:
    - NVR status: `healthy` / `degraded`
    - Storage: disk total bytes, used bytes, free bytes, estimated retention days
    - Per-camera metrics:
      - `serial`, `name`, `is_online`, `is_recording`, `current_bitrate_kbps`, `storage_used_bytes`

## 6. Mobile Management Endpoints
- Add Camera: `POST /api/v1/mobile/cameras` (Owner/Admin)
- Remove Camera: `DELETE /api/v1/mobile/cameras/{camera_id}` (Owner/Admin)
- Set Recording Mode: `PUT /api/v1/mobile/cameras/{camera_id}/recording-mode` (Owner/Operator)
  - Viewers rejected with HTTP 403 Forbidden.
