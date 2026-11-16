---
quick_id: 261113-peb
mode: quick
date: 2026-11-13
---

# Plan: multiview - reliable tile buttons, one full screen mode, sidebar "Full screen view"

## Problem (owner report)
"In multiview some times a button works, some times not", plus a request for a sidebar button that shows all cameras full screen without headers.

## Causes found (code read, then reproduced in Chromium against simulated cameras)
1. Tiles are `draggable`. A click on a tile button with a slightly moving mouse became a drag: the browser sent `dragstart` then `pointercancel` and never `click`. Reproduced: event trace `pointerdown mousedown dragstart pointercancel dragend`, favourite not toggled.
2. Double-click on the tile enlarges it, and a fast double click on a tile button bubbled up to that handler.
3. Full screen was requested on the grid `<div>` or on one tile. Tooltips, right-click menus and dialogs are Radix portals on `<body>`, which the browser does not draw when a smaller element is the fullscreen element. "Choose cameras" / "Save view" opened invisibly and trapped focus.
4. The tile corner button did three different things (tile fullscreen, enlarge inside grid fullscreen, exit) and the fullscreen toolbar only appeared with the pointer in the top 120 px.
5. Enlarged-camera state lived in both React state and `?camera=`; the right-click "Enlarge in grid" changed only the state, so the two drifted.

## Tasks
1. `web/src/lib/fullscreen.ts` (new): page-level full screen helpers and `useWallFullscreenGuard`.
2. `LivePage.tsx`: URL is the single source of truth (`?camera=` enlarged, `?wall=1` full screen view). Full screen view = page covers header and sidebar (`fixed inset-0`) + browser full screen requested on `<html>`; still works if the browser refuses. Controls show on activity, hide after 3 s. `F` toggles, `Esc` leaves.
3. `VideoTile.tsx`: no per-tile browser fullscreen; drag and double-click ignore presses that start on tile controls.
4. `AppSidebar.tsx` + `AppShell.tsx`: "Full screen view" item under Monitor; shell guard leaves browser full screen when the app navigates away.
5. Tests: update the fullscreen and nav tests, add tests for the new behaviour.

## Verify
- `tsc`, Vitest, design gates, build; backend suite unchanged.
- Chromium run against 5 simulated cameras covering every item above.
