# Phase 9: UI Redesign - Research

**Researched:** 2026-11-05
**Domain:** Frontend migration (React 18 / Vite 5 / TS 5 inline-styled SPA to React 19 / Vite 8 / TS 6 + Tailwind v4 + shadcn/ui + React Router 8), served by FastAPI
**Confidence:** HIGH on the toolchain (every version, peer range, init step and build below was run in a scratch project this session); MEDIUM on runtime behaviour of the video components (read, not run against a camera)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Brand reference is the VizenLink mobile app, not the old VMS. Accent is the mobile app's indigo `#5B6EF5` (from `/Users/gokul/mobilecctvapp/lib/theme/app_colors.dart`) with a darker variant for light mode that meets WCAG AA on white and on the light ground. The old VMS blue `#0056D2` in the UI-SPEC is superseded. Red is NOT the accent; it stays reserved for offline / critical / destructive / REC status.
- **D-02:** Dark and light grounds follow the mobile app: dark `#0B1120` base, `#141B33` mid, `#1B2340` card; light `#F4F6FB` base, `#E7ECFB` mid, `#FFFFFF` card. Status colors follow the app: online `#34D399`, offline `#FB7185`, attention `#F59E0B` (planner to check each pairing for AA contrast, adjusting the text-use shade if needed).
- **D-03:** Use the mobile app logo images. Copy (do not move; read-only use of that repo) `assets/branding/vizenlink_light.png` and `vizenlink_dark.png` (1536x1024, include the tagline) into the NVR web assets and use them on the sidebar header, Login and Setup. The tagline is too small for the sidebar, so crop or use a lockup variant there. `applogo.svg` is an acceptable vector alternative if it renders correctly on both themes. Replaces the text wordmark in the UI-SPEC. Reversibility: reversible (swapping a bundled asset).
- **D-04:** Do NOT copy the old VMS logos (`nuraeye-rt/vms/assets`).
- **D-05:** The primary-action indigo-to-cyan gradient is NOT adopted: solid indigo accent only.
- **D-06:** Default theme follows the system, with a Light / Dark / System override in the user menu (persisted as `nvr_theme`). Video surfaces stay black in both themes.
- **D-07:** Left sidebar, 240 px, collapsible to a 64 px icon rail by the user; Live is not auto-collapsed. Top bar 56 px. Matches the UI-SPEC shell.
- **D-08:** Add these to Phase 9 beyond the UI-SPEC: (1) Add-camera wizard, (2) user management (list, create, enable/disable, reset password; Owner only), (3) change-password dialog, (4) Profile page (current user, role, change password, theme and view-mode preferences, sign out). Each needs a page contract, copy rows, empty/error states and role gating in the UI-SPEC (see D-13).
- **D-09:** Add-camera wizard uses `POST /api/v1/cameras` (Operator or Owner; takes serial, username, password, streams). The backend exposes NO discovery or scan endpoint, so the wizard is manual entry unless research shows an existing safe way to scan. If LAN discovery in the web is wanted, that is a new backend capability: flag it as a decision for the owner, not something to build silently in this phase.
- **D-10:** User management uses `users.py` (`GET/POST /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/reset-password`) and `POST /auth/password`. Roles stay `viewer`, `operator`, `owner` (there is no `admin` role in the code). No endpoint or payload changes.
- **D-11:** Global Search is deferred to its own phase. Dedicated Alerts page stays deferred; alerts surface in the top-bar bell and the Dashboard.
- **D-12:** Page by page inside one app that builds and runs after every plan. Plan order: (1) tooling and tokens: stack bump, Tailwind, shadcn init, router, shell, theme, fix the TS2367 build break; (2) Live; (3) Playback; (4) Events and Gallery; (5) Dashboard, Cameras/Settings and Mobile devices; (6) Add-camera, users, profile. Exact split is the planner's call but plan 1 must leave `npm run build` green. Each plan must keep the app usable (no half-migrated unusable states).
- **D-13:** `09-UI-SPEC.md` was force-approved before these decisions. Where this CONTEXT.md and the UI-SPEC differ (accent color, grounds, logo, added pages), CONTEXT.md wins. Recommended: re-run `/gsd-ui-phase 9` in Update mode; if skipped, the planner must apply D-01 to D-12 on top of it.

### Claude's Discretion
- Exact dark-mode shades for light-mode accent and status text, as long as AA contrast holds.
- Cropping and sizing of the logo lockup for sidebar, collapsed rail and auth pages.
- Final plan split and wave order (D-12 is a guide).
- Form layout of the Add-camera wizard and users table.

### Deferred Ideas (OUT OF SCOPE)
- Global Search page (needs a new recordings/events search backend): its own phase.
- Web-based LAN camera discovery (new backend endpoint): owner decision, likely its own phase.
- Dedicated Alerts page, i18n, PWA/offline, drag-to-arrange tiles, indigo-to-cyan gradient styling.
</user_constraints>

<phase_requirements>
## Phase Requirements

No requirement IDs are mapped to Phase 9. Treat these existing v1 requirements as a **regression guard** (the restyle must not break them): LIVE-01 to LIVE-06, PLAY-01 to PLAY-05, AUTH-06 (Simple/Advanced), and the Events/Gallery/Camera Settings/Health groups in `.planning/REQUIREMENTS.md`. [VERIFIED: `.planning/REQUIREMENTS.md` lines 34-40, 59-63]
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Frontend is React + TypeScript (Vite). Locked stack versions: React `^19.3`, Vite `^8.3`, `@vitejs/plugin-react` `^6.1`, TypeScript `~6.0.3` (not 7), Tailwind `^4.3` + `@tailwindcss/vite`, shadcn/ui, React Router `^8.5` (library/SPA mode), TanStack Query, Zustand, zod, react-hook-form, lucide-react, Vitest, Playwright.
- Never modify `camera_api` or anything under the mobile app packages; the old VMS and the mobile repo are read-only reference. Copying the two logo PNGs is the only sanctioned read of the mobile repo (D-03).
- Nothing is exposed to the LAN without auth; time is stored UTC and displayed in the **site IANA time zone**; LAN only; no AI.
- GSD workflow: all edits go through a GSD command; this research wrote only `09-RESEARCH.md`.
- The working tree has **uncommitted, unrelated changes** (`api/app.py` lifespan, `cli/app.py`, `tools/phase_gate.py`, `tests/integration/test_16camera_soak.py`, `STATE.md`, and `web/src/components/Header.tsx`). Plans must stage only their own files. [VERIFIED: `git status` at session start and `git diff`]

## Summary

The stack bump is low risk. I copied the unmodified `web/src` into a scratch project and compiled it under React 19.3.1 + `@types/react` 19.3.0 + TypeScript 6.0.3 + Vite 8.3.6: the **only** `tsc` errors are the two known TS2367 errors at `App.tsx` 224 and 230, and `vite build` succeeds. So Plan 1 can bump the stack and get a green build before anything else changes. The TS2367 break exists only in the working tree: the uncommitted `Header.tsx` diff narrows `ViewTab` and removes the Settings/Devices buttons, while HEAD still has them. Deleting the string-switch tab state (as the UI-SPEC says) removes both errors.

