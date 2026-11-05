# Phase 9: UI Redesign - Context

**Gathered:** 2026-11-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the inline-styled React web UI (`src/vizenlink_nvr/web`) with a Tailwind v4 + shadcn/ui design system: light/dark tokens, a collapsible sidebar app shell with a router, and restyled pages (Live, Playback, Events, Gallery, Dashboard, Cameras/Settings, Mobile devices). Bump the web stack to React 19 / Vite 8 / TypeScript ~6.0 and fix the Settings/Devices navigation build break (`tsc` TS2367 in `App.tsx`).

Also in scope (decided in discussion): an Add-camera wizard, user management, change-password and a Profile page. All of these must use existing `/api/v1` endpoints. Backend behaviour, `camera_api` semantics and the "never miss footage" core are untouched.

**Out of scope:** global Search page (needs a new backend; own later phase), a dedicated Alerts page, i18n, PWA, drag-to-arrange tiles.

</domain>

<decisions>
## Implementation Decisions

### Brand and identity
- **D-01:** Brand reference is the VizenLink mobile app, not the old VMS. Accent is the mobile app's indigo `#5B6EF5` (from `/Users/gokul/mobilecctvapp/lib/theme/app_colors.dart`) with a darker variant for light mode that meets WCAG AA on white and on the light ground. The old VMS blue `#0056D2` in the UI-SPEC is superseded. Red is NOT the accent; it stays reserved for offline / critical / destructive / REC status.
- **D-02:** Dark and light grounds follow the mobile app: dark `#0B1120` base, `#141B33` mid, `#1B2340` card; light `#F4F6FB` base, `#E7ECFB` mid, `#FFFFFF` card. Status colors follow the app: online `#34D399`, offline `#FB7185`, attention `#F59E0B` (planner to check each pairing for AA contrast, adjusting the text-use shade if needed).
- **D-03:** Use the mobile app logo images. Copy (do not move; read-only use of that repo) `assets/branding/vizenlink_light.png` and `vizenlink_dark.png` (1536x1024, include the tagline) into the NVR web assets and use them on the sidebar header, Login and Setup. The tagline is too small for the sidebar, so crop or use a lockup variant there. `applogo.svg` is an acceptable vector alternative if it renders correctly on both themes. Replaces the text wordmark in the UI-SPEC. — **Reversibility:** reversible — swapping a bundled asset.
- **D-04:** Do NOT copy the old VMS logos (`nuraeye-rt/vms/assets`).
- **D-05:** The primary-action indigo-to-cyan gradient is NOT adopted: solid indigo accent only.

### Theme and shell
- **D-06:** Default theme follows the system, with a Light / Dark / System override in the user menu (persisted as `nvr_theme`). Video surfaces stay black in both themes.
- **D-07:** Left sidebar, 240 px, collapsible to a 64 px icon rail by the user; Live is not auto-collapsed. Top bar 56 px. Matches the UI-SPEC shell.

### Scope additions
- **D-08:** Add these to Phase 9 beyond the UI-SPEC: (1) Add-camera wizard, (2) user management (list, create, enable/disable, reset password; Owner only), (3) change-password dialog, (4) Profile page (current user, role, change password, theme and view-mode preferences, sign out). Each needs a page contract, copy rows, empty/error states and role gating in the UI-SPEC (see D-13).
- **D-09:** Add-camera wizard uses `POST /api/v1/cameras` (Operator or Owner; takes serial, username, password, streams). The backend exposes NO discovery or scan endpoint (`grep discover` in `src/vizenlink_nvr/api` finds nothing), so the wizard is manual entry unless research shows an existing safe way to scan. If LAN discovery in the web is wanted, that is a new backend capability: flag it as a decision for the owner, not something to build silently in this phase.
- **D-10:** User management uses `users.py` (`GET/POST /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/reset-password`) and `POST /auth/password`. Roles stay `viewer`, `operator`, `owner` (there is no `admin` role in the code). No endpoint or payload changes.
- **D-11:** Global Search is deferred to its own phase (needs a recordings/events search API). Dedicated Alerts page stays deferred; alerts surface in the top-bar bell and the Dashboard.

### Rollout
- **D-12:** Page by page inside one app that builds and runs after every plan. Plan order: (1) tooling and tokens: stack bump, Tailwind, shadcn init, router, shell, theme, fix the TS2367 build break; (2) Live; (3) Playback; (4) Events and Gallery; (5) Dashboard, Cameras/Settings and Mobile devices; (6) Add-camera, users, profile. Exact split is the planner's call but plan 1 must leave `npm run build` green. Each plan must keep the app usable (no half-migrated unusable states).

