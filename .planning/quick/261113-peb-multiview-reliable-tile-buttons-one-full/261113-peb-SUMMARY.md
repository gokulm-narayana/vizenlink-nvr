---
quick_id: 261113-peb
status: complete
date: 2026-11-13
commit: none (working tree only; see "Not committed")
---

# Summary: multiview - reliable tile buttons, one full screen mode, sidebar "Full screen view"

## Changed
- `web/src/lib/fullscreen.ts` (new): `enterPageFullscreen`, `exitPageFullscreen`, `fullscreenElement`, `WALL_PATH`, `useWallFullscreenGuard`.
- `web/src/features/live/VideoTile.tsx`
  - A press that starts on a tile button, link or badge can no longer start a drag (the press location is remembered on `pointerdown`, because `dragstart` reports the tile as its target) and no longer counts as a double-click on the picture.
  - Per-tile browser fullscreen, the in-tile layout switcher and the tile `F` handler are gone; the page owns full screen. Props `solo`, `currentDimension`, `onSelectLayout` replaced by `onFullscreen`, `fullscreenActive`.
- `web/src/features/live/LivePage.tsx`
  - `?camera=<serial>` (enlarged camera) and `?wall=1` (full screen view) in the URL are the only state. Buttons, right-click menu, keyboard and the sidebar all edit the URL.
  - Full screen view covers header and sidebar and asks the browser for full screen on the whole page, so menus, tooltips and dialogs stay visible. If the browser refuses, the view still fills the window.
  - Controls (toolbar and tile buttons) appear on any mouse, touch or key activity and hide after 3 s; they stay while the pointer rests on the toolbar. Replaces the "pointer within 120 px of the top" rule.
  - `F` toggles full screen view, `Esc` leaves it. Toolbar button reads "Exit full screen" while active.
  - Camera corner button: from the grid it fills the screen with that camera and a second press undoes exactly that; inside full screen view it enlarges the camera and a second press returns to the full screen grid.
- `web/src/components/shell/AppSidebar.tsx`: new "Full screen view" item under Monitor (all roles). It requests full screen inside the click, which browsers require.
- `web/src/components/shell/AppShell.tsx`: `useWallFullscreenGuard()` leaves browser full screen when the app is no longer on `/live?wall=1` (for example a tile's Playback link).
- Tests: `live.test.tsx` (fullscreen tests rewritten, 4 new), `routes.test.tsx` (nav list).

## Verified
- Typecheck clean; Vitest 437 passed; design gates 0 violations; build OK; backend 572 passed, 1 skipped.
- Chromium, 5 simulated cameras, 20 checks all pass: moving-mouse click on a tile button, double-click on a button, sidebar item, real browser full screen, header/sidebar covered, dialog and right-click menu visible in full screen, Esc on a menu closes only the menu, corner button in and out, idle hide and return, exit button, `F` key, leaving to Playback exits browser full screen.

## Not verified
- Real cameras with real WebRTC video (simulated cameras show snapshots).
- Safari, iPhone/iPad and touch screens. iPhone Safari does not allow page full screen; the view should still fill the window there, untested.
- `e2e/` Playwright specs were not run.

## Follow-up the same day (owner: "mainly that header is the issue")
- In full screen view the toolbar no longer appears on every mouse move, because it covered the top row's channel labels and LIVE badges. It now opens only when the pointer reaches the top edge (or the small handle at the top centre is pressed, which is also the way in on touch screens), and closes 0.4 s after the pointer leaves it. Camera buttons still appear on any activity. `F` and `Esc` work without the toolbar.
- Browser run repeated with this behaviour: 23 of 24 checks pass. The one failure is the script's own check (the labels are `pointer-events-none`, so `elementFromPoint` cannot see them); the screenshot shows the labels uncovered.

## Known trade-offs
- While the toolbar is open in full screen view it still overlaps the top row's labels; that is now only when the user has asked for it.
- `hooks/use-fullscreen-controls.ts` is no longer used by Live View (its own test still passes). Left in place; remove if nothing else adopts it.

## Not committed
Same reason as 261113-kag: touched files carry the owner's uncommitted work. No subagents or worktree used.

## Follow-up 2 (owner asked for an exit button)
- Full screen view has an "Exit full screen" button in the top-right corner that appears on any mouse movement (same show/hide as the camera buttons). The toolbar's own exit button was removed in full screen (one button, one name) and the toolbar stops short of that corner.
- The top-right camera moves its LIVE/REC badges inwards (`cornerInset`) so the button does not cover them.
- Checked in Chromium: button visible on mouse move without going to the top edge, one click leaves full screen view and browser full screen. Vitest 437 passed, gates clean.

## Follow-up 3 (owner: full screen button must show all cameras)
- The sidebar "Full screen view" now opens `/live?wall=1&fit=all`: filters and saved views are ignored and the grid is the smallest that holds every camera (1×1, 2×2, 3×3 or 4×4). More than 16 cameras are paged at 4×4. The saved grid is not overwritten; leaving full screen returns to it. Picking a grid in the toolbar ends "fit all".
- The Live View toolbar button and `F` still go full screen with the grid already on screen.
- Checked in Chromium with 7 simulated cameras and a saved 2×2: all 7 shown in full screen, 4 again after exit. Vitest 438 passed, gates clean.
