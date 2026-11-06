# Plan 09-22 Summary: Owner User Management & Access Scoping

**Execution Wave:** 9
**Depends on:** 09-21
**Status:** Completed
**Requirements Covered:** AUTH-04, AUTH-05, AUTH-03

---

## 1. What Was Built

### User Management Feature (`/users`)
- **`src/vizenlink_nvr/web/src/features/users/copy.ts`**:
  - Full copywriting contract for Users management, including column headers, role descriptions, status badges, camera cell counts, actions menu, self-protection tooltips, discard dialogs, create user validation errors, stale cameras error, enable/disable prompts, and toast strings.
- **`src/vizenlink_nvr/web/src/features/users/api.ts`**:
  - `useUsers()`: Queries `GET /api/v1/users` with `refetchOnWindowFocus: true`.
  - `useCreateUser()`: TanStack Query mutation with `gcTime: 0` (T-09-49 security requirement: secret credentials never retained in query cache memory). Invalidates query key `["users"]`.
  - `useUpdateUser(userId?)`: TanStack Query mutation supporting both bound `userId` and payload `id`, sending `PATCH /api/v1/users/{id}`. Invalidates query key `["users"]`.
  - `useResetUserPassword(userId)`: TanStack Query mutation with `gcTime: 0` (T-09-49) sending `POST /api/v1/users/{id}/reset-password`. Invalidates query key `["users"]`.
- **`src/vizenlink_nvr/web/src/features/users/CameraChecklist.tsx`**:
  - Checkbox whitelist for Viewer role in a `ScrollArea` (h-44).
  - Ghost buttons: "Select all cameras" and "Clear all cameras".
  - Displays camera name and serial font-mono.
  - Helper caption: "Viewers see only the cameras you tick. With none ticked they see nothing."
- **`src/vizenlink_nvr/web/src/features/users/CreateUserDialog.tsx`**:
  - 480 px dialog for creating new user accounts.
  - Fields: Username, Password (`PasswordField`, `new-password`, min 8 characters), Confirm password.
  - Role selection radio group with descriptions from `ROLE_DESCRIPTIONS` (Viewer, Operator, Owner).
  - Conditionally renders `CameraChecklist` only when Viewer role is selected.
  - Leave protection: Discard new user button opens `AlertDialog` only when input is entered; closes directly if pristine.
  - Error mapping: 409 duplicate username maps to inline error on Username field ("A user named {username} already exists. Choose a different username."). Generic error maps to `InlineError` with "Retry create user".
  - Toasts "User created" and refetches users list.
- **`src/vizenlink_nvr/web/src/features/users/EditAccessDialog.tsx`**:
  - 480 px dialog for editing user role and camera permissions.
  - Role selection radio group: disabled with tooltip "You can't change your own role." when editing current owner's own row.
  - Conditionally renders `CameraChecklist` for Viewer role.
  - Scoping contract: sends `{ role }` for operator and owner; sends `{ role, permissions }` only when role is viewer.
  - Error mapping: 400 Unknown camera serials maps to `InlineError` with "Reload cameras" action; other failures map to "Retry save user access".
  - Toasts "Access saved for {username}".
- **`src/vizenlink_nvr/web/src/features/users/ResetPasswordDialog.tsx`**:
  - 480 px dialog for resetting another user's password.
  - Fields: New password and Confirm password (`PasswordField`, min 8 characters).
  - Helper: "At least 8 characters. {username} is signed out everywhere and must use the new password."
  - Primary button: "Reset password" (`variant="destructive"`).
  - Back-out: "Keep current password" (`variant="outline"`).
  - Toasts "Password reset for {username}".
- **`src/vizenlink_nvr/web/src/features/users/UsersTable.tsx`**:
  - Desktop view (>= 768px): Table rendering Username (with secondary "You" badge on own row), Role secondary badge, StatusBadge (`user-active` or `user-disabled`), Cameras cell ("All cameras", "{n} cameras", or "No cameras" with warning icon), Created date in site time zone, and icon-only row actions trigger (`EllipsisVertical`).
  - Mobile view (< 768px): Stacked cards rendering all attributes and actions.
  - Actions menu:
    - Edit access
    - Enable user (immediate PATCH `{ is_active: true }`) / Disable user
    - On owner's own row: Disable user is disabled with tooltip "You can't disable your own account."
    - On owner's own row: Reset password is replaced with "Change your password", opening `ChangePasswordDialog` from `features/profile`.
- **`src/vizenlink_nvr/web/src/features/users/UsersPage.tsx`**:
  - Top header with `h1` "Users" and primary button "Create user".
  - Page-level `InlineError` for enable/disable failures ("Retry enable user" / "Retry disable user").
  - Table skeleton loading state.
  - Load error state with "Reload users".
  - Defensive empty state with "No users found" / "Create a user to give someone access to this NVR." and "Create user" button.
  - Role protection: returns `<Forbidden />` when current user is not owner.
  - Disable user `AlertDialog` ("Disable {username}? They are signed out everywhere and can't sign in until you enable the account again.") with "Disable user" (destructive outline) and "Keep user enabled".
- **`src/vizenlink_nvr/web/src/features/users/routes.tsx`**:
  - Registers route `/users` with title "Users", `minRole: "owner"`, and element `<UsersPage />`. Enables the Users navigation item in `AppSidebar`.
- **`src/vizenlink_nvr/web/src/features/users/users.test.tsx` & `users-api.test.tsx`**:
  - 23 tests covering table rendering, create user, validation, 409 duplicate username, discard protection, edit access scoping, 400 stale cameras error, enable/disable flows, reset password, self-protection rules, loading/error/empty/403 states, API endpoints, and `gcTime: 0` password hygiene.

---

## 2. Test Execution & Verification

### Automated Verification
1. **Users Feature Tests:**
   ```bash
   npm --prefix src/vizenlink_nvr/web test -- src/features/users
   ```
   **Output:** 2 test files passed, 23 tests passed.
2. **Design System Gates:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run gates
   ```
   **Output:** Scanned 194 files with 0 violations.
3. **TypeScript & Production Build:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run build
   ```
   **Output:** Vite build succeeded with 0 errors.
4. **Full Web Test Suite:**
   ```bash
   npm --prefix src/vizenlink_nvr/web test
   ```
   **Output:** 34 test files passed, 351 tests passed.

---

## 3. Deviations & Discoveries
- Radix UI's `RadioGroupItem` component requires a parent `RadioGroup` provider context even when disabled. When rendering the disabled role options on the owner's own row, wrapped the items in `<RadioGroup value={role} disabled={true}>` inside the `<Tooltip>`.

---

## 4. Next Plan
- **09-23-PLAN.md**: Final phase verification, end-to-end checks, bundle analysis, and handoff documentation.
