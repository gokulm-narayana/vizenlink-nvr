# Plan 09-14 Summary: Events Page Overhaul

## What Was Built
- **`src/vizenlink_nvr/web/src/features/events/api.ts`**:
  - `useEvents`: Infinite query fetching `/api/v1/events` by page with offset and limit (default 50), filtering by `camera_serial`, `event_type`, `start_time`, `end_time`, `is_locked`.
  - `useLockEvent` & `useUnlockEvent`: Mutations posting to `/api/v1/events/{id}/lock` and `/unlock` invalidating queries on success.
- **`src/vizenlink_nvr/web/src/features/events/copy.ts`**:
  - Centralized user-facing copy matching the UI-SPEC copywriting contract for events, empty states, mutation error alerts, and action labels.
- **`src/vizenlink_nvr/web/src/features/events/EventCard.tsx`**:
  - 16:9 snapshot thumbnail with skeleton loading and `ImageOff` placeholder when missing/errored.
  - Neutral secondary badge with per-type lucide icons (`Footprints` for motion, `Spline` for line crossing, `ShieldAlert` with `text-warning` for tamper, `User` for person, `Car` for vehicle, `Bell` for generic).
  - Body strong camera name, relative time with full site-zone formatted datetime in `title`.
  - 8px primary unread dot with visually hidden "Unread" label when event ID is not in `readEventIds`.
  - Lock icon indicator when `is_locked` is true.
- **`src/vizenlink_nvr/web/src/features/events/EventSheet.tsx`**:
  - 480 px right sheet (full width on small screens) with accessible icon-only close button (`aria-label="Close event details"`).
  - Snapshot display, metadata table, and site-zone timestamps with zone abbreviation.
  - "Lock event" switch with optimistic local update and revert on mutation failure.
  - Inline error (`role="alert"`) displaying exact UI-SPEC mutation failure copy with "Retry lock event" / "Retry unlock event" action button.
  - Advanced view metadata: raw topic and clock-sync state ("Camera clock synced" with Info icon or "Camera clock uncertain - NVR time used" with warning icon). Simple view hides both.
  - Primary "Play footage" action navigating to `/playback?camera={serial}&t={start_time}`.
- **`src/vizenlink_nvr/web/src/features/events/EventFilters.tsx`**:
  - Filter bar in card container with wrapping layout:
    - Camera select ("All cameras" + permitted cameras).
    - Event type select ("All types" + known types).
    - Date range popover + single-month calendar (`mode="range"`).
    - Ghost "Clear filters" button when filters are active.
    - Advanced view: "Unread only" toggle switch filtering read cards client-side.
- **`src/vizenlink_nvr/web/src/features/events/EventsPage.tsx`**:
  - Complete Events page wiring URL search params (`camera`, `type`, `from`, `to`), infinite query pagination with "Load more events" button, skeleton loading, and empty states.
  - Empty states using shadcn `empty` component with 24 px `Bell` icon:
    - Filtered empty: "No events match. Try a wider date range or clear the camera and type filters."
    - Unfiltered empty: "No events yet. Events from your cameras show up here as they happen."
- **`src/vizenlink_nvr/web/src/features/events/routes.tsx`**:
  - Updated to render `EventsPage` directly for `/events`.
- **`src/vizenlink_nvr/web/src/legacy/EventFeed.tsx` & `EventCard.tsx`**:
  - Completely removed via `git rm`.

## Verification Results
- `npm --prefix src/vizenlink_nvr/web test -- src/features/events`: PASS (8/8 tests)
- `npm --prefix src/vizenlink_nvr/web run gates`: PASS (115 non-legacy files scanned, 0 violations)
- `npm --prefix src/vizenlink_nvr/web run build`: PASS (TypeScript tsc & Vite bundle completed cleanly)
- `npm --prefix src/vizenlink_nvr/web test`: PASS (228/228 tests across 21 test suites)
- `test ! -e src/vizenlink_nvr/web/src/legacy/EventFeed.tsx`: PASS (legacy feed deleted)
- `test ! -e src/vizenlink_nvr/web/src/legacy/EventCard.tsx`: PASS (legacy card deleted)

## Deviations & Notes
- Updated `src/app/routes.test.tsx` to click the event card and then click the sheet's "Play footage" button to test jump-to-playback, aligning with the new sheet-based workflow replacing the legacy card's inline jump button.
- Removed duplicate `h1` in `EventsPage.tsx` since AppShell header renders the top-bar route `h1` title.

