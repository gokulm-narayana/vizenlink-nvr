---
quick_id: 261112-9kw
status: complete
date: 2026-11-12
commit: none (working tree only; see "Not committed")
---

# Summary: UI audit fixes (2026-11-12)

## Changed
- `web/src/components/shell/AlertStack.tsx`: one-line strip (title, message from md up, health link, icon dismiss). Not rendered on `/` and `/dashboard`.
- `web/src/features/dashboard/DashboardPage.tsx`: system alert rows gained the camera health link and a dismiss button (the banner is hidden there); row dot colour follows `row.state`; "Storage ready"; cameras panel `xl:self-start`.
- `web/src/components/PageIntro.tsx` + 8 callers: props are now `description` and `actions` only. The shell header already shows the page title. `ObjectSearchPreview` keeps its own `h2` because it shares the `/search` route.
- `web/src/features/events/EventCard.tsx`: compact header line when there is no snapshot (or it fails to load); 16:9 image only when a snapshot exists.
- `web/src/features/search/SearchPage.tsx` + `globals.css`: layout defaults to list when no result has a thumbnail (user choice still wins); list rows are one line tall.
- `web/src/features/playback/PlaybackToolbar.tsx`: date button formats the calendar day in UTC with no clock time (was showing 17:30:00 in Asia/Kolkata); phone toolbar uses `max-sm:contents`, labels hidden below `sm`, "Back to Live View" (was "Back to Multiview") hidden below `sm`.
- `web/src/features/cameras/CamerasPage.tsx`: removed simulator wording.
- `web/src/features/users/UsersPage.tsx`, `devices/DevicesPage.tsx`, `profile/ProfilePage.tsx`: removed inner padding; Profile is a two-column grid from `xl`.
- `web/src/features/settings/RecordingPage.tsx` + `globals.css`: `.vms-select-narrow` (a Tailwind `max-w-*` utility loses to the unlayered `.vms-select { max-width: 100% }`).
- `services/alert_service.py`: message is now "Offline for 5 hours (since 01:57)." in the site time zone, with the date added when the outage started on another day. New `tests/unit/test_alert_duration.py`.

## Audit items that were not product bugs
- Camera health HTTP 500: caused by the audit's seeded cameras having no credential row. Real cameras always have one. No change.
- "Video service: Running" with nothing recording: `/health` reports `True` only when the app is started without the recorder (test server). `nvr run` reports the real state. No change.

## Measured (same seeded data)
- Alerts page height: 5,896px to 2,661px desktop; 15,672px to 7,200px phone.
- Search page height: 3,351px to about 2,430px desktop; 8,514px to 3,045px phone.
- Banner height: about 100px to 40px desktop; about 170px to 40px phone.

## Verification
- Vitest 419/419, `tsc --noEmit` clean, design gates 0 violations.
- pytest (not mediamtx, not hardware) 558 passed, 1 skipped; ruff clean on changed Python.
- Screenshots re-taken at 1440px and 390px; no horizontal overflow.

## Not committed
The working tree already held the owner's large uncommitted change set in the same files, so a commit here would have mixed the two. Left for the owner to commit.

## Not done (recommended next)
Settings sub-menu and system settings, per-account preferences, audit log page, footage lock from Playback, naming clean-up ("Events" vs "Alerts"), native form controls in about 17 files.

## Follow-up, same day: Settings polish, fullscreen fix, digital zoom

Owner asked to improve the look of the Settings pages another tool had built, and reported a broken Live View fullscreen.

- `features/settings/SettingsSection.tsx` (new): one titled card used by System, Recording table, Storage folder, Recording index and Audit log.
- `SettingsPage.tsx`: grouped menu with icons (Recorder / Access / You); one scrolling row on phones. `/profile` now renders inside this layout.
- `SystemSettings.tsx`: Recorder card with helper text, live "time there now" preview, discard/save footer; About as a definition list.
- `AuditLog.tsx`: plain-language action names (code kept as tooltip), area chip, failures and destructive actions in red, "Showing a-b of n".
- `StoragePage.tsx`, `StorageLocation.tsx`: folder card always visible; rescan explained, results as four tiles.
- `RecordingPage.tsx`: mode badges, selected-row highlight, selection count.
- `ProfilePage.tsx`: "Sign out other sessions" moved into Security; duplicate page heading removed.
- `hooks/use-fullscreen-controls.ts`: **bug** - the effect returned early when the element was not mounted on first render (Live View renders a loading state first) and never re-ran, so `isFullscreen` stayed false: toolbar stayed in the page flow on a light background with a black gap. Fullscreen state now comes from a document listener.
- `LivePage.tsx`: fullscreen toolbar uses the dark palette and floats over the video.
- `features/live/useDigitalZoom.ts` (new) + `VideoTile.tsx`: digital zoom on single-camera and fullscreen views (wheel at pointer, drag to pan, 1x-8x, buttons, double-click resets). Pulled forward from Phase 13 (LIVE-X1) at the owner's request. `zoom.test.ts` covers the maths.

Verified: Vitest 426/426, tsc clean, gates 0 violations; Playwright confirmed fullscreen state, 3 s auto-hide and wheel zoom transform. Not verified with a real video stream (seeded cameras are offline).
