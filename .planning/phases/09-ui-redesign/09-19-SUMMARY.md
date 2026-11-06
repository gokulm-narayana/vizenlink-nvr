# Plan 09-19 Summary: Mobile Devices & QR Pairing Overhaul

## What Was Built
- **`src/vizenlink_nvr/web/src/features/devices/QrCode.tsx`**:
  - Scannable QR code generated via `uqr.encode(payload, { ecc: "M", border: 2 })`.
  - Pure SVG rendering without HTML injection (satisfies Gate R7): renders an outer white `<rect fill="white">` background with 16 px quiet zone (border) and individual `<rect fill="black">` modules corresponding exactly to dark cells.
  - No hex colors in TSX (satisfies Gate R2).
  - Supports `dimmed` opacity state when pairing code expires.
- **`src/vizenlink_nvr/web/src/features/devices/copy.ts`**:
  - UI-SPEC strings for Devices page, pairing instructions, copy buttons, LAN HTTP fallback caption, and revoke confirmation dialog.
- **`src/vizenlink_nvr/web/src/features/devices/api.ts`**:
  - `useQrInit`: Mutation for `POST /api/v1/mobile/qr/init` with `gcTime: 0` to prevent short-lived pairing secret retention in client caches (T-09-38).
  - `useDevices`: Query for `GET /api/v1/mobile/devices`.
  - `useRevokeDevice`: Mutation for `POST /api/v1/mobile/devices/{device_id}/revoke` with automatic `["devices"]` cache invalidation.
- **`src/vizenlink_nvr/web/src/features/devices/PairingDialog.tsx`**:
  - 480 px Radix `Dialog` displaying scannable QR code.
  - Monospace pairing code text with icon-only copy button (`aria-label="Copy pairing code"`), Tooltip, and toast "Code copied".
  - Plain-HTTP LAN clipboard fallback caption ("Press Ctrl+C or Cmd+C to copy.").
  - Ticking expiry countdown timer (`Expires in Xm Ys` / `Code expired`), dimming the QR code on expiration.
  - Numbered instructions matching mobile app onboarding flow.
  - "Generate new code" secondary action with loading spinner.
  - Init failure handling with `InlineError` and "Retry generate pairing code" button.
  - Footer button "Close pairing".
- **`src/vizenlink_nvr/web/src/features/devices/DevicesPage.tsx`**:
  - Top header with "Mobile Devices", "Paired mobile clients" subtitle, and primary "Pair mobile device" button.
  - Zero paired devices empty state: renders `Empty` component with `Smartphone` icon and "Pair mobile device" CTA.
  - Desktop `Table` with device name, platform with `Smartphone` icon, paired timestamp in site time zone, and last seen relative time (with absolute time in `title`).
  - Mobile stacked cards below 768 px.
  - Role-gated revoke action with `AlertDialog` confirmation ("Revoke {device name}? It will be signed out and refused until it pairs again.", with actions "Keep device paired" / "Revoke device").
  - Revoke failure handling with `InlineError` and "Retry revoke device" action.
- **`src/vizenlink_nvr/web/src/features/devices/routes.tsx`**:
  - Mounted `DevicesPage` directly on `/devices` with `minRole: "owner"`.
- **Legacy Files Deleted**:
  - `src/vizenlink_nvr/web/src/legacy/PairedDevicesView.tsx`
  - `src/vizenlink_nvr/web/src/legacy/MobilePairingModal.tsx`
- **`src/vizenlink_nvr/web/src/features/devices/devices.test.tsx`**:
  - 8 unit and integration tests covering QR code cell count parity against `uqr.encode`, dimmed styling, pairing dialog QR/timer/clipboard/fallback/error, and devices page list/revoke/empty flows.

## Verification
- `npm --prefix src/vizenlink_nvr/web test -- src/features/devices`: PASS (8/8 tests)
- `npm --prefix src/vizenlink_nvr/web run gates`: PASS (150 non-legacy files scanned, 0 violations)
- `npm --prefix src/vizenlink_nvr/web run build`: PASS (TypeScript tsc & Vite production bundle green)
- `npm --prefix src/vizenlink_nvr/web test`: PASS (279/279 tests across 26 suites)
- `test ! -e src/vizenlink_nvr/web/src/legacy/PairedDevicesView.tsx && test ! -e src/vizenlink_nvr/web/src/legacy/MobilePairingModal.tsx`: PASS (legacy files removed)
