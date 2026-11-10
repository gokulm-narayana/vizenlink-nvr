# Phase 09 Plan 10 Summary: Playwright E2E Harness & Browser Checks

**Date:** 2026-11-06  
**Commit:** `4a40eef`  
**Phase:** 09-ui-redesign  
**Plan:** 10  
**Wave:** 8  

---

## 1. Overview & Objective
Added the Playwright end-to-end test harness against the real FastAPI backend serving the built SPA on loopback:
- Built `tools/e2e_serve.py` loopback-only launcher that enforces `.e2e` in the data path, wipes and recreates the throwaway directory per run, verifies `runtime.vault` initialization (D-18), and sets `NVR_SECRETS_BACKEND=file`.
- Configured `playwright.config.ts` with two web servers (fresh port 8765, initialized port 8766) and three projects (`first-run`, `setup`, `app`).
- Implemented UI-SPEC e2e test (a) in `first-run.spec.ts` (tagged `@smoke`).
- Implemented global setup in `global.setup.ts` saving owner session state to `.e2e/owner.json`.
- Implemented UI-SPEC e2e tests (b) through (e) in `auth.spec.ts` (deep link round-trip tagged `@smoke`, open-redirect rejection, signed-in `/login` redirect, and sign-out).
- Implemented UI-SPEC e2e test (f) in `shell.spec.ts` testing sidebar default expansion at 1280px (`@smoke`), 900px, 768px on `/` and `/dashboard`; persistence of collapse across reload and viewport resize; and 390px mobile drawer not touching `nvr_sidebar` in `localStorage`.
- Updated `.github/workflows/ci.yml` web job with Playwright Chromium installation, `npm run e2e` with `CI="true"`, and artifact upload (`actions/upload-artifact@v4`) on failure.
- Updated `tests/unit/test_ci_workflow.py` to assert CI steps for Playwright.

---

## 2. Changes Made

### A. E2E Test Server & Infrastructure
- `tools/e2e_serve.py`: loopback test server launcher ensuring data safety (refuses non-`.e2e` paths with code 2, exits code 3 if vault is missing, binds 127.0.0.1).
- `src/vizenlink_nvr/web/playwright.config.ts`: dual web servers and three projects (`first-run`, `setup`, `app`).
- `src/vizenlink_nvr/web/.gitignore`: ignores `.e2e/`, `test-results/`, `playwright-report/`, `blob-report/`.
- `src/vizenlink_nvr/web/package.json`: added `"e2e"`, `"e2e:smoke"`, and `"e2e:run"` scripts.
- `src/vizenlink_nvr/web/tsconfig.json`: included `e2e` and `playwright.config.ts`.

### B. E2E Specs & Auth Flow Fixes
- `src/vizenlink_nvr/web/e2e/fixtures.ts`: test owner credentials and `absRecordingsDir` path resolver.
- `src/vizenlink_nvr/web/e2e/first-run.spec.ts`: verifies setup form submission from a deep link, creating owner account and landing on `/` with heading "Live".
- `src/vizenlink_nvr/web/e2e/global.setup.ts`: sets up owner on port 8766 and caches storage state.
- `src/vizenlink_nvr/web/e2e/auth.spec.ts`: tests (b) deep link `next` round-trip, (c) open-redirect rejection, (d) `/login` redirect when signed in, and (e) sign-out.
- `src/vizenlink_nvr/web/e2e/shell.spec.ts`: tests (f) sidebar expansion defaults at 1280, 900, 768 px, collapse persistence across reload/resize, and drawer below 768 px preserving `nvr_sidebar`.
- `src/vizenlink_nvr/web/src/features/auth/AuthGate.tsx`: preserved `next` parameter redirection upon becoming authenticated (`safeNext(new URLSearchParams(search).get("next")) ?? "/"`).
- `src/vizenlink_nvr/web/src/features/auth/LoginPage.tsx`: synchronized `authStatus` query cache with `loginMutation` result prior to navigation.

### C. CI Integration
- `.github/workflows/ci.yml`: added `npx playwright install --with-deps chromium`, `npm run e2e` (`env.CI: "true"`), and `actions/upload-artifact@v4` on failure for `playwright-report`.
- `tests/unit/test_ci_workflow.py`: added assertions for `playwright install` and `npm run e2e` in web job run steps.