### UI-SPEC relationship
- **D-13:** `09-UI-SPEC.md` was force-approved before these decisions. Where this CONTEXT.md and the UI-SPEC differ (accent color, grounds, logo, added pages), CONTEXT.md wins. The UI-SPEC still carries the four open items from its sign-off (verb-plus-noun retry labels, sign-out alert role, accent-list gaps, first-run flow e2e). Recommended: re-run `/gsd-ui-phase 9` in Update mode so the contract carries the new tokens and pages before planning; if skipped, the planner must apply D-01 to D-12 on top of it.

### Claude's Discretion
- Exact dark-mode shades for light-mode accent and status text, as long as AA contrast holds.
- Cropping and sizing of the logo lockup for sidebar, collapsed rail and auth pages.
- Final plan split and wave order (D-12 is a guide).
- Form layout of the Add-camera wizard and users table.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design contract
- `.planning/phases/09-ui-redesign/09-UI-SPEC.md` — page, token, copy and web-stack contract (see D-13 for what is superseded)
- `.claude/CLAUDE.md` — project stack decisions and rules (stack, no edits to `camera_api` or mobile packages)
- `.planning/research/STACK.md` — frontend version and library decisions

### Brand sources (read-only; do not modify)
- `/Users/gokul/mobilecctvapp/lib/theme/app_colors.dart` — brand palette (indigo, cyan, status, dark/light grounds)
- `/Users/gokul/mobilecctvapp/lib/theme/app_theme.dart` — how the mobile app applies the palette
- `/Users/gokul/mobilecctvapp/lib/theme/branding.dart` — brand name constant ("VizenLink")
- `/Users/gokul/mobilecctvapp/assets/branding/vizenlink_light.png` and `vizenlink_dark.png` — logo lockups to copy
- `/Users/gokul/mobilecctvapp/assets/branding/applogo.svg` — vector logo alternative

### Backend contracts the new pages call
- `src/vizenlink_nvr/api/v1/cameras.py` — `POST /cameras` (Operator or Owner), `GET/DELETE /cameras/{serial}`, `POST /cameras/{serial}/reprobe`
- `src/vizenlink_nvr/api/v1/users.py` — user CRUD and reset-password (Owner)
- `src/vizenlink_nvr/api/v1/auth.py` — `/auth/status`, `/setup`, `/login`, `/logout`, `/me`, `/password`
- `src/vizenlink_nvr/api/dependencies.py` — `require_role`, `RequireOwner`, `RequireOperator`, `RequireViewer`
- `src/vizenlink_nvr/api/app.py` — SPA fallback (currently an uncommitted change; must be committed before the router ships)

### Visual reference only (old VMS; not for porting)
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms/css/layout.css` and `views/dashboard.html` — shell grid and dashboard zoning ideas

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vizenlink_nvr/web/src/services/player.ts`: WHEP/HLS player logic; re-theme, do not rewrite.
- `src/vizenlink_nvr/web/src/components/TimelineCanvas.tsx` (490 lines): custom canvas timeline; keep the math, re-read colors from tokens.
- `src/vizenlink_nvr/web/src/services/grid_storage.ts`: persisted grid layout; keep its localStorage key.
- Existing components to restyle: Live grid, VideoTile, PlaybackView, TransportBar, ClipExportModal, EventFeed/EventCard, GalleryView, Dashboard, CameraSettingsView (1069 lines), MobilePairingModal, PairedDevicesView, Login, SetupWizard.

### Established Patterns
- All 19 components use inline `style={{}}` with hardcoded hex colors, no CSS files, no router, manual `fetch` + `useState`; current stack React 18 / Vite 5 / TS 5.
- localStorage keys to preserve: `nvr_view_mode`, `nvr_read_events`, the GridStorage key; add `nvr_theme`, `nvr_sidebar`.
- Simple/Advanced mode currently affects only the Dashboard; the UI-SPEC extends it (assumption A7).

### Integration Points
- `App.tsx` string-switch tab state is replaced by routes (this removes the TS2367 errors at lines 224 and 230).
- FastAPI serves the built `web/dist`; SPA fallback in `api/app.py` must be committed.
- Auth is cookie-session via `/api/v1/auth/*`; role names `viewer`, `operator`, `owner`.

</code_context>

<specifics>
## Specific Ideas

- "You know the app I am developing, it has the VizenLink logo": the NVR should look like the same product family as the mobile app (indigo accent, same grounds, same logo).

</specifics>

<deferred>
## Deferred Ideas

- Global Search page (needs a new recordings/events search backend): its own phase.
- Web-based LAN camera discovery (new backend endpoint): owner decision, likely its own phase.
- Dedicated Alerts page, i18n, PWA/offline, drag-to-arrange tiles, indigo-to-cyan gradient styling.

</deferred>

---

*Phase: 9-UI Redesign*
*Context gathered: 2026-11-05*