The tooling path works end to end. In a scratch project, `shadcn@4.23.0 init -t vite -b radix -p nova --yes` succeeded on Vite 8 / TS 6 / Tailwind 4.3.4, and adding all 38 planned components type-checked and built. Three things differ from the UI-SPEC and need planner attention: (1) TS 6 rejects `baseUrl` (TS5101) so the alias must be `paths` only, and a CSS side-effect import needs `src/vite-env.d.ts` (TS2882 otherwise); (2) shadcn 4.23 now generates `cn` as a re-export from a new `cn` package and puts `shadcn` itself in `dependencies`, which makes `npm audit` report 6 vulnerabilities until `shadcn` is moved to `devDependencies`; (3) there is no `form` component in shadcn 4.23 (use `field` with react-hook-form).

The larger risks are in the existing app, not the toolchain, and several UI-SPEC claims do not match the code. `TimelineCanvas` is **DOM divs with inline styles, not a `<canvas>`**, and has no wheel zoom, keyboard handling or ARIA. `SetupWizard` sends a required `timezone` and an `allow_system_disk` flag that the UI-SPEC's "keeps exactly the existing fields" list omits. The web player requests `/cam/...` from the FastAPI origin, but only the Vite dev proxy serves that path; in production the SPA fallback answers `200 text/html`, so Live cannot work from the built bundle today. No API exposes the site time zone. None of these block planning, but each needs an explicit task or an owner decision (see Open Questions).

**Primary recommendation:** Plan 1 starts with a stack-bump-only commit (bump, `vite-env.d.ts`, restore `ViewTab`, `npm run build` green, add a `web` CI job), then layers Tailwind/tokens, shadcn, router and shell on top; keep `TimelineCanvas` DOM-based and restyle it with token classes; carry the Setup `timezone` and `allow_system_disk` fields into the new Setup page; and raise the `/cam` proxy gap before the Live plan is verified.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Routing, deep links, `next` redirect validation | Browser / Client (React Router) | Frontend Server (SPA fallback) | Client owns navigation; FastAPI only has to return `index.html` for unknown GETs |
| SPA fallback and static assets | Frontend Server (FastAPI `StaticFiles` + 404 handler) | CDN / Static (n/a, LAN) | Already implemented and committed in `api/app.py` |
| Theme, sidebar, view mode state | Browser / Client (Zustand + `localStorage`) | none | D-06, A17: per-browser, no backend |
| Role gating of routes and controls | API / Backend (authoritative via `require_role`) | Browser / Client (cosmetic hide + 403 state) | Server stays the authority; client hiding is UX only |
| Auth session (cookie) | API / Backend | Browser / Client (`authStatus` query) | HTTP-only SameSite=Lax cookie; client never sees the token |
| Live video (WHEP) | Browser / Client (`TilePlayer`) | API / Backend (media-token), MediaMTX | Client negotiates SDP; media-token endpoint authorises. The `/cam` route is not served by FastAPI (see Pitfall 3) |
| Timeline math and rendering | Browser / Client | API / Backend (segments, outages, events) | Pure client geometry over server-provided spans |
| Add camera / users / password forms | Browser / Client (validation) | API / Backend (authoritative validation, 409/400) | zod mirrors API minimums only for UX |
| Brand assets | Browser / Client (bundled, hashed by Vite) | none | No network fetch at runtime (LAN-only) |

## Standard Stack

### Core (all verified against the npm registry on 2026-11-05)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react / react-dom | 19.3.1 | UI | Locked by CLAUDE.md [VERIFIED: npm view] |
| vite | 8.3.6 | Build / dev server | Locked; engines `^20.19.0\|\|>=22.12.0` [VERIFIED: npm view] |
| @vitejs/plugin-react | 6.2.1 | React transform | Peer `vite ^8.0.0` [VERIFIED: npm view] |
| typescript | `~6.0.3` (6.0.3) | Type checking | **`latest` dist-tag is 7.0.2**; a bare `npm i typescript` installs 7. Pin with `~6.0.3` [VERIFIED: npm view typescript version = 7.0.2; `typescript@~6.0` lists 6.0.2, 6.0.3] |
| tailwindcss + @tailwindcss/vite | 4.3.4 | Styling | Plugin peer `vite ^5.2\|\|^6\|\|^7\|\|^8` [VERIFIED: npm view] |
| react-router | 8.5.1 | Routing | engines `node >=22.22.0`; peers `react >=19.2.7`. `RouterProvider` comes from `react-router/dom`. **Do not install `react-router-dom`** [VERIFIED: npm view; probe typecheck] |
| @tanstack/react-query | 5.106.1 | Server state | Peer `react ^18\|\|^19` [VERIFIED: npm view] |
| zustand | 5.0.16 | Client UI state | [VERIFIED: npm view] |
| lucide-react | 1.69.0 | Icons | Peer includes React 19 [VERIFIED: npm view] |
| shadcn (CLI) | 4.23.0 | Component generator | Put in `devDependencies` (see Pitfall 5) [VERIFIED: probe `npm audit --omit=dev` = 0 vulnerabilities after moving] |
| radix-ui | 1.8.1 | Primitives (shadcn radix base installs the unified package) | [VERIFIED: probe `package.json`] |
| tw-animate-css | 1.4.0 | shadcn animation classes | Added by `shadcn init` [VERIFIED: probe] |
| class-variance-authority | 0.7.1 | Variant helper | Added by shadcn [VERIFIED: probe] |
| cn | 0.5.2 | `cn()` helper that shadcn 4.23 now re-exports (`export { cn } from "cn"`) | Maintainer `shadcn`, repo `shadcn-ui/cn` [VERIFIED: npm view cn@0.5.2 maintainers and repository; probe `src/lib/utils.ts`] |
| sonner | 2.0.8 | Toasts | shadcn `sonner` imports `next-themes` (see Pitfall 6) [VERIFIED: probe] |
| react-day-picker + date-fns | 10.0.2 / 4.4.0 | Calendar | Pulled in by shadcn `calendar`; type-checks under TS 6 [VERIFIED: probe] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| react-hook-form | 7.91.0 | Forms | Not installed by shadcn; add explicitly. There is no shadcn `form` file in 4.23 (use `field`) [VERIFIED: npm view; probe `ls src/components/ui` shows `field.tsx`, no `form.tsx`] |
| zod | 4.6.7 | Schemas | [VERIFIED: npm view] |
| @hookform/resolvers | 7.0.3 | zod resolver | Peers `zod ^3.25\|\|^4`, `react-hook-form ^7.55.0` [VERIFIED: npm view] |
| @fontsource-variable/inter | 5.3.0 | Self-hosted font | `shadcn init` installs Geist by default; swap to Inter per A10 [VERIFIED: npm view; probe shows geist import] |
| vitest | 5.1.0 | Unit/component tests | engines `^22.12.0\|\|^24.0.0\|\|>=26.0.0`; peer `vite ^6.4\|\|^7\|\|^8` [VERIFIED: npm view; probe test run passed] |
| jsdom | 30.1.3 | DOM for Vitest | engines `^22.22.2\|\|^24.15.0\|\|>=26.0.0` [VERIFIED: npm view] |
| @testing-library/react / dom / jest-dom / user-event | 16.3.3 / 10.x / 7.0.1 / 14.6.8 | Component tests | RTL has `@testing-library/dom ^10` as a **peer you must install** [VERIFIED: npm view; probe] |
| @playwright/test | 1.64.1 | E2E | engines `node >=20`; run `npx playwright install chromium` [VERIFIED: npm view] |
| @types/react, @types/react-dom | 19.3.0 | Types | [VERIFIED: npm view] |
| @types/node | 26.6.6 (or the `^22.12\|\|>=24` major matching CI) | Vite config typing | Vite peer `^20.19.0\|\|>=22.12.0` [VERIFIED: npm view] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `cn` package (shadcn 4.23 default) | `clsx` + `tailwind-merge` 3.7.0 (UI-SPEC wording) | Equivalent behaviour. Keep whichever `shadcn init` generates; if the team prefers the UI-SPEC pair, edit `src/lib/utils.ts` once. Do not run both. |
| `next-themes` in `sonner.tsx` | Zustand theme store | UI-SPEC already requires replacing it; this also removes the `next-themes` dependency |

