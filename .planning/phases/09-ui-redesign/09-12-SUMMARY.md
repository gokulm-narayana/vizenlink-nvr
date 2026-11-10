# Plan 09-12 Summary: Timeline Tracer & Accessible Token-Styled DOM Timeline

## What Was Built
- **`src/vizenlink_nvr/web/src/lib/timeline.ts`**:
  - Pure timeline geometry and math functions:
    - `getWindowRange(day, zoom, anchor, zone)`: Full site-zone day (23h or 25h during DST transitions) at 24h, centered around anchor and clamped to the day bounds at 12h, 4h, and 1h.
    - `timeToPct` & `pctToTime`: Sub-second precision round-trip positioning within any window range.
    - `zoomAround(windowRange, cursorTime, nextZoom, day, zone)`: Maintains cursor position under zoom.
    - `retentionSpan(windowRange, retentionDays, now)`: Computes the retention-removed interval.
    - `nextZoom(current, direction)`: Traverses `["24h", "12h", "4h", "1h"]`.
- **`src/vizenlink_nvr/web/src/lib/timeline.test.ts`**:
  - 12 unit tests verifying standard days, 23h spring-forward, 25h fall-back, Asia/Kolkata half-hour zone offsets, round-trip conversion, zoom anchors, and retention intervals.
- **`src/vizenlink_nvr/web/src/features/playback/timeline/HatchPattern.tsx`**:
  - Inline SVG pattern (`outage-hatch`) drawing diagonal lines using `currentColor` and `text-warning`, avoiding CSS gradient syntax per Gate R8.
- **`src/vizenlink_nvr/web/src/features/playback/timeline/copy.ts`**:
  - User-facing labels, tooltip strings, and accessible screen-reader table captions.
- **`src/vizenlink_nvr/web/src/features/playback/timeline/TimelineLegend.tsx`**:
  - Accessible legend displaying swatches for: Recorded (primary), Recording outage (warning hatch), Removed by retention (input bar with dotted underline), Event (info diamond), and Locked (lock icon).
- **`src/vizenlink_nvr/web/src/features/playback/timeline/Timeline.tsx`**:
  - DOM-based, token-styled, accessible timeline component implementing:
    - `role="slider"`, `aria-label="Timeline"`, min/max/now values in milliseconds, and `aria-valuetext` in site timezone.
    - Keyboard controls: ArrowLeft/ArrowRight (+-10s), Shift+Arrow (+-60s), +/- zoom, Space play/pause, M mute, I/O in/out markers.
    - Non-passive wheel zoom around pointer position (`preventDefault` called on zoom).
    - Multi-touch pinch-to-zoom handling (>20% distance change).
    - Dynamic percentage styling with gate compliance (`dynamic-style:` comments).
    - Visually hidden (`sr-only`) table for screen readers listing day's recorded spans.
- **`src/vizenlink_nvr/web/src/features/playback/timeline/timeline.test.tsx`**:
  - 7 component integration tests covering slider ARIA, keyboard navigation, legend items, screen reader table, mouse pointer seek, wheel zoom, and in/out markers.
- **Legacy PlaybackView Update**:
  - Swapped import in `src/vizenlink_nvr/web/src/legacy/PlaybackView.tsx` from `TimelineCanvas` to `@/features/playback/timeline/Timeline`.
  - Deleted legacy `src/vizenlink_nvr/web/src/legacy/TimelineCanvas.tsx` via `git rm`.

## Retention-Span Derivation (for Owner Review)
The timeline API (`GET /api/v1/playback/timeline`) returns recorded segments, outages, and events, but does not provide an explicit "removed by retention" span.
- When `retention_days` is a positive number (configured time-based retention):
  - Any time window prior to `now - (retention_days * 86400 * 1000)` has had recordings pruned by the retention policy.
  - The interval from the start of the visible day window up to `min(now - retentionDays, windowEnd)` is marked as "Removed by retention" unless active segments exist in that range.
  - This is rendered with `bg-input` and a dotted baseline (`border-dotted border-foreground/60`), clearly distinguishing it from recording outages (`text-warning` hatch) and normal empty background.
- When `retention_days` is null (size-based retention or unset):
  - No retention span is rendered; empty intervals render as standard unrecorded background.

## Verification
- `npm --prefix src/vizenlink_nvr/web test -- src/lib/timeline.test.ts src/features/playback/timeline`: PASS (19/19 tests)
- `npm --prefix src/vizenlink_nvr/web run gates`: PASS (108 non-legacy files scanned, 0 violations)
- `npm --prefix src/vizenlink_nvr/web run build`: PASS (TypeScript tsc & Vite bundle completed cleanly)
- `npm --prefix src/vizenlink_nvr/web test`: PASS (220/220 tests passed across 20 test suites)
- `test ! -e src/vizenlink_nvr/web/src/legacy/TimelineCanvas.tsx`: PASS (file deleted)

## Deviations & Notes
- Fixed `timeline.test.tsx` assertion where `getByText` on visually hidden table cells required query matching without selector error.
- Fixed missing `ZOOM_LEVELS` import in `Timeline.tsx`.

