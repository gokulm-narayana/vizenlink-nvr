# Phase 09 Plan 07 Summary: App Shell, UI Store, Route Registry, User Menu, and Theme Synchronization (AUTH-03, AUTH-06)

## 1. What Was Built
- **Zustand UI Store (`src/stores/ui.ts`):**
  - Manages client state with exact persisted keys: `nvr_theme` ("light" | "dark" | "system", default system), `nvr_sidebar` ("expanded" | "collapsed", default expanded), `nvr_view_mode` ("simple" | "advanced", default simple), `nvr_read_events` (Set of event IDs stored as JSON array), and session-only `dismissedAlertIds` (Set of alert IDs).
  - Provides helper `resolvedTheme(theme)` resolving "system" via matchMedia `(prefers-color-scheme: dark)`.
- **Feature Route Registry & Role Protection (`src/app/routes.tsx`):**
  - Eager discovery of feature routes via `import.meta.glob("../features/**/routes.tsx", { eager: true })` exporting `shellRoutes`.
  - Pattern matching query function `isRegistered(path)`.
  - Role hierarchy: viewer (0) < operator (1) < owner (2).
  - Role guard `<RequireRole min={r.minRole}>` rendering the accessible 403 `Forbidden` state with "You don't have access to this page. Ask the NVR owner to change your role if you need it." and "Go to Live" action button whenever a user lacks permissions.
- **Data Query Extensions (`src/lib/queries.ts`):**
  - Added `useCameras()` (GET `/api/v1/cameras`, staleTime 30s).
  - Added `useRecordingStatus()` (GET `/api/v1/recording/status`, refetchInterval 10s, keeping previous data).
- **Navigation & App Sidebar (`src/components/shell/AppSidebar.tsx`):**
  - shadcn `Sidebar` with `collapsible="icon"`.
  - 56px header row: links to `/` with aria-label "VizenLink NVR, go to Live". Renders `BrandLogo variant="lockup"` when expanded, and `BrandLogo variant="mark"` with Tooltip "VizenLink NVR" when collapsed.
  - Three nav groups: Watch (Live, Playback, Events, Gallery), Monitor (Dashboard), Manage (Cameras, Users, Mobile devices).
  - Cosmetic nav filtering by user role AND registration in `shellRoutes` (`isRegistered(path)`).
  - Active NavLink styling with `bg-selected text-primary-text font-semibold` and 4px leading `bg-primary` indicator.
  - Nav landmark with `aria-label="Primary"`.
- **App Shell & Top Bar (`src/components/shell/AppShell.tsx`):**
  - Integrates `TooltipProvider delayDuration={0}` and `SidebarProvider` bound to store's `sidebarOpen`.
  - Top bar (56px, `h-14`, border-b, bg-card): `SidebarTrigger`, mobile brand mark linking to `/`, single `h1` route heading synchronized from deepest matched route `handle.title`.
  - Non-video content wrapped in `max-w-320 mx-auto w-full` with responsive padding (`p-4 md:p-6`), while full-bleed routes (such as Live) use `p-2`.
- **Theme Synchronization (`src/components/shell/ThemeSync.tsx`, `src/main.tsx`):**
  - Effect component mounted at app root and shell to ensure `document.documentElement` receives or removes `.dark` class dynamically. Subscribes to `prefers-color-scheme` changes live when theme is "system".
  - Toaster at app root synced to store's resolved theme.
- **User Menu & View Mode Toggle (`src/components/shell/UserMenu.tsx`, `src/components/shell/ViewModeToggle.tsx`):**
  - Trigger avatar showing username's first initial on `--muted` background with `aria-label="Account menu for {username}"`.
  - Shows username and secondary role badge.
  - Theme radio group: Light (`Sun`), Dark (`Moon`), System (`Monitor`).
  - View mode radio group inside menu on mobile; desktop `ViewModeToggle` with `ToggleGroup` (Simple/Advanced) in top bar.
  - Sign out item with `LogOut` icon calling `useSignOut()`.
- **Live Feature Adapter (`src/features/live/routes.tsx`):**
  - Registers `/live` with title "Live", viewer role, `fullBleed: true`.
  - Adapts `useCameras()` and `useRecordingStatus()` into legacy `LiveGrid`.
- **Transition Rule Maintained:**
  - `/` and unmatched paths continue serving `LegacyApp` with its original header until Plan 09-08 migrates them.

## 2. Verification Commands & Outputs
```bash
npm --prefix src/vizenlink_nvr/web test -- src/components/shell && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build
```
- **Shell Vitest Suite:** 2 test files, 10 tests passed (100% pass)
  - `shell.test.tsx`: 5 passed
  - `user-menu.test.tsx`: 5 passed
- **Full Vitest Suite:** 10 test files, 147 passed (100% pass)
- **Design Gates:** Passed, scanned 72 non-legacy files with 0 violations.
- **Build:** `tsc && vite build` passed in 229ms with 0 errors.
- **Legacy preservation:** `test -e src/vizenlink_nvr/web/src/legacy/LegacyApp.tsx` verified intact.

## 3. Commit
- `742a347`: `feat(09-07): app shell, UI store, route registry, theme sync and user menu`

