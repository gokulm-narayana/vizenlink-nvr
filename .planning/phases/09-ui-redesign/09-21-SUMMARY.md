# Plan 09-21 Summary: Profile Page & Change Password Overhaul

## What Was Built
- **`src/vizenlink_nvr/web/src/features/profile/copy.ts`**:
  - `ROLE_DESCRIPTIONS` for viewer, operator, and owner.
  - UI-SPEC strings for password validation, toast message, error alerts, account, security, and preferences cards.
- **`src/vizenlink_nvr/web/src/features/profile/api.ts`**:
  - `useChangePassword`: Mutation for `POST /api/v1/auth/password` with `gcTime: 0` and no password caching/logging (T-09-45), automatically invalidating `["authStatus"]` and `["authMe"]`.
  - `useMe`: Query for `GET /api/v1/auth/me`.
- **`src/vizenlink_nvr/web/src/features/profile/ChangePasswordDialog.tsx`**:
  - 480 px controlled Radix `Dialog` with Current password, New password (`autoComplete="new-password"`), and Confirm new password inputs using `PasswordField`.
  - Client validation preventing API calls if new password is under 8 characters (`PROFILE_COPY.PASSWORD_TOO_SHORT`) or passwords mismatch (`PROFILE_COPY.PASSWORD_MISMATCH`).
  - 400 error handling mapping "Current password is incorrect" directly to the current password field with automatic focus.
  - General server failure handling displaying `InlineError` with "Retry change password" button without clearing entered fields.
  - Modal dismissal prevention (Escape and backdrop click locked) and inputs disabled while request is pending.
  - Success toast "Password changed. Your other devices were signed out." on 200.
- **`src/vizenlink_nvr/web/src/components/shell/UserMenu.tsx`**:
  - Added "Change password" item (`KeyRound` icon) opening `ChangePasswordDialog`.
- **`src/vizenlink_nvr/web/src/features/profile/ProfilePage.tsx`**:
  - Three single-column cards (max 640 px):
    1. **Account Card** (Visual Anchor): Large initial Avatar, username heading, role badge, role description, and "Cameras you can view" ("All cameras" for owner/operator; list of camera badges or empty state copy for viewer).
    2. **Security Card**: Secondary "Change password" button and session invalidation caption.
    3. **Preferences Card**: Theme `RadioGroup` (Light, Dark, System), View mode `ToggleGroup` (Simple, Advanced), "Saved in this browser only." caption, and secondary outline "Sign out" button in footer.
- **`src/vizenlink_nvr/web/src/features/profile/routes.tsx`**:
  - Mounted `ProfilePage` on `/profile` with `minRole: "viewer"`.
- **`src/vizenlink_nvr/web/src/features/profile/profile.test.tsx`**:
  - 8 unit and integration tests covering password validation, 200 toast, 400 focus, network retry, UserMenu integration, Account card role states, and preferences updates.

## Verification
- `npm --prefix src/vizenlink_nvr/web test -- src/features/profile src/components/shell`: PASS (34/34 tests across 6 suites)
- `npm --prefix src/vizenlink_nvr/web run gates`: PASS (156 non-legacy files scanned, 0 violations)
- `npm --prefix src/vizenlink_nvr/web run build`: PASS (TypeScript tsc & Vite production bundle green)
- `npm --prefix src/vizenlink_nvr/web test`: PASS (287/287 tests across 27 suites)
