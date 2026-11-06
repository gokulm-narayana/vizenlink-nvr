# Plan 09-18 Summary: Camera Health & Maintenance, Factory Reset, and Legacy Removal

**Execution Wave:** 9
**Depends on:** 09-17
**Status:** Completed
**Requirements Covered:** SET-05, SET-06, SET-07, HLTH-09, AUTH-06

---

## 1. What Was Built

### Read-Only Camera Health
- **`HealthPanel.tsx`**: Reusable component rendering read-only Uptime (via `formatUptime`), Last reboot reason, Clock sync (`StatusBadge` with synced/uncertain), and Firmware version. Includes skeleton loading and `InlineError` with action `Reload camera health`.
- **`tabs/HealthTab.tsx`**: Embeds `HealthPanel` into the `/cameras/:serial` view.
- **`health/routes.tsx` & `health/CameraHealthPage.tsx`**: Registers `/cameras/:serial/health` with title "Camera health" and `minRole: "viewer"`. Renders camera header with `HealthPanel`. Maps API 403 errors to the shared `<Forbidden />` state ("You don't have access to this page." / "Go to Live"). Renders no settings controls or maintenance actions for any role.

### Maintenance & Safe Destructive Actions
- **`MaintenanceTab.tsx`**: Card with two action rows:
  - **Reboot camera**: Secondary action button opening an `AlertDialog` ("Reboot {camera name}? It will go offline for about a minute. Recording resumes automatically."). Action button "Reboot camera", cancel button "Keep camera running". On failure, renders inline `Alert` with `role="alert"` and "Retry reboot camera". On success, toasts "Reboot started for {name}".
  - **Factory reset camera**: Destructive action button opening `FactoryResetDialog`.
- **`FactoryResetDialog.tsx`**: Two-step `AlertDialog` implementing Acceptance 11:
  - **Step 1 (Mode Selection)**: Radio group with "Reset mode" (`CAMERAS_COPY.RESET_MODE_LABEL`). Preselects "Soft reset (keep network)" (`mode: "Soft"`), with optional "Hard reset (erase all)" (`mode: "Hard"`). Displays full descriptions alongside each radio and repeats selected mode's description in dialog body. Buttons: "Keep camera settings" (`variant="outline"`) and "Continue factory reset" (`variant="default"`).
  - **Step 2 (Typed Confirmation)**: Mode-specific prompt naming the camera. Field label "Type RESET to confirm" with helper "Type RESET to enable the button.". Destructive button labelled "Soft reset camera" or "Hard reset camera", disabled until input trimmed & upper-cased equals `RESET`. Ghost button "Back to reset mode" returns to Step 1 keeping previous mode selection. "Keep camera settings" backs out.
  - **Body Payload Assertion**: Sends exactly `{ mode: "Soft" | "Hard", confirmation: "RESET" }` to `POST /api/v1/cameras/{serial}/factory-reset`. Camera name is never sent in the body.
  - **Failure Handling**: Keeps dialog open with input intact and renders `InlineError` ("Couldn't factory reset {name}...") with "Retry factory reset camera".
  - **Success Toast**: Displays "Soft reset started for {name}" or "Hard reset started for {name}".

### Legacy Removal
- Deleted `src/vizenlink_nvr/web/src/features/cameras/tabs/LegacyBridgeTab.tsx`.
- Deleted `src/vizenlink_nvr/web/src/legacy/CameraSettingsView.tsx`.
- Confirmed zero references remain in the entire codebase via repository grep.

---

## 2. Test Execution & Verification

### Automated Verification
1. **Camera Feature Tests:**
   ```bash
   npm --prefix src/vizenlink_nvr/web test -- src/features/cameras
   ```
   **Output:** 4 test files passed, 39 tests passed (12 capabilities, 7 factory-reset, 14 cameras, 6 health).
2. **Design System Gates:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run gates
   ```
   **Output:** `✅ Design gates passed: scanned 172 non-legacy files with 0 violations.`
3. **TypeScript & Production Build:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run build
   ```
   **Output:** `tsc && vite build` built successfully in 240ms with zero errors.
4. **Legacy Deletion Verification:**
   ```bash
   test ! -e src/vizenlink_nvr/web/src/legacy/CameraSettingsView.tsx && test ! -e src/vizenlink_nvr/web/src/features/cameras/tabs/LegacyBridgeTab.tsx
   ```
   **Output:** Exit code 0 (both files deleted).
5. **Full Web Suite:**
   ```bash
   npm --prefix src/vizenlink_nvr/web test
   ```
   **Output:** 31 test files passed, 319 tests passed with zero failures.

---

## 3. Deviations & Observations
- **SET-06 Role Mapping:** SET-06 says "Owner/Admin can factory-reset". The codebase has roles `viewer`, `operator`, and `owner` only (no admin role). The backend endpoint uses `RequireOperator`. The UI gates the maintenance tab to operators and owners (as implemented and verified in UI-SPEC). Recommended owner follow-up: update requirement text or restrict backend endpoint in a future phase if tighter scoping is desired.

---

## 4. Next Steps
- Execute **Plan 09-20 (Wave 9)**: Add Camera Wizard (`/cameras/add`, 3-step stepper, network scan note, encrypted password helper, duplicate serial 409 handling, vault 503 handling).
