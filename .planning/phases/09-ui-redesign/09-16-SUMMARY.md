# Plan 09-16 Summary: Dashboard & Telemetry Overhaul

## What Was Built
- **`src/vizenlink_nvr/web/src/features/dashboard/copy.ts`**:
  - Exact strings from UI-SPEC D-03: card titles, storage metric labels, empty states, outage dialog titles/headers, uptime labels, and error messages.
- **`src/vizenlink_nvr/web/src/features/dashboard/api.ts`**:
  - `useStorageStatus`: Query hook for `GET /api/v1/storage` polling telemetry.
  - `useOutages`: Query hook for `GET /api/v1/health/outages` returning camera outage records.
- **`src/vizenlink_nvr/web/src/features/dashboard/MetricCard.tsx`**:
  - Metric card supporting display-size value anchor (used for "Recorder status") and heading-size values (`text-xl font-semibold tabular-nums`) for numeric metrics, with optional status badge, subtitle, and action buttons.
- **`src/vizenlink_nvr/web/src/features/dashboard/StorageCard.tsx`**:
  - Path display with middle-ellipsis truncation and full tooltip.
  - Clipboard copy button with LAN HTTP fallback (`fallbackCopyTextToClipboard`).
  - Storage telemetry breakdown: Used space (e.g. `1.2 TB / 2.0 TB`), Progress bar with semantic critical/warning/primary thresholds, Estimated retention days, and Reserved margin notice (`10 GB reserve maintained`).
  - Critical/degraded health warning with explicit failure reasons.
- **`src/vizenlink_nvr/web/src/features/dashboard/AlertsCard.tsx`**:
  - Active alerts feed with severity icons (warning triangle / critical octagon).
  - One-click dismissal button (`X`, "Dismiss alert") persisted into `uiStore.dismissedAlertIds`.
  - Deep-link pill button (`CameraHealthLink`) linking camera-related alerts to `/cameras/{serial}`.
  - Empty state when no alerts are active ("No active alerts. System is operating normally.").
- **`src/vizenlink_nvr/web/src/features/dashboard/CamerasTable.tsx`**:
  - Responsive layout: Desktop `Table` and mobile stacked cards.
  - Independent status badges: Connection status (`online` / `offline`) and Recording status (`recording` / `not-recording`).
  - Outage status indicator: Shows ongoing outage or relative last seen timestamp.
  - Direct action button to open camera-specific outage history dialog.
  - Role-gated empty state: Owners/operators see "Add your first camera to start monitoring" with a button linking to `/cameras/add`; viewers see "No cameras have been added yet."
- **`src/vizenlink_nvr/web/src/features/dashboard/OutageHistoryDialog.tsx`**:
  - Accessible Radix `Dialog` displaying camera outage history globally or filtered to a single camera.
  - Columns: Camera, Started, Ended (or "Ongoing"), Duration (formatted e.g. `30m 0s`), and Reason.
  - Accessible icon close button (`aria-label="Close outage history"`) and footer outline button.
  - Empty state: "No outage events recorded."
- **`src/vizenlink_nvr/web/src/features/dashboard/DashboardPage.tsx`**:
  - Top header with "System Health & Diagnostics", "Operational telemetry" subtitle, and "Camera outage history" button.
  - Row 1: 5 metric cards (Recorder status with Display anchor, Cameras online, Recording now, Storage used, Active alerts).
  - Row 2: 2-column layout with `StorageCard` (left) and `AlertsCard` (right).
  - Row 3: `CamerasTable`.
  - Advanced diagnostic view: Revealed in `advanced` viewMode showing subsystem health badges (MediaMTX, Database, Storage), Recorder uptime (`Xd Xh` / `Xh Xm`), and collapsible raw health details JSON key-value inspector.
- **`src/vizenlink_nvr/web/src/features/dashboard/routes.tsx`**:
  - Updated to render `DashboardPage` directly on `/dashboard` and `/`.
- **Legacy Files Removed**:
  - `src/vizenlink_nvr/web/src/legacy/Dashboard.tsx`
  - `src/vizenlink_nvr/web/src/legacy/OutageHistoryModal.tsx`

## Verification
- `npm --prefix src/vizenlink_nvr/web test -- src/features/dashboard`: PASS (9/9 tests)
- `npm --prefix src/vizenlink_nvr/web run gates`: PASS (131 non-legacy files scanned, 0 violations)
- `npm --prefix src/vizenlink_nvr/web run build`: PASS (TypeScript tsc & Vite production bundle green)
- `npm --prefix src/vizenlink_nvr/web test`: PASS (245/245 tests across 23 test suites)
- `test ! -e src/vizenlink_nvr/web/src/legacy/Dashboard.tsx && test ! -e src/vizenlink_nvr/web/src/legacy/OutageHistoryModal.tsx`: PASS (legacy files removed)
