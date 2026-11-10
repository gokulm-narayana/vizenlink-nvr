# Phase 09 Plan 09 Summary: Shell Status Layer & Shared Primitives

**Date:** 2026-11-06  
**Commit:** `b5e94a3`  
**Phase:** 09-ui-redesign  
**Plan:** 09  
**Wave:** 7  

---

## 1. Overview & Objective
Completed the shell's status layer and cross-feature shared primitives:
- Replaced the legacy `AlertsBanner` with `AlertStack` (at most 2 alerts, critical first with `role="alert"`, warnings with `role="status"`, subtle status fills, dismiss action).
- Created `AlertsBell` popover in the top bar listing all active non-dismissed alerts with severity icons and timestamps, count badge, and empty state ("All clear. No active alerts.").
- Built shared `CameraHealthLink` with role-aware target links ("Open camera health" for operators/owners; "View camera health" for viewers when route registered).
- Built `RecorderStatusChip` showing "Recording {n} of {total}" with truth-telling status dot (success / warning / critical) and icon, with tooltip on collapsed rail.
- Added active alert count badge on Dashboard nav item and unread events count badge on Events nav item.
- Built `StatusBadge` supporting 9 status kinds without relying on color alone (`online`, `offline`, `recording`, `not-recording`, `degraded`, `critical`, `disabled`, `user-active`, `user-disabled`).
- Built `InlineError` enforcing verb+noun template literals on `actionLabel` (`Retry ${string}` | `Reload ${string}`) and pending spinner state.
- Implemented `lib/time.ts` with pure `Intl.DateTimeFormat` (DST spring-forward 23h, fall-back 25h, site timezone formatting, relative time formatting).
- Implemented `Shortcuts` (`G` then `L`/`P`/`E`/`G`/`D` navigation chord), "Skip to main content" link targeting `#main`, and 2px `RefetchBar` indicator.

---

## 2. Changes Made

### A. Alerts System & Shared Links
- `src/vizenlink_nvr/web/src/components/CameraHealthLink.tsx`: shared recovery link detecting camera serial from `serial` or `source` string (`camera:*` or `watchdog:*`), routing operators/owners to `/cameras/:serial?tab=health` and viewers to `/cameras/:serial/health`.
- `src/vizenlink_nvr/web/src/components/shell/AlertStack.tsx`: mounts below top bar; renders up to 2 sorted alerts with `role="alert"` or `role="status"` and "Dismiss alert" button.
- `src/vizenlink_nvr/web/src/components/shell/AlertsBell.tsx`: popover component in header with count badge and full scrollable list of active alerts.
- `src/vizenlink_nvr/web/src/legacy/AlertsBanner.tsx`: deleted.

### B. Status, Error & Sidebar Badges
- `src/vizenlink_nvr/web/src/components/StatusBadge.tsx`: icon + text + token color badge for system and user statuses.
- `src/vizenlink_nvr/web/src/components/InlineError.tsx`: `role="alert"` alert with strictly typed action label (`Retry *` | `Reload *`) and pending spinner.
- `src/vizenlink_nvr/web/src/components/shell/RecorderStatusChip.tsx`: sidebar footer chip displaying recorder status, camera counts, and truth-telling dot.
- `src/vizenlink_nvr/web/src/components/shell/AppSidebar.tsx`: mounted `RecorderStatusChip` in `SidebarFooter`, added active alert badge on Dashboard, unread count badge on Events, and documented `Kbd` shortcut tooltips.
- `src/vizenlink_nvr/web/src/lib/queries.ts`: added `useHealth()` and `useUnreadCount()`.

### C. Time, Shortcuts & Accessibility
- `src/vizenlink_nvr/web/src/lib/time.ts`: exported `zonedDayBounds`, `zonedDayStart`, `formatDateTime`, `formatTime`, `zoneAbbreviation`, `formatRelative`, `useSiteTimeZone`.
- `src/vizenlink_nvr/web/src/components/shell/Shortcuts.tsx`: global keyboard listener for `G` chords, ignoring editable targets and modifier keys.
- `src/vizenlink_nvr/web/src/components/shell/RefetchBar.tsx`: 2px progress bar at header bottom edge during background refetches.
- `src/vizenlink_nvr/web/src/components/shell/AppShell.tsx`: mounted skip link, shortcuts, refetch bar, and `AlertStack`.

---

## 3. Verification & Test Results

### Unit & Integration Tests:
```bash
npm --prefix src/vizenlink_nvr/web test
```
**Output:**
```
Test Files  15 passed (15)
Tests       180 passed (180)
Duration    2.49s
```

### TypeScript Validation:
```bash
npm --prefix src/vizenlink_nvr/web run typecheck
```
**Output:** Clean pass (exit 0).

### Design Gates:
```bash
npm --prefix src/vizenlink_nvr/web run gates
```
**Output:**
```
✅ Design gates passed: scanned 93 non-legacy files with 0 violations.
```

### Production Build:
```bash
npm --prefix src/vizenlink_nvr/web run build
```
**Output:**
```
vite v8.3.6 building client environment for production...
dist/index.html                           0.93 kB │ gzip:   0.50 kB
dist/assets/index-AZpEn55A.css          125.59 kB │ gzip:  19.83 kB
dist/assets/index-BJS7ls1l.js           846.74 kB │ gzip: 250.19 kB
✓ built in 222ms
```

### File Deletion Verification:
```bash
test ! -e src/vizenlink_nvr/web/src/legacy/AlertsBanner.tsx
```
**Output:** Clean pass (exit 0).

---

## 4. Next Plan
Next plan in execution sequence: **Plan 09-10** (`.planning/phases/09-ui-redesign/09-10-PLAN.md`).

