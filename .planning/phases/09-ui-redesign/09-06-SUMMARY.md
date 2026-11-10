# Phase 09 Plan 06 Summary: Router, Auth Routing Table, Safe Redirects, Restyled Login and Setup (AUTH-01, AUTH-02)

## 1. What Was Built
- **API and Query Infrastructure (`src/lib/api.ts`, `src/lib/queries.ts`):**
  - Implemented typed `apiFetch<T>` with auto JSON serialization for plain object bodies, credentials set to `same-origin`, and `ApiError` throwing status and error detail.
  - Implemented `setUnauthorizedHandler(fn)` hook triggering only on 401 status for non-auth endpoints (`/auth/(status|login|setup|logout)` excluded).
  - Created TanStack Query client factory `createQueryClient()` (retry: 1, refetchOnWindowFocus: true) and exported singleton `queryClient`.
  - Implemented `useAuthStatus()` (query key `["authStatus"]`, staleTime: 0) and `useCurrentUser()` deriving `{ id, username, role, permissions }`.
- **Open-Redirect Safe Next Validator (`src/lib/safe-next.ts`):**
  - Strictly validates next query paths: accepts paths starting with single `/` without `//`, rejects any backslash, rejects `/login`, `/setup`, `/api` prefixes, and rejects empty/undefined values.
  - Unit tested comprehensively in `src/lib/safe-next.test.ts`.
- **Password Field Component (`src/components/PasswordField.tsx`):**
  - Implemented with shadcn `InputGroup`, `InputGroupInput`, `InputGroupAddon`, `InputGroupButton`.
  - Accessible toggle button with `Eye` and `EyeOff` icons (16px), switching between `password` and `text` types with `aria-label` ("Show password" / "Hide password") and `aria-pressed`.
  - Forwards `ref` and accepts `autoComplete` for react-hook-form integration.
- **Copywriting Constants (`src/features/auth/copy.ts`):**
  - Centralized all auth and first-run copy from the `09-UI-SPEC.md` Copywriting Contract.
- **Auth Gate & Router (`src/features/auth/AuthGate.tsx`, `src/app/router.tsx`, `src/main.tsx`):**
  - Built React Router 8 router in library mode (`createBrowserRouter(createAppRoutes())`).
  - AuthGate implements the full 12-row auth state table:
    - Row 1: Full-page skeleton while status is pending (`data-testid="auth-loading-skeleton"`).
    - Row 2: NVR-unreachable error with "Retry connection" button on network failure/5xx.
    - Row 3: `initialized=false` replaces to `/setup`.
    - Rows 4 to 6: `initialized=true, authenticated=false` stays at `/login`, replaces `/setup` to `/login`, and redirects other paths to `/login?next=...`.
    - Row 10: `authenticated=true` replaces `/login` and `/setup` to `/`.
    - Row 11: 401 on protected requests clears cache and routes to `/login?next=...` with `sessionEnded: true`.
    - Signed-in users access the app at `/` and other routes.
- **Restyled Login Page (`src/features/auth/LoginPage.tsx`):**
  - Centered layout with `BrandLogo variant="full"`, card max-w-sm, `h1` "Sign in", username and password fields using react-hook-form + zod.
  - Error mapping for 401 ("Incorrect username or password..."), 429 ("Too many failed attempts..."), and generic server errors.
  - Handles router state alerts: informational `sessionEnded` status alert and destructive `signOutFailed` alert with "Retry sign-out request".
  - Redirects to `safeNext(next) ?? "/"` upon successful sign-in.
- **Restyled Setup Page (`src/features/auth/SetupPage.tsx`):**
  - Centered layout with `BrandLogo variant="full"`, card max-w-lg, `h1` "Set up VizenLink NVR".
  - All six form fields in order: Owner username, Password (with helper "At least 8 characters."), Confirm password, Site time zone (`NativeSelect` populated from `Intl.supportedValuesOf("timeZone")` and defaulted to browser zone), Recording storage directory (`/var/lib/vizenlink-nvr/recordings`), and system-disk checkbox ("Allow recordings on the system disk (testing only)").
  - Client validation for password matching and minimum length 8.
  - Submits the exact 5-property payload (`owner_username`, `owner_password`, `timezone`, `storage_path`, `allow_system_disk`).
  - On 400 failure: shows setup failure alert with server detail and "Retry create owner account", while preserving all entered values.
  - On success: invalidates auth status and lands directly on `/` signed in with no second sign-in.
- **Legacy Cleanup:**
  - `LegacyApp.tsx` updated to use `useCurrentUser()` and `useSignOut()`.
  - Deleted legacy `src/legacy/Login.tsx` and `src/legacy/SetupWizard.tsx`.

## 2. Verification Commands & Outputs
```bash
npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build
```
- **Vitest:** 8 test files, 137 passed (100% pass)
  - `safe-next.test.ts`: 6 passed
  - `auth-gate.test.tsx`: 11 passed
  - `login.test.tsx`: 9 passed
  - `setup.test.tsx`: 5 passed
  - `contrast.test.ts`: 81 passed
  - `gates.test.mjs`: 11 passed
  - `brand.test.tsx`: 5 passed
  - `ui-overrides.test.tsx`: 9 passed
- **Design Gates:** Passed, scanned 62 non-legacy files with 0 violations.
- **Build:** `tsc && vite build` passed in 215ms with 0 errors.
- **Legacy file deletion check:**
  - `test ! -e src/vizenlink_nvr/web/src/legacy/Login.tsx && test ! -e src/vizenlink_nvr/web/src/legacy/SetupWizard.tsx` -> exited 0.

## 3. Commit
- `7a6007d`: `feat(09-06): router, auth routing table, restyled login and setup`

