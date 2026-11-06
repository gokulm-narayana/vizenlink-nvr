# Phase 9 Plan 13 Summary: Restyled Playback Page

Rebuilt the Playback page to the UI-SPEC contract on top of the 09-12 Timeline. Ported segment sequencing and gap skipping from legacy `PlaybackView` into a dedicated hook (`usePlaybackEngine`), restyled the toolbar and transport controls with responsive mobile collapse, migrated clip export to a shadcn dialog, wired frame snapshot capture with inline error recovery and success toast, and removed the legacy playback files.

## What Was Built

1. **Playback Engine Hook (`usePlaybackEngine.ts`)**:
   - `findCoveringOrNextSegment(target, segments)`: Pure function identifying covering segment or next segment start for seamless gap skipping.
   - `toDatetimeLocal` and `parseDatetimeLocal`: Timezone-aware date string conversion helpers.
   - `parseTimeToDate`: Parses `HH:MM:SS` (or `HH:MM`) into exact site-zone instant on the selected day.
   - Ported player commands: `seek`, `play`, `pause`, `togglePlay`, `skip(+-10s)`, `setPlaybackRate(0.5x, 1x, 2x, 4x)`, `toggleMute`, `handleTimeUpdate`, `handleEnded`.

2. **Playback API Client (`api.ts`)**:
   - `useTimeline(serial, day, zone)`: Queries `/api/v1/playback/timeline` with `[start, end]` computed from `zonedDayBounds(day, zone)`.
   - `useRecordedDays(serial, year, month)`: Queries `/api/v1/playback/days`.
   - `useCameraRetention(serial)`: Extracts camera retention days from `useRecordingStatus()`.
   - `useSaveSnapshot()`: Mutation posting `{ camera_serial, image_base64, title, captured_at }` to `/api/v1/playback/snapshot`.
   - `useExportClip()`: Mutation posting `{ camera_serial, start_time, end_time, title }` to `/api/v1/playback/export`.

3. **Playback Copy Dictionary (`copy.ts`)**:
   - UI-SPEC strings for playback states, overlays, snapshot, clip export dialog, and transport.

4. **Playback Toolbar (`PlaybackToolbar.tsx`)**:
   - Camera `Select` showing camera name and online/offline status dot.
   - Date `Popover` + `Calendar` displaying footage-day dots (`4px` dot modifier) and muted non-footage days.
   - "Jump to time" `Input` accepting `HH:MM:SS` in site zone with Jump action.
   - "Events" link routing to `/events?camera={serial}`.

5. **Transport Bar (`TransportBar.tsx`)**:
   - `ButtonGroup` with Skip -10s (`RotateCcw`), Play/Pause (`Play`/`Pause`), Skip +10s (`RotateCw`), speed select (0.5x, 1x, 2x, 4x).
   - Desktop icon actions: Mute (`Volume2`/`VolumeX`), Snapshot (`Camera`), Mark in, Mark out, Fullscreen (`Maximize`), each with `aria-label`, tooltip, and `Kbd` shortcut.
   - Primary `Export clip` button (enabled only when both In and Out marks are set).
   - Caption playhead timestamp in site zone with timezone abbreviation.
   - Mobile responsive dropdown ("More playback controls") below 768px (`md:hidden`).
   - Inline snapshot error `Alert` with "Retry save snapshot" button.

6. **Clip Export Dialog (`ClipExportDialog.tsx`)**:
   - 560px max width dialog (`sm:max-w-[560px]`).
   - Fields: Title, Start time, End time (prefilled in site zone), duration caption, fixed MP4 format.
   - Client-side validation: verifies End time is after Start time before sending.
   - Pending state: indeterminate progress indicator, disabled inputs, prevented backdrop dismissal.
   - Success: closes dialog, clears markers, fires toast "Clip exported" with single action "Open in Gallery" (`/gallery?tab=clips`).
   - Failure: keeps dialog open, shows inline `role="alert"` Alert, changes primary button to "Retry export clip".

7. **Playback Page (`PlaybackPage.tsx`) & Routes (`routes.tsx`)**:
   - Deep-link support: parses `camera` and `t` query params, default camera and "now" fallback.
   - 16:9 black video container (`bg-video-bg`, max height 60 dvh, dark scope) with Loading, Empty Day, Gap Overlay, and error state with "Retry playback".
   - Integrated with 09-12 `Timeline`.
   - Direct route mounted on `/playback` replacing legacy adapter.

8. **Removed Legacy Files**:
   - `src/vizenlink_nvr/web/src/legacy/PlaybackView.tsx`
   - `src/vizenlink_nvr/web/src/legacy/TransportBar.tsx`
   - `src/vizenlink_nvr/web/src/legacy/ClipExportModal.tsx`

## Verification Output

1. **Playback Unit Tests**:
   - `src/features/playback/playback.test.tsx` (15 tests passing)
   - `src/features/playback/export.test.tsx` (4 tests passing)
   - `src/features/playback/timeline/timeline.test.tsx` (7 tests passing)
   - Total playback test suite: 26 passed.

2. **Design Gates**:
   - `node scripts/gates.mjs`: Scanned 165 non-legacy files with 0 violations.

3. **Build**:
   - `tsc && vite build`: Completed with 0 errors.

4. **Full Web Test Suite**:
   - 306 tests passed across 29 test suites.

## Deviations & Known Gaps

- **UTC Footage-Day Dots (Backend Gap)**:
  `GET /api/v1/playback/days` computes recorded calendar days based on UTC timestamps on the server (`services/timeline.py`). Footage-day dots in the date picker follow UTC dates and may be offset by one calendar day near midnight for non-UTC sites. Per D-14 and D-15, backend changes outside the 3 approved items are out of scope; this behavior is preserved and recorded for owner follow-up if a `tz` query parameter is added in a future backend phase.

## Next Plan

Plan 09-18 (Wave 9): Camera Health & Maintenance (`/cameras/:serial/health`, maintenance tab, reboot & factory reset modals, delete `CameraSettingsView.tsx`).