---

## 3. Verification & Test Results

### Ruff Checks on Server Launcher:
```bash
uv run ruff check tools/e2e_serve.py && uv run ruff format --check tools/e2e_serve.py
```
**Output:** All checks passed! 1 file already formatted.

### Playwright E2E Smoke Suite:
```bash
npm --prefix src/vizenlink_nvr/web run e2e:smoke
```
**Output:**
```
Running 4 tests using 1 worker
  ✓  1 [first-run] › first-run.spec.ts:5:3 › First-run setup › first-run setup from a deep link lands on live @smoke (410ms)
  ✓  2 [setup] › e2e/global.setup.ts:9:1 › setup owner account (56ms)
  ✓  3 [app] › e2e/auth.spec.ts:7:3 › Auth routing e2e › deep-link next round trip preserves path and query params @smoke (340ms)
  ✓  4 [app] › e2e/shell.spec.ts:12:5 › Shell sidebar e2e › desktop sidebar is expanded by default at 1280px on / and /dashboard @smoke (235ms)
4 passed (3.5s)
```

### Full Auth and Shell E2E Specs:
```bash
npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/auth.spec.ts e2e/shell.spec.ts
```
**Output:**
```
Running 10 tests using 1 worker
  ✓ 1 [setup] › e2e/global.setup.ts:9:1 › setup owner account (73ms)
  ✓ 2 [app] › e2e/auth.spec.ts:7:3 › Auth routing e2e › deep-link next round trip preserves path and query params @smoke (542ms)
  ✓ 3 [app] › e2e/auth.spec.ts:20:3 › Auth routing e2e › open-redirect attempt is rejected and defaults to / (260ms)
  ✓ 4 [app] › e2e/auth.spec.ts:31:3 › Auth routing e2e › signed-in user visiting /login redirects to / (301ms)
  ✓ 5 [app] › e2e/auth.spec.ts:42:3 › Auth routing e2e › sign out redirects to /login with no next parameter (459ms)
  ✓ 6 [app] › e2e/shell.spec.ts:12:5 › Shell sidebar e2e › desktop sidebar is expanded by default at 1280px on / and /dashboard @smoke (217ms)
  ✓ 7 [app] › e2e/shell.spec.ts:12:5 › Shell sidebar e2e › desktop sidebar is expanded by default at 900px on / and /dashboard (209ms)
  ✓ 8 [app] › e2e/shell.spec.ts:12:5 › Shell sidebar e2e › desktop sidebar is expanded by default at 768px on / and /dashboard (250ms)
  ✓ 9 [app] › e2e/shell.spec.ts:30:3 › Shell sidebar e2e › sidebar collapse persists across reload and viewport resize (281ms)
  ✓ 10 [app] › e2e/shell.spec.ts:54:3 › Shell sidebar e2e › drawer below 768px opens without touching nvr_sidebar (498ms)
10 passed (6.5s)
```

### CI Workflow Unit Tests:
```bash
uv run pytest tests/unit/test_ci_workflow.py -q
```
**Output:**
```
..                                                                       [100%]
2 passed in 0.03s
```

### Web Unit Tests:
```bash
npm --prefix src/vizenlink_nvr/web test
```
**Output:**
```
Test Files  15 passed (15)
Tests       180 passed (180)
Duration    2.41s
```

### Design Gates:
```bash
npm --prefix src/vizenlink_nvr/web run gates
```
**Output:**
```
✅ Design gates passed: scanned 93 non-legacy files with 0 violations.
```

### Typecheck & Production Build:
```bash
npm --prefix src/vizenlink_nvr/web run typecheck && npm --prefix src/vizenlink_nvr/web run build
```
**Output:**
```
dist/index.html                           0.93 kB │ gzip:   0.50 kB
dist/assets/index-Cza0NZf7.css          125.61 kB │ gzip:  19.83 kB
dist/assets/index-Bs7S42Wm.js           846.87 kB │ gzip: 250.27 kB
✓ built in 216ms
```

---

## 4. Next Plan
Wave order execution sequence:
- Next plan: **Plan 09-11** (`.planning/phases/09-ui-redesign/09-11-PLAN.md`) — Live page overhaul.

