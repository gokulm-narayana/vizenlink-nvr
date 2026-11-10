# Phase 09 Plan 11 Summary: Live Grid Overhaul & Hardened WHEP Player

**Date:** 2026-11-06  
**Commit:** `840cb73`  
**Phase:** 09-ui-redesign  
**Plan:** 11  
**Wave:** 8  

---

## 1. Overview & Objective
Rebuilt the Live monitoring page to the UI-SPEC Live contract and hardened the WebRTC WHEP player:
- Hardened `TilePlayer` (D-17) with disposal guards across asynchronous steps, exponential backoff reconnects (1s, 2s, 4s, 8s, 16s, 30s max), stall detection (>5s frozen frame triggers reconnection), transition to offline status after 3 consecutive failures, WHEP session `DELETE` on cleanup, and removal of public Google STUN servers (`iceServers: []` for LAN-only operation).
- Implemented `LivePage`, `LiveToolbar`, `VideoTile`, `TileOverlay`, and `copy.ts`.
- Grid dimension and page state persist via `GridStorage` under key `vizenlink_nvr_grid_layout_v1`; Simple view caps 4x4 down to 3x3 without modifying storage; 1 camera defaults to 1x1 if unset.
- Tiles negotiate sub-stream in the grid and switch to main stream when maximized. Fullscreen toggle is supported via keyboard (`F`). Enter maximizes/un-maximizes.
- Deleted legacy `LiveGrid.tsx`, `VideoTile.tsx`, and `TileControls.tsx`.
- Wrote full unit test suites for `TilePlayer`, `GridStorage`, and `LivePage`.

---

## 2. Changes Made

### A. WHEP Player Hardening (`services/player.ts`)
- Added `reconnecting` to `PlayerState`.
- Implemented `attemptId` generation and `disposed` guard after every `await` to prevent unmounted component leaks.
- Removed public Google STUN server; `RTCPeerConnection` now uses `iceServers: []`.
- WHEP endpoint constructed using server-issued media token path without case modification: `/${path}/whep?token=${token}`.
- Tracks `Location` response header and dispatches HTTP `DELETE` upon cleanup.
- Added stall watchdog detecting frozen frames (>5s elapsed without `timeupdate`) and triggering reconnect with exponential backoff.
- Added `retryNow()` to cancel backoff delay and initiate an immediate reconnection.

### B. Live Page Components (`features/live/`)
- `LiveToolbar.tsx`: 48 px sticky header featuring dimension toggle group (1x1 to 4x4 in Advanced, 1x1 to 3x3 in Simple), pagination controls (when total cameras > tiles per page), and total camera count caption.
- `TileOverlay.tsx`: solid `bg-video-overlay` chips with `text-video-fg` (no blur) showing camera name (truncated with full title), live/reconnecting/connecting/offline badge, animated `REC` indicator, advanced stream details (`SUB` / `MAIN` • WebRTC • serial), and action buttons (Snapshot, Mute, Maximize).
- `VideoTile.tsx`: root `dark` class container enforcing dark video chrome in both themes, keyboard controls (Enter to maximize, F for fullscreen, Esc to exit), snapshot canvas export, and state overlays (shimmer skeleton on connect, centered `WifiOff` and last-seen on offline, inline error with "Retry stream" button on failure).
- `LivePage.tsx`: responsive CSS grid (`grid-cols-1` to `grid-cols-4`, `gap-2` / `gap-1`), maximized view inside shell, and empty states ("No cameras yet" with primary "Add camera" link for operators/owners; "No cameras assigned" for viewers).
- `routes.tsx`: registered `/` and `/live` with `fullBleed: true`.
- `copy.ts`: centralized copy for all Live strings.

### C. Legacy Cleanup
- Removed legacy components `src/vizenlink_nvr/web/src/legacy/LiveGrid.tsx`, `VideoTile.tsx`, and `TileControls.tsx`.

---

## 3. Verification & Test Results

### Player Unit Tests:
```bash
npm --prefix src/vizenlink_nvr/web test -- src/services/player.test.ts
```
**Output:**
```
Test Files  1 passed (1)
Tests       6 passed (6)
Duration    579ms
```

### Grid Layout Persistence Tests:
```bash
npm --prefix src/vizenlink_nvr/web test -- src/services/grid_storage.test.ts
```
**Output:**
```
Test Files  1 passed (1)
Tests       7 passed (7)
Duration    290ms
```

### Live Page Tests:
```bash
npm --prefix src/vizenlink_nvr/web test -- src/features/live
```
**Output:**
```
Test Files  1 passed (1)
Tests       8 passed (8)
Duration    904ms
```

### Full Web Test Suite:
```bash
npm --prefix src/vizenlink_nvr/web test
```
**Output:**
```
Test Files  18 passed (18)
Tests       201 passed (201)
Duration    2.72s
```

### Design Gates:
```bash
npm --prefix src/vizenlink_nvr/web run gates
```
**Output:**
```
✅ Design gates passed: scanned 101 non-legacy files with 0 violations.
```

### Production Build:
```bash
npm --prefix src/vizenlink_nvr/web run build
```
**Output:**
```
vite v8.3.6 building client environment for production...
dist/index.html                           0.93 kB │ gzip:   0.50 kB
dist/assets/index-Bia3LbGI.css          127.69 kB │ gzip:  20.18 kB
dist/assets/index-BQJHvbj1.js           856.02 kB │ gzip: 253.64 kB
✓ built in 210ms
```

### Legacy File Removal Verification:
```bash
test ! -e src/vizenlink_nvr/web/src/legacy/LiveGrid.tsx
```
**Output:** Clean pass (exit 0).

---

## 4. Owner Follow-Ups (Flagged Findings)
1. **Uppercase Serial Path Mismatch in Backend:**
   - MediaMTX auth webhook expects exact case match against token path (`path` returned in `generate_camera_media_token`).
   - However, the background reconciler registers MediaMTX paths using lower-cased camera serials. If a camera has uppercase letters in its serial, MediaMTX will report a path mismatch on stream access. A future backend reconciliation update should normalize path registrations consistently.
2. **Loopback-Only WebRTC Media:**
   - MediaMTX's WebRTC UDP/TCP listeners currently bind loopback (127.0.0.1). While WHEP signaling is proxied through `/cam` on any LAN origin, ICE media exchange succeeds only when browser and MediaMTX reside on the same host unless MediaMTX's `webrtcAdditionalHosts` is configured with the NVR host's LAN IP address.

---

## 5. Next Plan
Wave order execution sequence:
- Next plan: **Plan 09-12** (`.planning/phases/09-ui-redesign/09-12-PLAN.md`) — Playback page overhaul.

