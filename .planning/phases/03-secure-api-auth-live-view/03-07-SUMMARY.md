# Plan 03-07: React SPA, Live Multiview Grid, WHEP/HLS Player Summary

**Execution Date:** 2026-11-04  
**Status:** Completed  
**Requirements:** LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06

---

## 1. Summary of Delivered Capabilities

1. **Live Multiview Domain & State Machine (`src/vizenlink_nvr/services/live_view.py`):**
   - Implemented `TileStateMachine` enforcing truthful operational states (`connecting`, `live`, `stalled`, `offline`, `error`).
   - Implemented stall watchdog: if frame progress halts for > 5 seconds, state transitions immediately from `live` to `stalled` (Prohibition: never present a frozen frame as live).
   - Implemented `GridLayoutCalculator` handling 1×1 (1), 2×2 (4), 3×3 (9), and 4×4 (16) grid geometries and pagination slicing.
   - Implemented `TileControlsModel` handling mute toggle, snapshot validation, and dynamic stream auto-switch (`sub` in grid view, `main` when enlarged/maximized).
   - Implemented `GridLayoutConfig` providing JSON serialization and schema sanitization for layout persistence.

2. **React + TypeScript Frontend SPA (`src/vizenlink_nvr/web/`):**
   - `App.tsx`: checks `/api/v1/auth/status`, conditionally rendering `SetupWizard` (if uninitialized), `Login` (if unauthenticated), or the main authenticated navigation and `LiveGrid`.
   - `SetupWizard.tsx`: first-run onboarding wizard creating the owner account, setting timezone and storage paths.
   - `Login.tsx`: session sign-in form with brute-force lockout handling and error alerts.
   - `LiveGrid.tsx`: interactive multiview grid with 1×1 to 4×4 layouts, page navigation, empty slot rendering, and maximized single-camera view.
   - `VideoTile.tsx` & `TileControls.tsx`: WebRTC video element, camera name overlay, status/recording badges, snapshot button (downloads canvas JPEG), mute toggle, and maximize button.
   - `services/player.ts`: WebRTC WHEP client with stall detection and dynamic stream switcher (`sub` <-> `main`).
   - `services/grid_storage.ts`: browser `localStorage` layout persistence.

3. **FastAPI Static File Serving (`src/vizenlink_nvr/api/app.py`):**
   - Configured static file mounting on `/` when frontend build artifacts are present.

4. **Automated Verification:**
   - `tests/unit/test_tile_state_machine.py`: 5 passed.
   - `tests/unit/test_layout_persistence.py`: 3 passed.
   - `tests/integration/test_sub_stream_auto_switch.py`: 1 passed.
   - `tests/unit/test_live_grid_layout.py`: 3 passed.
   - `tests/unit/test_tile_controls.py`: 3 passed.