**Installation (matches what was run in the probe):**
```bash
cd src/vizenlink_nvr/web
npm i react@^19.3 react-dom@^19.3 react-router@^8.5 @tanstack/react-query@^5.104 zustand@^5 lucide-react@^1.61 \
      react-hook-form@^7.91 zod@^4.6 @hookform/resolvers@^7 @fontsource-variable/inter
npm i -D vite@^8.3 @vitejs/plugin-react@^6.1 typescript@~6.0.3 @types/react@^19 @types/react-dom@^19 @types/node \
         tailwindcss@^4.3 @tailwindcss/vite@^4.3 \
         vitest@^5.1 jsdom@^30 @testing-library/react@^16.3 @testing-library/dom@^10 @testing-library/jest-dom@^7 @testing-library/user-event@^14 \
         @playwright/test@^1.64
npx shadcn@4.23.0 init -t vite -b radix -p nova --yes   # then: npm i -D shadcn@4.23.0 (move it out of dependencies)
npx shadcn@4.23.0 add sidebar button-group toggle-group toggle tabs card badge alert alert-dialog dialog sheet popover calendar select native-select input input-group label field switch slider checkbox radio-group table progress skeleton spinner empty tooltip dropdown-menu avatar scroll-area separator sonner kbd pagination collapsible --yes
```
`shadcn init` without `-p` is interactive even with `--yes` (it prompts for a preset); `-p nova` makes it non-interactive. [VERIFIED: probe; first run hung on the preset prompt]

**Version verification:** every version above was read from `npm view` on 2026-11-05. Node here is v26.9.0 and npm 11.19.1, which satisfy every engines range. CI must use Node `>=24.15` (jsdom 30 needs `^22.22.2 || ^24.15.0 || >=26`; react-router 8 needs `>=22.22`).

## Package Legitimacy Audit

Ran `gsd-tools query package-legitimacy check --ecosystem npm` on 37 packages. No package returned **SLOP**. 35 returned **SUS**, but every reason was a heuristic (`too-new` = a release in the last few weeks; `unknown-downloads` = no download count returned), not a missing repo or install script. No package reported a `postinstall` script. Every package has a source repo owned by the expected org.

