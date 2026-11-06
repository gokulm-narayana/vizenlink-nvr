# Plan 09-20 Summary: Add Camera Wizard & Stream Contract Integration

**Execution Wave:** 9
**Depends on:** 09-17, 09-03
**Status:** Completed
**Requirements Covered:** AUTH-03, LIVE-01, CAM-02, CAM-03

---

## 1. What Was Built

### Add Camera Wizard (`/cameras/add`)
- **`schema.ts`**:
  - `addCameraSchema`: Comprehensive Zod validation covering all 3 steps. Serial validates length (1-64), character set (`^[A-Za-z0-9._-]+$`), and prohibits `"add"`. Validates host, port, username, password, stream paths, and sub stream requirements when toggled.
  - `toCreateRequest(values)`: Transforms form values into `CameraCreateRequestPayload`. Sets `name` to serial when blank, `location` to `"Default"` when blank, `group_tag` to `"default"` when blank. Main stream always uses `Profile_1`/`VideoEncoder_1`; sub stream (when enabled) uses `Profile_2`/`VideoEncoder_2` to avoid profile/encoder token reuse (Pitfall 10).
- **`copy.ts`**:
  - Full copywriting contract for Add Camera, including the header note with inline `nvr cameras scan` code element, helpers, step captions, button labels, discard dialog strings, and error messages (including the 503 vault-unavailable copy from UI-SPEC revision 5).
- **`api.ts`**:
  - `useCreateCamera`: TanStack Query mutation with `gcTime: 0` (T-09-41 security rule: passwords are never retained in query cache memory). Invalidates query key `["cameras"]` on success.
- **`Stepper.tsx`**:
  - 3-step ordered list (`ol`) with `aria-current="step"`, active indicator, check mark for completed steps, and `Step {n} of 3` caption.
- **`steps/CameraStep.tsx`**:
  - Step 1 fields: Serial number, IP address or hostname, HTTPS port, Camera username (default `admin`), and Camera password (`PasswordField` with show/hide toggle).
  - Inline error handling on Serial field: when 409 conflict occurs, displays `A camera with serial {serial} already exists. Check the serial number, or open the existing camera.` with an inline link to `/cameras/{serial}`.
- **`steps/DetailsStep.tsx`**:
  - Step 2 fields: Name (optional, defaults to serial), Location (optional), Group (optional).
- **`steps/StreamsStep.tsx`**:
  - Step 3 fields: Main stream (scheme radio group `rtsp`/`rtsps`, port 554, path `/stream1`), sub stream toggle with `Switch` ("Add a sub stream"). When toggled on, reveals sub stream scheme, port, and required path (`/stream2`).
  - Advanced view collapsible ("Stream details"): Codec, width, height, transport, profile token, encoder token.
- **`ReviewList.tsx`**:
  - Read-only review section displaying serial, address, name, location, group, and stream endpoints. Password is masked as dots (`••••••••`).
- **`AddCameraPage.tsx`**:
  - Single `useForm` instance maintaining state across step transitions.
  - Validation auto-focuses first invalid field on Continue.
  - Leave protection: `useBlocker` intercepts navigation if the form is dirty, presenting an `AlertDialog` ("Discard this new camera? The details you entered will be lost."). Discards without prompt if clean.
  - Error mapping: 409 returns to step 1 with focused serial error and link; 503 displays vault-unavailable inline `Alert`; other errors display generic add camera error with "Retry add camera".
- **`routes.tsx`**:
  - Exports `/cameras/add` with title "Add camera" and `minRole: "operator"`.

### Backend Contract Pinning (Pytest)
- **`tests/integration/test_api_cameras_create_streams.py`**:
  - Verifies `POST /api/v1/cameras` with both a main stream (`Profile_1`/`VideoEncoder_1`) and a sub stream (`Profile_2`/`VideoEncoder_2`) returns 201 Created on a runtime vault-backed app.
  - Verifies camera credentials can be opened and decrypted using `load_connection` with `rt.vault`.
  - Verifies duplicate serial submissions return 409 Conflict.
  - Verifies viewer accounts receive 403 Forbidden.

---

## 2. Test Execution & Verification

### Automated Verification
1. **Add Camera Web Tests:**
   ```bash
   npm --prefix src/vizenlink_nvr/web test -- src/features/cameras/add
   ```
   **Output:** 1 test file passed, 9 tests passed.
2. **Design System Gates:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run gates
   ```
   **Output:** `✅ Design gates passed: scanned 183 non-legacy files with 0 violations.`
3. **TypeScript & Production Build:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run build
   ```
   **Output:** `tsc && vite build` passed in 249ms with zero errors.
4. **Pytest Integration Tests:**
   ```bash
   uv run pytest tests/integration/test_api_cameras_create_streams.py tests/integration/test_api_cameras_vault.py -q
   ```
   **Output:** 5 passed in 0.87s.
5. **Full Web Test Suite:**
   ```bash
   npm --prefix src/vizenlink_nvr/web test
   ```
   **Output:** 32 test files passed, 328 tests passed.

---

## 3. Deviations & Planner Decisions
- **Sub Stream Tokens:** As specified in Pitfall 10, sub streams default to `profile_token: "Profile_2"`, `profile_name: "SubStream"`, and `venc_token: "VideoEncoder_2"` so that token collisions with main stream never occur.
- **Field Defaults in Payload:** The UI always explicitly provides `name` (falling back to serial), `location` (`"Default"`), and `group_tag` (`"default"`), ensuring predictable backend insertion matching the API models.

---

## 4. Next Steps
- Execute **Plan 09-22 (Wave 10)**: User Management (`/users`, table with role/status badges, dialogs for Create user, Edit access, Reset password, and Disable user with leave confirmation and role protection).
