# Phase 09 Plan 08 Summary: Migrate Legacy Pages to Shell & Cut-Over

**Date:** 2026-11-06  
**Commit:** `9abbca8`  
**Phase:** 09-ui-redesign  
**Plan:** 08  
**Wave:** 6  

---

## 1. Overview & Objective
Executed the second half of the shell migration (approved split):
- Decoupled legacy views by migrating cross-page shared types (`CameraInfo`, `CameraOption`, `ViewMode`) into `src/vizenlink_nvr/web/src/lib/types.ts`.
- Implemented per-feature route adapters across `features/playback/routes.tsx`, `features/events/routes.tsx`, `features/gallery/routes.tsx`, `features/dashboard/routes.tsx`, `features/cameras/routes.tsx`, and `features/devices/routes.tsx`.
- Integrated operational health alerts under the shell's top bar via `useAlerts()` feeding `AlertsBanner`, filtered by `dismissedAlertIds` in `UiState`.
- Executed the cut-over: `/` and `/live` render the shell's Live page, unknown paths redirect to `/`, and deleted legacy `LegacyApp.tsx` and `Header.tsx`.
- Verified precondition: preserved the owner's uncommitted `Header.tsx` diff in `.planning/phases/09-ui-redesign/owner-Header.tsx.patch` (1928 bytes).

---

## 2. Changes Made

### A. Shared Types Decoupling
- `src/vizenlink_nvr/web/src/lib/types.ts`: Created providing `CameraInfo`, `CameraOption`, and `ViewMode`.
- `LiveGrid.tsx`, `PlaybackView.tsx`: Updated to re-export `CameraInfo` and `CameraOption` from `@/lib/types`.
- `Dashboard.tsx`, `CameraSettingsView.tsx`, `GalleryView.tsx`: Updated type imports to `@/lib/types`.

### B. Feature Route Adapters
- `src/vizenlink_nvr/web/src/features/playback/routes.tsx`: `/playback` (title "Playback", viewer, fullBleed), wires `initialCameraSerial` and `initialTimestamp` from query params `camera` and `t`, wires `onOpenGallery` to navigate to `/gallery?tab=clips`.
- `src/vizenlink_nvr/web/src/features/events/routes.tsx`: `/events` (title "Events", viewer), wires `readEventIds` and `markEventRead` from `uiStore`, wires `onJumpToPlayback` to `/playback?camera=<camera>&t=<timestamp>`.
- `src/vizenlink_nvr/web/src/features/gallery/routes.tsx`: `/gallery` (title "Gallery", viewer), wires `userRole` and `onJumpToPlayback`.
- `src/vizenlink_nvr/web/src/features/dashboard/routes.tsx`: `/dashboard` (title "Dashboard", viewer), wires `viewMode` from `uiStore` and active `recordingCount`.
- `src/vizenlink_nvr/web/src/features/cameras/routes.tsx`: `/cameras` and `/cameras/:serial` (title "Cameras", operator).
- `src/vizenlink_nvr/web/src/features/devices/routes.tsx`: `/devices` (title "Mobile devices", owner).
- `src/vizenlink_nvr/web/src/features/live/routes.tsx`: routes for both `/` and `/live` (title "Live", viewer, fullBleed).

### C. Alerts in AppShell & Data Queries
- `src/vizenlink_nvr/web/src/lib/queries.ts`: added `useAlerts()` query targeting `/api/v1/health/alerts` with 10s poll interval.
- `src/vizenlink_nvr/web/src/components/shell/AppShell.tsx`: mounted `AlertsBanner` directly below `<header>`, fed by `useAlerts()` filtered against `dismissedAlertIds`.

### D. Shell Cut-Over & Legacy Deletions
- `src/vizenlink_nvr/web/src/components/shell/AppSidebar.tsx`: pointed Live nav item at `/` (and dynamic match on `/live`).
- `src/vizenlink_nvr/web/src/app/router.tsx`: removed `LegacyApp` routes; mapped `/` as index route; configured `path: "*"` to `<Navigate to="/" replace />`.
- `src/vizenlink_nvr/web/src/legacy/LegacyApp.tsx`: deleted.
- `src/vizenlink_nvr/web/src/legacy/Header.tsx`: deleted (owner diff preserved in patch).

---

## 3. Verification & Test Results

### Precondition Check:
- Checked `.planning/phases/09-ui-redesign/owner-Header.tsx.patch`: file exists (1928 bytes) containing the owner's uncommitted diff. Precondition passed.

### Test Execution:
```bash
npm --prefix src/vizenlink_nvr/web test
```
**Output:**
```
Test Files  11 passed (11)
Tests       158 passed (158)
Duration    2.22s
```

### Design Gates:
```bash
npm --prefix src/vizenlink_nvr/web run gates
```
**Output:**
```
✅ Design gates passed: scanned 80 non-legacy files with 0 violations.
```

### Production Build:
```bash
npm --prefix src/vizenlink_nvr/web run build
```
**Output:**
```
vite v8.3.6 building client environment for production...
dist/index.html                           0.93 kB │ gzip:   0.50 kB
dist/assets/index-BbYOu92N.css          120.02 kB │ gzip:  19.05 kB
dist/assets/index-NFwyuRGF.js           816.16 kB │ gzip: 243.01 kB
✓ built in 239ms
```

### Reference Cleanliness:
```bash
! grep -rn "LegacyApp\|legacy/Header" src/vizenlink_nvr/web/src
```
**Output:** 0 occurrences found.

---

## 4. Next Plan
Next plan in execution sequence: **Plan 09-09** (`.planning/phases/09-ui-redesign/09-09-PLAN.md`).