| Package | Registry | Downloads/wk | Source Repo | Verdict | Disposition |
|---------|----------|-------------|-------------|---------|-------------|
| react, react-dom | npm | ~247M / ~231M | github.com/react/react | SUS (too-new) | Approved: named in CLAUDE.md and UI-SPEC |
| vite, @vitejs/plugin-react | npm | ~253M / ~122M | vitejs/vite, vitejs/vite-plugin-react | SUS (too-new) | Approved: named in CLAUDE.md |
| typescript | npm | ~407M | microsoft/TypeScript | OK | Approved (pin `~6.0.3`) |
| tailwindcss, @tailwindcss/vite | npm | ~169M / ~56M | tailwindlabs/tailwindcss | SUS (too-new) | Approved: named in CLAUDE.md |
| react-router | npm | ~74M | remix-run/react-router | SUS (too-new) | Approved: named in CLAUDE.md |
| @tanstack/react-query, zustand, lucide-react, react-hook-form, zod, @hookform/resolvers | npm | 47M to 450M | official org repos | SUS (too-new) | Approved: named in CLAUDE.md / UI-SPEC |
| sonner | npm | ~55M | emilkowalski/sonner | OK | Approved |
| radix-ui | npm | ~26M | radix-ui/primitives | SUS (too-new) | Approved: installed by shadcn |
| shadcn, cn | npm | null | shadcn-ui/ui, shadcn-ui/cn | SUS (too-new, unknown-downloads) | Approved: maintainer `shadcn`, named in UI-SPEC (`shadcn@4.23.0`); `cn` is the new shadcn-owned helper |
| vitest, jsdom, @playwright/test, @testing-library/*, @types/* | npm | mixed/null | official org repos | SUS (too-new / unknown-downloads) | Approved: standard tools named in CLAUDE.md |
| @fontsource-variable/inter, clsx, tailwind-merge, class-variance-authority, tw-animate-css, next-themes, react-day-picker, date-fns | npm | null | official repos | SUS (unknown-downloads) | Approved: named in UI-SPEC or installed by the shadcn CLI |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged [SUS]:** the rows above. Because the flags are download-count and release-age heuristics on packages the project documents already name, I recommend **one** `checkpoint:human-verify` in Plan 1 (review the `package-lock.json` diff and `npm audit --omit=dev` output) instead of a checkpoint per package. If the planner wants to follow the protocol literally, the genuinely new-to-the-project names are `cn`, `shadcn`, `tw-animate-css` and `@fontsource-variable/inter`.

Provenance note: package names in this section came from CLAUDE.md and the approved UI-SPEC (authoritative project documents) or were emitted by the official `shadcn` CLI during the probe; none came from web search.

## Architecture Patterns

### System Architecture Diagram

```
Browser (any LAN host)
   |
   |  GET /playback?camera=X&t=T     (deep link, hard reload)
   v
FastAPI (api/app.py)
   |-- /api/v1/*  --> routers (cookie-session auth, require_role)   <-- JSON
   |-- /assets/*  --> StaticFiles(web/dist/assets)                  <-- hashed bundles
   |-- anything else, 404 --> spa_404_handler --> web/dist/index.html (200)
   v
index.html -> inline theme script (adds .dark before paint) -> main.tsx
   |
   v
createBrowserRouter
   |-- /login, /setup  (outside shell)  <-- boot: GET /api/v1/auth/status -> AuthGate (12-row table)
   |-- <Shell> (SidebarProvider open from Zustand/nvr_sidebar, TopBar, AlertStack)
         |-- /            LiveGrid -> VideoTile -> TilePlayer -> POST media-token, POST /cam/<s>/<role>/whep
         |-- /playback    PlaybackView + TimelineCanvas(segments/outages/events) + ClipExport
         |-- /events, /gallery, /dashboard
         |-- /cameras, /cameras/add, /cameras/:serial   (operator, owner)
         |-- /users (owner), /devices (owner), /profile (all)
   |
   v
TanStack Query (authStatus, me, cameras, recording status, health, alerts, events, storage, users)
```

### Recommended Project Structure
```
web/
├── components.json              # from shadcn init
├── vite.config.ts               # react(), tailwindcss(), resolve.tsconfigPaths, test block, dev proxy
├── tsconfig.json                # "paths": {"@/*": ["./src/*"]} and NO baseUrl
├── playwright.config.ts
├── e2e/                         # Playwright specs (a-f from the UI-SPEC)
├── src/
│   ├── vite-env.d.ts            # /// <reference types="vite/client" />  (required under TS 6)
│   ├── styles/{tokens,globals}.css
│   ├── components/ui/*          # shadcn, edited per override rules
│   ├── components/shell/*
│   ├── features/{auth,live,playback,events,gallery,dashboard,cameras,devices,users,profile}/
│   ├── lib/{utils.ts,safe-next.ts,timeline.ts,api.ts}
│   ├── stores/ui.ts
│   ├── assets/brand/*
│   └── test/setup.ts
```

### Pattern 1: tsconfig and Vite config that were tested under TS 6.0.3 / Vite 8.3.6
```jsonc
// tsconfig.json  (tested: tsc exit 0, shadcn init accepted it)
{
  "compilerOptions": {
    "target": "ES2020", "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext", "moduleResolution": "bundler", "skipLibCheck": true,
    "resolveJsonModule": true, "isolatedModules": true, "noEmit": true,
    "jsx": "react-jsx", "strict": true, "noFallthroughCasesInSwitch": true,
    "paths": { "@/*": ["./src/*"] }          // NO "baseUrl": TS 6 errors TS5101
  },
  "include": ["src", "e2e"]
}
```
```ts
// vite.config.ts  (tested: build + vitest run)
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { tsconfigPaths: true },
  server: { port: 3000, proxy: { "/api": "http://127.0.0.1:8000", "/cam": "http://127.0.0.1:8889" } },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false },
});
```
[VERIFIED: scratch probe this session. The `@/` alias also resolved with no Vite config at all, so Rolldown reads tsconfig paths; `resolve.tsconfigPaths: true` makes that explicit.]

### Pattern 2: Tailwind v4 tokens with compile-time scale enforcement
```css
/* styles/tokens.css (excerpt) -- tested: text-lg and font-medium produce NO css; text-display, text-sm, font-semibold do */
@import "tailwindcss";
@custom-variant dark (&:is(.dark *));
@theme {
  --text-*: initial;
  --text-xs: 0.75rem;      --text-xs--line-height: 1.5;
  --text-sm: 0.875rem;     --text-sm--line-height: 1.5;
  --text-xl: 1.25rem;      --text-xl--line-height: 1.2;
  --text-display: 1.75rem; --text-display--line-height: 1.2;
  --font-weight-*: initial;
  --font-weight-normal: 400;
  --font-weight-semibold: 600;
}
```
Caution: an off-scale class then becomes a **silent no-op** (e.g. shadcn's `font-medium` falls back to inherited weight, not 600). Resetting the namespace is a safety net; the shadcn override edits and the grep gates still have to happen. [VERIFIED: probe build, grep of `dist/assets/*.css`]

### Pattern 3: React Router 8 data router (library mode)
```tsx
// Source: probe typecheck against react-router 8.5.1 exports (".", "./dom")
import { createBrowserRouter, Navigate, NavLink, Outlet, useBlocker, useSearchParams, redirect } from "react-router";
import { RouterProvider } from "react-router/dom";
```
`useBlocker` requires a data router (`createBrowserRouter`), which the UI-SPEC already chooses; it is the supported way to implement "browser Back with unsaved input opens an alert-dialog" on the wizard. `NavLink` sets `aria-current="page"` (asserted in a passing RTL test). [VERIFIED: probe]

### Pattern 4: Pure, testable helpers extracted before restyling
- `lib/safe-next.ts`: the `next` validator from the UI-SPEC (single leading `/`, no `//`, no backslash, not `/login`, `/setup`, `/api`).
- `lib/timeline.ts`: move `getWindowRange`, `timeToPct`, `pctToDate` out of `TimelineCanvas.tsx` (lines 65-99 today) into pure functions so Vitest covers them before the DOM is touched.
- `AuthGate`: a single component that implements the 12-row auth table from `authStatus`.

### Anti-Patterns to Avoid
- **Running `shadcn init` before the tsconfig has `paths`**: init validates the alias; the probe passed only after `paths` existed.
- **Leaving `shadcn` in `dependencies`**: pulls ts-morph/minimatch into the production audit.
- **Trusting the shadcn sidebar cookie**: its `setOpen` writes `document.cookie = sidebar_state=...` on every toggle (sidebar.tsx line ~85). Control `open` from the store and delete that line, since nothing reads the cookie in a Vite SPA.
- **Keeping shadcn's Ctrl/Cmd+B shortcut** if `[` is the contract: `SIDEBAR_KEYBOARD_SHORTCUT = "b"` with `metaKey || ctrlKey` is built in; change it.
- **Migrating all 19 components in one commit**: D-12 forbids a half-migrated unusable state.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dialog/sheet/popover focus trap, escape handling | Custom modal divs (today's `ClipExportModal`, `MobilePairingModal`, `OutageHistoryModal`) | shadcn `dialog`, `alert-dialog`, `sheet` (Radix) | Focus management and `aria-modal` are free; today's modals have none |
| Sidebar collapse, mobile drawer, tooltips on rail | Custom sidebar | shadcn `sidebar` with controlled `open` | Handles icon rail, Sheet below 768, `data-state` styling |
| Form validation and error focus | Per-field `useState` | react-hook-form + zod (`setFocus`, resolver) | Spec requires "first invalid field gets focus" on 6 forms |
| Server state polling and invalidation | `setInterval` + `fetch` + `useState` (App.tsx lines 116-125; Dashboard line 43) | TanStack Query `refetchInterval` | Existing code re-creates the interval on every `readEventIds` change |
| Toast stack | Custom | sonner | Matches spec; swap `next-themes` for the store |
| Date picker with day markers | Custom calendar | shadcn `calendar` (react-day-picker 10) with `modifiers` | Footage-day dots are a modifier |
| Theme flash prevention | Anything but a tiny inline script in `index.html` | Inline script setting `.dark` from `nvr_theme` / `prefers-color-scheme` | No CSP exists in the app, so inline script is allowed [VERIFIED: grep for Content-Security-Policy in `src/vizenlink_nvr` found nothing] |
| Contrast checking | Eyeballing | A Vitest test that parses `tokens.css` and asserts ratios (UI-SPEC acceptance 9) | I recomputed the spec's table with the WCAG formula and it matches (e.g. white on `#4656E8` 5.59, `#050810` on `#5B6EF5` 4.76, `#8C99FF` on `#243068` 4.78) [VERIFIED: scratch script] |

**Key insight:** the restyle is mostly mechanical; the expensive parts are the net-new behaviours the UI-SPEC adds on top of "restyle" (timeline keyboard/wheel/ARIA, auth routing, wizard, users). Plan those as features with tests, not as styling.

## Runtime State Inventory

> This is not a rename/migration of a runtime-registered string, but the stored-key question matters for the UI state keys.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Browser `localStorage`: `nvr_view_mode`, `nvr_read_events`, `vizenlink_nvr_grid_layout_v1` (the GridStorage key, [VERIFIED: `grid_storage.ts` line 14: `const STORAGE_KEY = "vizenlink_nvr_grid_layout_v1";`]). New: `nvr_theme`, `nvr_sidebar` | Code edit only: keep the three existing keys byte-identical; no data migration |
| Live service config | None. No backend or MediaMTX change in this phase | None |
| OS-registered state | None | None |
| Secrets/env vars | None changed. Session cookie name comes from `SESSION_COOKIE_NAME` (unchanged) | None |
| Build artifacts | `web/dist/` is git-ignored (`dist/` in `.gitignore`) and is the only thing FastAPI serves; the existing `dist/assets/index-CgmrIyRj.js` is stale after any change. `package-lock.json` is tracked. Wheel packaging does not build the web UI (no `npm` reference in `pyproject.toml`, `tools/`, or `.github`) | Rebuild `dist` before any manual or e2e check; `node_modules` must be reinstalled after the major bumps (`npm ci`) |

## Common Pitfalls

### Pitfall 1: TS 6 rejects the usual shadcn tsconfig and bare CSS imports
**What goes wrong:** `baseUrl` gives `TS5101: Option 'baseUrl' is deprecated and will stop functioning in TypeScript 7.0`; `import "./styles/globals.css"` gives `TS2882: Cannot find module or type declarations for side-effect import`.
**Why:** TS 6 deprecates `baseUrl` and enables side-effect import checking.
**How to avoid:** `paths` without `baseUrl`; add `src/vite-env.d.ts` containing `/// <reference types="vite/client" />`. Do not add `ignoreDeprecations`.
**Warning signs:** `npm run build` fails at `tsc` before Vite starts. [VERIFIED: both errors reproduced in the probe]

### Pitfall 2: `tsc` is not run in CI, which is how TS2367 shipped
**What goes wrong:** `.github/workflows/ci.yml` has no Node step, so a broken `npm run build` never fails a check. [VERIFIED: ci.yml read in full; no node/npm reference]
**How to avoid:** add a `web` job in Plan 1 (`actions/setup-node` latest release is v7.1.0 [VERIFIED: `gh api repos/actions/setup-node/releases/latest`]; Node 24; `npm ci`, `npm run build`, `npm test`, grep gates). Adding a second job does not break `tests/unit/test_ci_workflow.py`, which only inspects `jobs.test`. [VERIFIED: file read]

### Pitfall 3: `/cam/...` is not served by FastAPI, so Live cannot work from the built bundle
**What goes wrong:** `player.ts` posts SDP to `/cam/${serial}/${stream}/whep?token=...` on the page origin. The only thing that maps `/cam` to MediaMTX `:8889` is the Vite **dev** proxy. In production the SPA 404 handler answers every unknown path with `index.html` and status 200; I observed `GET /cam/s1/main/whep` return `200 text/html`. `whepRes.ok` is then true and `setRemoteDescription` receives HTML, so every tile ends offline.
**Why it matters:** The mobile endpoint builds `http://{host}:8889/{path}/whep?token={token}` directly, and MediaMTX is configured with `webrtcAllowOrigins: []`, so a cross-origin browser call to `:8889` is blocked by default. [VERIFIED: `api/v1/mobile.py` lines 408-412; `media/config.py` line 86; TestClient probe]
**How to avoid:** this is a pre-existing gap, not caused by the restyle, but Plan 2 (Live) cannot be accepted without live video. It needs an owner decision (see Open Questions 1): same-origin reverse proxy in FastAPI, or `webrtcAllowOrigins` + a direct `:8889` URL in the player. Do not paper over it in UI code.

### Pitfall 4: The SPA fallback swallows missing assets and non-GET requests
**What goes wrong:** observed with the committed handler: `GET /assets/nope.js` returns `200 text/html`; `POST /foo` returns `200` HTML; `GET /api` (no trailing slash) returns HTML; `GET /openapi.json` returns HTML (the real one is `/api/v1/openapi.json`). After a rebuild, a browser holding an old `index.html` requests a vanished hashed chunk and gets HTML with 200, producing a confusing parse error instead of a 404 and reload.
**How to avoid:** a small backend change (return 404 for `/assets/`, `/cam/`, and non-GET/HEAD) is outside "backend untouched"; list it as an optional owner-approved fix with a pytest in `tests/unit`. The Playwright suite should include one assertion that `/assets/does-not-exist.js` is not HTML only if the fix is approved.
**Correction to CONTEXT.md:** the canonical-refs note says the SPA fallback is "currently an uncommitted change". It is **committed** (`git show HEAD:src/vizenlink_nvr/api/app.py` contains `spa_404_handler`). The uncommitted `app.py` diff is the unrelated `lifespan` addition. Nothing needs committing for the router. [VERIFIED: `git diff`, `git show HEAD`]

### Pitfall 5: shadcn 4.23 init puts `shadcn` in `dependencies`
**What goes wrong:** `npm audit` reports 6 vulnerabilities (2 low, 4 moderate; minimatch via ts-morph via shadcn). `security_enforcement` is on in `.planning/config.json`.
**How to avoid:** `npm i -D shadcn@4.23.0` after init. Probe: `npm audit --omit=dev` then reports 0 vulnerabilities and `vite build` still succeeds, because `@import "shadcn/tailwind.css"` is resolved at build time. Gate in CI: `npm audit --omit=dev --audit-level=high`. [VERIFIED: probe]

### Pitfall 6: shadcn defaults violate several UI-SPEC rules
Counted in the generated `src/components/ui` after adding the planned set: 26 `font-medium`, 7 `text-base`, 3 `backdrop-blur-xs`, plus shadow classes. The spec bans 500-weight, 16 px text and `backdrop-blur` over video. The `backdrop-blur` hits matter: a modal overlay over 16 live WebRTC tiles forces per-frame blur compositing. Also `sonner.tsx` imports `next-themes`, `sidebar.tsx` defaults to 16rem / 3rem widths (spec: 15rem / 4rem, set through the provider `style`), and `use-mobile.ts` initial state is `false` so a phone gets one frame of the desktop sidebar. Sequence for the executor: add components, then run the override edits, then the grep gate (acceptance 10). [VERIFIED: probe counts and file reads]

### Pitfall 7: `Setup` loses required fields if the spec is followed literally
`SetupRequest` requires `timezone` (`min_length=1`) and accepts `allow_system_disk`. The current `SetupWizard` has a Timezone input (default `"UTC"`) and an "Allow recordings on system root partition (testing/dev)" checkbox and sends both. The UI-SPEC says Setup "keeps exactly the existing fields: Owner username, Password, Confirm password, Recording storage directory", which omits both. Dropping `timezone` yields a 422; dropping the checkbox makes it impossible to set up on a dev machine whose storage path is on the system disk (the backend has a system-drive guard). [VERIFIED: `api/v1/auth.py` lines 46-51 `SetupRequest`; `SetupWizard.tsx` lines 11, 31-41, 98-127]
**How to avoid:** the Setup task must list all six body fields. Ask for a UI-SPEC amendment (or document it as planner-applied) before Plan 1 finishes. Use a timezone `select` fed by `Intl.supportedValuesOf("timeZone")` defaulting to the browser zone [ASSUMED: Intl API availability on all target browsers; verify in Playwright Chromium].

### Pitfall 8: `TimelineCanvas` is not a canvas
**What goes wrong:** the UI-SPEC and STACK.md describe a `<canvas>` with a `getComputedStyle` token reader, `devicePixelRatio` scaling, a `role="slider"`, wheel/pinch zoom and a visually hidden span table. The real component is `div` elements positioned by percentage with 29 inline `style={{}}` blocks and hex colours (`#10b981`, `#f59e0b`, `#ef4444`, `#eab308`, `#38bdf8`, `#0284c7`, etc.). It has no `onWheel`, `onKey*`, `role`, `aria-*` or `tabIndex`. [VERIFIED: `grep` of `TimelineCanvas.tsx` returned no canvas/wheel/aria matches; lines 1-130 read]
**How to avoid:** keep the DOM implementation (cheap: roughly 288 five-minute spans per camera per day) and restyle it with Tailwind token classes, which removes the `getComputedStyle` and theme-redraw requirements entirely. Treat keyboard control, ARIA slider semantics, wheel zoom, the legend and the hidden table as **new feature tasks** with Vitest tests. If the owner insists on a real canvas, that is a rewrite and belongs to its own plan.
**Time zone caveat:** the day window is built with `startOfDay.setHours(0,0,0,0)` in the **browser's** local zone, not the site zone. See Open Question 4.

### Pitfall 9: Web player lifecycle and policy gaps
`TilePlayer.start()` awaits a token fetch then creates the `RTCPeerConnection`; if `cleanup()` runs in between (route change, StrictMode double mount, tile unmount), the peer connection is created after cleanup and leaks. With a router, tiles mount and unmount far more often. Other facts: `iceServers: [{ urls: "stun:stun.l.google.com:19302" }]` contacts a public Google host, which contradicts the LAN-only, no-external-requests rule; there is no automatic reconnect in `player.ts` or `VideoTile.tsx` even though the spec says "reconnect is automatic" and LIVE-04 requires it; and there is no hls.js fallback anywhere in the web source although D-45 and STACK.md promise one. The MediaMTX path is lower-cased (`cam/{serial.lower()}/main`) while the player uses `serial` as given. [VERIFIED: `player.ts` lines 70-80; `VideoTile.tsx` lines 30-46 and grep for restart/reconnect; `media/reconciler.py` line 223; grep for hls]
**How to avoid:** Plan 2 adds a `disposed` flag to `TilePlayer` (checked after each await), removes the public STUN server (LAN host candidates do not need it; flag to the owner), lower-cases the serial in the URL, and states clearly in the plan whether auto-reconnect and HLS fallback are in scope (they are not restyle work). `player.ts` has no React or colour dependencies, so theming does not touch it.

### Pitfall 10: Wizard stream payload details
`StreamInput` defaults are `role: "main"`, `profile_token: "Profile_1"`, `venc_token: "VideoEncoder_1"`, `scheme: "rtsp"`, `port: 554`, `path: "/stream1"`, `codec: "H264"`, `width: 1920`, `height: 1080`, `transport: "tcp"`. A sub stream must send `role: "sub"` and should not reuse the main stream's tokens. `CameraCreateRequest.password` defaults to `"admin123"` and `streams` defaults to `[]`. [VERIFIED: `api/v1/cameras.py` lines 47-61, 65-84] Whether duplicate tokens are rejected server-side was not checked [ASSUMED]; the plan should verify with a pytest against `POST /cameras` before the wizard ships.

### Pitfall 11: Test-environment gaps in jsdom
jsdom does not implement `window.matchMedia`, `ResizeObserver`, `HTMLMediaElement.play`, or `RTCPeerConnection`, all of which the shell (`useIsMobile`), tiles and Radix components touch. Stub them in `src/test/setup.ts` [ASSUMED: standard jsdom limitation; confirm on first test failure]. `fetch` mocking: use a tiny typed `vi.stubGlobal("fetch", ...)` helper instead of adding MSW.

## Code Examples

### Tested Vitest + RTL + react-router 8 smoke test
```tsx
// Source: scratch probe, passed with vitest 5.1.0 + jsdom 30
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route, NavLink } from "react-router";
import { expect, it } from "vitest";
import { Button } from "@/components/ui/button";
it("renders", () => {
  render(<MemoryRouter initialEntries={["/b"]}><NavLink to="/b">B</NavLink>
    <Routes><Route path="/b" element={<Button>Go</Button>} /></Routes></MemoryRouter>);
  expect(screen.getByRole("link", { name: "B" })).toHaveAttribute("aria-current", "page");
});
```
`src/test/setup.ts` contains `import "@testing-library/jest-dom/vitest";`.

### Contrast test oracle (values for the table in `tokens.css`)
The scratch script `/private/tmp/claude-501/-Users-gokul-Desktop-Vizenlink-Vms/6ee05f59-6d02-4813-8658-dd4423edd26b/scratchpad/contrast.mjs` reproduces every pairing in the UI-SPEC table with the relative-luminance formula; all matched the spec to two decimals (light: primary-foreground on primary 5.59; dark: 4.76; dark `--primary` fill on card 3.67, which is non-text and passes the 3:1 bar). Port the 15-line `lum`/`cr` function into `src/test/contrast.test.ts` and parse hex values out of `tokens.css`. [VERIFIED: script run]

### Playwright e2e against the real backend
```ts
// playwright.config.ts (shape; commands verified to exist, not yet run end to end)
webServer: {
  command: "uv run nvr run --host 127.0.0.1 --port 8765 --no-mdns --data-dir ./.e2e-data",
  url: "http://127.0.0.1:8765/api/v1/auth/status",
  env: { NVR_SECRETS_BACKEND: "file" },
  reuseExistingServer: false,
}
```
`nvr run` accepts `--host --port --data-dir --no-mdns`; entry point `nvr = "vizenlink_nvr.cli.app:app"`; `create_app` serves `web/dist` only if it exists, so run `npm run build` first. The session cookie is HTTP-only SameSite=Lax and `secure` defaults to False, so plain-HTTP e2e works. [VERIFIED: `cli/app.py` lines 75-119, `pyproject.toml` line 46, `session_manager.py` lines 114-126]. Auth e2e (a) needs a fresh data dir per run; (b) to (e) reuse one initialized dir via `storageState` or a setup project. Playwright browsers are already cached on this machine under `~/Library/Caches/ms-playwright` (chromium-1217), but 1.64.1 may need its own revision: run `npx playwright install chromium`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `react-router-dom` package | `react-router` + `react-router/dom` for `RouterProvider` | RR 7, kept in 8 | Do not install `react-router-dom` |
| `baseUrl` + `paths` | `paths` only | TS 6.0 | `baseUrl` is an error without `ignoreDeprecations` |
| `form` shadcn component (react-hook-form wrapper) | `field` component | shadcn 4.x | `add form` produced no `form.tsx` in 4.23 |
| `clsx` + `tailwind-merge` in `utils.ts` | `cn` package re-export | shadcn 4.23 | New dependency name in the lockfile |
| `tailwind.config.js` | CSS-first `@theme` in the CSS file | Tailwind 4 | `components.json` has `"config": ""` |
| `npm i typescript` | `typescript@latest` is now 7.0.2 | 2026 | Pin `~6.0.3` explicitly |

**Deprecated/outdated in the UI-SPEC:** `shadcn add form` (use `field`); the statement that `TimelineCanvas` is a canvas; `Plan 1` text "commit the SPA fallback" (already committed); "`tsc --noEmit && vite build`" is already what `tsconfig.noEmit` makes `tsc && vite build` do, so either script text works.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Intl.supportedValuesOf("timeZone")` works on every supported browser for the Setup timezone select | Pitfall 7 | Setup would need a static IANA list; low impact |
| A2 | Server does not reject duplicate `profile_token`/`venc_token` between main and sub streams on `POST /cameras` | Pitfall 10 | Wizard may 4xx/409 for sub streams; verify with a pytest |
| A3 | jsdom lacks `matchMedia`, `ResizeObserver`, `play()`, `RTCPeerConnection`, so tests need stubs | Pitfall 11 | Extra setup time only |
| A4 | Removing the public STUN server does not break WebRTC on a LAN (host candidates suffice) | Pitfall 9 | Live fails across subnets/VLANs; owner should confirm network topology |
| A5 | CI runner Node 24 resolves to >=24.15 (jsdom 30 engine) | Standard Stack | CI install warning or failure; pin `node-version: 24.x` and check |
| A6 | Rolldown resolving `@/` with no config is stable behaviour, not an accident of this probe | Pattern 1 | Mitigated by setting `resolve.tsconfigPaths: true` explicitly |

## Open Questions

1. **How does the browser reach MediaMTX WHEP in production? (blocking for Plan 2 acceptance)**
   - Known: web player calls `/cam/<serial>/<role>/whep` on the page origin; only the Vite dev proxy serves it; FastAPI returns HTML 200; MediaMTX `webrtcAllowOrigins` is `[]`.
   - Unclear: whether Phase 5/8 verification ever exercised web Live from a built bundle.
   - Recommendation: ask the owner to choose (a) a FastAPI reverse proxy for `/cam/*` (backend change) or (b) `webrtcAllowOrigins` for the NVR origin plus a direct `http://<host>:8889` URL (config change). Until then Plan 2 verifies Live only via the Vite dev proxy.
2. **Setup form fields.** Recommendation: keep `timezone` and `allow_system_disk`; amend the UI-SPEC (or have the planner list them explicitly).
3. **Keep `TimelineCanvas` DOM-based?** Recommendation: yes; treat keyboard/ARIA/wheel as new tasks and scope them (they are sizeable). Owner should confirm that a true `<canvas>` rewrite is not expected this phase.
4. **Site time zone source.** The setup flow stores a `timezone`, but no `/api/v1` response exposes it (grep of `api/v1/*.py` finds `timezone` only in `auth.py` setup and `camera_settings.py`). The project rule and UI-SPEC say display in the site IANA zone; the web can only use the browser zone today. Recommendation: Phase 9 uses the browser zone and records the gap; a read-only site-timezone field on an existing endpoint is a small backend change for the owner to approve.
5. **SPA fallback hardening** (assets/non-GET/`/cam` returning HTML). Recommendation: optional backend fix with a pytest; owner approval needed because the phase says backend untouched.
6. **Auto-reconnect and HLS fallback in the web player.** Neither exists in the web source. Recommendation: state in the Live plan that they are out of scope (restyle only) or add them as explicit tasks.
7. **UI-SPEC amendments.** Revision 4 already carries D-01 to D-13, so the planner does not need to re-apply them. Remaining open items to carry as explicit plan notes: `form` to `field`, `cn` vs clsx/tailwind-merge, Setup fields, timeline implementation, `/cam`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Build, Vitest, Playwright | yes | v26.9.0 | CI: Node 24 (>=24.15) |
| npm | Install | yes | 11.19.1 | n/a |
| uv + project `.venv` (Python 3.13) | e2e server (`uv run nvr run`) | yes | uv at `~/.local/bin/uv` | n/a |
| Playwright browsers | e2e | cached chromium-1217 etc. | revision may not match 1.64.1 | `npx playwright install chromium` |
| Pillow | Logo cropping | no (not in `.venv`) | n/a | `uv run --with pillow python tools/crop_brand.py` (one-off, not a project dependency); `sips` cannot crop by alpha bbox |
| Mobile logo PNGs | D-03 | yes | `vizenlink_light.png`, `vizenlink_dark.png`, both 1536x1024 RGBA | n/a |
| Real camera + MediaMTX | Manual Live/Playback checks | not probed | n/a | Human checkpoint at end of phase (`human_verify_mode: end-of-phase`) |

**Missing dependencies with no fallback:** none. **With fallback:** Pillow (one-off script), Playwright browser revision.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest 5.1.0 + jsdom 30.1.3 + Testing Library (unit/component); Playwright 1.64.1 (e2e). No JS test infrastructure exists today (web `package.json` has no test script). Python side: pytest 9 in `tests/` |
| Config file | none yet: Wave 0 adds `test` block in `vite.config.ts`, `src/test/setup.ts`, `playwright.config.ts` |
| Quick run command | `cd src/vizenlink_nvr/web && npm test` (`vitest run`) |
| Full suite command | `cd src/vizenlink_nvr/web && npm run build && npm test && npx playwright test` |

### Phase Requirements to Test Map
No mapped requirement IDs; map the UI-SPEC acceptance checks and the regression guards.

| Check | Behavior | Test Type | Automated Command | File Exists? |
|-------|----------|-----------|-------------------|-------------|
| Acc 1 | `tsc` + `vite build` green after every plan | build | `npm run build` | Wave 0 (CI job) |
| Acc 2-4, 7, 10 | grep gates: `style={{`, hex in `.tsx`, `text-[N`, bare labels, `font-medium` in `components/ui` | script | `npm run gates` (a `scripts/gates.mjs` or shell grep list) | Wave 0 |
| Acc 8 | brand assets present, none from old VMS | unit | `vitest run src/test/brand.test.ts` | Wave 0 |
| Acc 9 | Contrast table from `tokens.css` | unit | `vitest run src/test/contrast.test.ts` | Wave 0 |
| Acc 11 | Factory reset body is exactly `{ mode: "Soft"\|"Hard", confirmation: "RESET" }` | component | `vitest run src/features/cameras/factory-reset.test.tsx` | Wave 0 |
| Auth table rows 1-12 | `AuthGate` redirects | component | `vitest run src/features/auth/auth-gate.test.tsx` | Wave 0 |
| `next` validation | `//evil`, backslash, `/login`, `/api` rejected | unit | `vitest run src/lib/safe-next.test.ts` | Wave 0 |
| e2e a-e | first run, deep link `next`, open redirect, signed-in `/login`, sign out | e2e | `npx playwright test e2e/auth.spec.ts` | Wave 0 |
| e2e f | Sidebar expanded at 1280/900/768 with cleared storage, rail persists after reload/resize | e2e | `npx playwright test e2e/shell.spec.ts` | Wave 0 |
| Timeline math | window range, pct/date round trips, DST day (23 h / 25 h) | unit | `vitest run src/lib/timeline.test.ts` | Wave 0 |
| LIVE-06 | `vizenlink_nvr_grid_layout_v1` load/save unchanged | unit | `vitest run src/services/grid_storage.test.ts` | Wave 0 |
| Backend unchanged | existing Python suite | integration | `uv run pytest -q` | exists |
| Visual regression (backstop) | light/dark per route at 1440 and 390 | e2e screenshots + human review | `npx playwright test e2e/visual.spec.ts` | Wave 0 |
| Performance (backstop) | 16 mock tiles, no long tasks | e2e | `npx playwright test e2e/perf.spec.ts` | Wave 0 |

### Sampling Rate
- **Per task commit:** `npm run build && npm test`
- **Per wave merge:** full suite above plus `uv run pytest -q`
- **Phase gate:** full suite green, `npm audit --omit=dev --audit-level=high` clean, human visual and live-video checkpoint at end of phase

### Wave 0 Gaps
- [ ] `vite.config.ts` test block, `src/test/setup.ts` (jest-dom, `matchMedia`/`ResizeObserver` stubs)
- [ ] `playwright.config.ts` + `e2e/` and a fresh-data-dir helper
- [ ] Contrast, brand, safe-next, timeline, grid-storage, auth-gate test files
- [ ] `web` job in `.github/workflows/ci.yml` (Node 24, `npm ci`, build, test, gates, audit)
- [ ] `package.json` scripts: `build`, `test`, `gates`, `e2e`

## Security Domain

`security_enforcement` is enabled (ASVS level 1, block on high).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing cookie session; UI adds `new-password`/`current-password` autocomplete, no password prefill (never use the API default `admin123`), lockout copy |
| V3 Session Management | yes | HTTP-only SameSite=Lax cookie unchanged; 401 handler clears the query cache; sign-out always clears local state |
| V4 Access Control | yes | Server `require_role` is authoritative; client hides and shows the 403 state; viewer permissions list drives camera visibility |
| V5 Input Validation | yes | zod mirrors API minimums (password 8); server remains authoritative; `next` redirect validator |
| V6 Cryptography | no | None in the web layer; no secrets in `localStorage` |
| V14 Config / supply chain | yes | Pinned lockfile, `npm ci`, `npm audit --omit=dev`, `shadcn` as devDependency, single lockfile review checkpoint |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Open redirect via `?next=` | Tampering | `safeNext()` allow-list rules from the UI-SPEC; unit + e2e (c) |
| Secrets in query keys, cache, logs or URL | Information disclosure | `gcTime: 0` on password mutations, no `localStorage` writes, never log request bodies |
| XSS via camera names, usernames, event text | Tampering | React escaping only; ban `dangerouslySetInnerHTML` with a grep gate |
| Stale `index.html` served for missing asset or API-like paths | Spoofing/DoS | Pitfall 4 hardening (optional) |
| Third-party registry component | Tampering | UI-SPEC registry-safety gate; only the official shadcn registry is used |
| External network call from the UI (public STUN host) | Information disclosure | Remove `stun.l.google.com` (Pitfall 9) |
| CSRF on cookie auth | Tampering | SameSite=Lax plus JSON bodies; no change in this phase [ASSUMED adequate; unchanged from Phases 2-7] |

## Sources

### Primary (HIGH confidence)
- npm registry via `npm view` (versions, engines, peerDependencies, maintainers) for all packages above, 2026-11-05
- Scratch project builds this session: React 19.3.1 + TS 6.0.3 + Vite 8.3.6 + Tailwind 4.3.4 + react-router 8.5.1 + shadcn 4.23.0 init and add of 38 components + Vitest 5.1.0 run + `npm audit`
- Scratch copy of the unmodified `web/src` compiled under the new stack (only the two TS2367 errors)
- Repo files read this session: `09-CONTEXT.md`, `09-UI-SPEC.md` (all 698 lines), `web/{package.json,tsconfig.json,vite.config.ts,index.html,src/App.tsx}`, `player.ts`, `grid_storage.ts`, `TimelineCanvas.tsx` (1-130 + greps), `SetupWizard.tsx`, `VideoTile.tsx` (1-50), `api/app.py`, `api/v1/auth.py`, `api/v1/cameras.py` (47-84), `api/dependencies.py` (roles), `cli/app.py`, `services/session_manager.py`, `media/config.py`, `media/reconciler.py`, `.github/workflows/ci.yml`, `.gitignore`, `/Users/gokul/mobilecctvapp/lib/theme/app_colors.dart` (values), and the dark logo PNG
- `gh api repos/actions/setup-node/releases/latest` = v7.1.0
- `gsd-tools query package-legitimacy check` (37 packages: 0 SLOP)

### Secondary (MEDIUM confidence)
- Behaviour of `TilePlayer` and `VideoTile` from reading source only; not run against a camera or MediaMTX

### Tertiary (LOW confidence)
- jsdom missing-API list, Intl timezone support, STUN removal impact (all in the Assumptions Log)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, every version, peer range and the init flow were exercised
- Architecture: HIGH for routing/SPA/test design; MEDIUM for Live because of the `/cam` gap
- Pitfalls: HIGH for toolchain items; MEDIUM for player behaviour (static reading)

**Research date:** 2026-11-05
**Valid until:** 2026-11-12 for versions (Vite, TanStack Query, lucide-react and Playwright published within the last 5 days); structure and findings stay valid for about 30 days.
