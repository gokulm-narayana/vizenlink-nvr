---
phase: "09"
slug: "ui-redesign"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-05"
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `09-RESEARCH.md` "Validation Architecture" and mapped onto the 23 plans (revision 2026-11-05: 09-03 vault plan added, old shell and cameras plans split).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest 5.1.0 + jsdom 30.1.3 + Testing Library (unit and component); Playwright 1.64.1 (e2e against the real FastAPI backend); pytest 9 (Python, existing) |
| **Config file** | None for JS today. 09-04 adds the `test` block in `vite.config.ts` and `src/test/setup.ts`; 09-10 adds `playwright.config.ts` and `tools/e2e_serve.py`. Python uses the existing `pyproject.toml` and `tests/conftest.py` |
| **Quick run command** | `npm --prefix src/vizenlink_nvr/web test` (`vitest run`) |
| **Full suite command** | `npm --prefix src/vizenlink_nvr/web run build && npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run e2e && npm --prefix src/vizenlink_nvr/web audit --omit=dev --audit-level=high && uv run pytest -q` |
| **E2E smoke command** | `npm --prefix src/vizenlink_nvr/web run e2e:smoke` (tests tagged `@smoke`; added by 09-10) |
| **Estimated runtime** | Quick ~30-60 s; targeted Playwright spec runs ~60-120 s; full suite ~6-10 min (Playwright dominates) |

---

## Sampling Rate

- **After every task commit:** the task's own `<automated>` command (targeted Vitest files plus `npm run gates` and `npm run build`; targeted pytest files for the backend tasks in 09-01, 09-02, 09-03 and 09-20).
- **After every plan wave:** `npm --prefix src/vizenlink_nvr/web run build && npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates`, plus `uv run pytest -q`; from wave 8 on, also `npm --prefix src/vizenlink_nvr/web run e2e:smoke`.
- **E2E sampling (W6):** a task that writes Playwright specs runs only those specs (`npm run e2e:run -- <spec files>` after a build) or the smoke subset. The full `npm run e2e` suite runs only in 09-23 Task 3 (final gate) and in CI's `web` job.
- **Before `/gsd-verify-work`:** 09-23 Task 3's one-pass full suite must be green, plus `npm audit --omit=dev --audit-level=high` clean, plus the end-of-phase human visual and live-video checkpoint.
- **Max feedback latency:** 120 s per task (only the Playwright tasks 09-10 T1/T2 and 09-23 T2/T3 exceed 60 s).

---

## Check-to-Test Map

Research mapped no requirement IDs to Phase 9 (the IDs below are regression guards), so the map covers the UI-SPEC acceptance checks, the regression guards and the three approved backend additions.

| Check | Behavior | Test Type | Automated Command | Created By |
|-------|----------|-----------|-------------------|------------|
| Acc 1 | `tsc` + `vite build` green after every plan | build | `npm --prefix src/vizenlink_nvr/web run build` | 09-01 T3 (first green build); CI `web` job 09-04 T3 |
| Acc 2-4, 7, 10 | Grep gates: inline static styles, hex in TSX, off-scale type, bare action labels, `font-medium`/`text-base` in `components/ui` | script | `npm --prefix src/vizenlink_nvr/web run gates` (`scripts/gates.mjs`, self-tested by `scripts/gates.test.mjs`) | 09-04 T2; R0 (no `src/legacy`) in 09-23 T1 |
| Acc 5 | Icon-only buttons carry `aria-label` | script | gate R9 in `npm run gates` | 09-04 T2 |
| Acc 6 | 16 mock tiles, no long tasks over budget, no backdrop blur | e2e | `npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/perf.spec.ts` | 09-23 T2 |
| Acc 8 | Brand assets present; provenance from the mobile app proved by a committed SHA-256 manifest (no old-VMS read) | unit | `npm --prefix src/vizenlink_nvr/web test -- src/test/brand.test.tsx` | 09-05 T3 |
| Acc 9 | Contrast table from `tokens.css`, both themes, plus a negative control | unit | `npm --prefix src/vizenlink_nvr/web test -- src/test/contrast.test.ts` | 09-04 T2 |
| Acc 11 | Factory reset body is exactly `{ mode: "Soft"\|"Hard", confirmation: "RESET" }` | component | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras/factory-reset.test.tsx` | 09-18 T2 |
| Auth table rows 1-12 | `AuthGate` routing, login, setup, session end, sign out | component | `npm --prefix src/vizenlink_nvr/web test -- src/features/auth` | 09-06 T1-T3 |
| `next` validation | `//evil`, backslash, `/login`, `/setup`, `/api` rejected | unit | `npm --prefix src/vizenlink_nvr/web test -- src/lib/safe-next.test.ts` | 09-06 T2 |
| e2e a | First run from a deep link to `/setup` and on to `/` | e2e | `npm --prefix src/vizenlink_nvr/web run e2e:smoke -- --project=first-run` | 09-10 T1 |
| e2e b-e | Deep-link `next`, open redirect, signed-in `/login`, sign out | e2e | `npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/auth.spec.ts` | 09-10 T2 |
| e2e f | Sidebar expanded at 1280/900/768 with cleared storage; collapse persists | e2e | `npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/shell.spec.ts` | 09-10 T2 |
| Shell and registry | Sidebar, role-filtered nav, 403, theme, user menu; every page path, title and minimum role | component | `npm --prefix src/vizenlink_nvr/web test -- src/components/shell src/app` | 09-07 T1-T2, 09-08 T1-T3 |
| Site-zone time | `zonedDayBounds` DST days (23 h / 25 h), zone-independent formatting | unit | `npm --prefix src/vizenlink_nvr/web test -- src/lib/time.test.ts` | 09-09 T3 |
| Timeline math | Window range, pct/time round trip, zoom around cursor, retention span, DST | unit | `npm --prefix src/vizenlink_nvr/web test -- src/lib/timeline.test.ts` | 09-12 T1 |
| LIVE-04, D-17 | Player reconnect backoff, no leak on cleanup during token fetch, no ICE servers | unit | `npm --prefix src/vizenlink_nvr/web test -- src/services/player.test.ts` | 09-11 T1 |
| LIVE-06 | `vizenlink_nvr_grid_layout_v1` load/save unchanged | unit | `npm --prefix src/vizenlink_nvr/web test -- src/services/grid_storage.test.ts` | 09-11 T3 |
| A7 (viewer health) | Viewer reads health of an assigned camera at `/cameras/:serial/health`, 403 otherwise; role-aware health link | component | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras src/components/shell/alerts.test.tsx` | 09-09 T1, 09-18 T1 |
| D-14 `/cam` proxy | Auth (401/403), SSRF-safe path, header allowlist, body cap, 502, route precedence over the SPA fallback | integration | `uv run pytest tests/integration/test_cam_proxy.py -q` | 09-02 T1 |
| D-15 site zone | `site_timezone` null signed out, stored zone signed in, fallback when invalid | integration | `uv run pytest tests/integration/test_auth_site_timezone.py -q` | 09-02 T2 |
| D-18 vault | 503 and nothing written without a runtime vault; `app.state.vault` ignored; production-factory round trip opens with `runtime.vault` and the recorder's `open_vault` | integration | `uv run pytest tests/integration/test_api_cameras_vault.py -q` | 09-03 T1-T2 |
| OpenAPI guard | No breaking change; baseline only gains `site_timezone` | contract | `uv run pytest tests/contract/test_openapi_spec.py -q` | existing; re-run in 09-02, 09-03 |
| Bundle served | FastAPI serves the built SPA, hashed assets non-HTML, deep link fallback, API 404 JSON | integration | `uv run pytest tests/integration/test_web_bundle_served.py -q` | 09-01 T3 |
| CI guard | `web` job present on Node 24 with build, test, gates, audit, e2e | unit | `uv run pytest tests/unit/test_ci_workflow.py -q` | 09-04 T3, 09-10 T3 |
| Backend scope | Backend diff limited to the 09-02 and 09-03 files; existing Python suite green | integration + diff | `uv run pytest -q` plus the 09-23 T3 `git diff --stat` scope check | 09-23 T3 |
| Visual backstop | Every route, light and dark, 1440 and 390 px, no horizontal scroll, no console errors | e2e + human review | `npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/visual.spec.ts` | 09-23 T2 |

---

## Per-Task Verification Map

Generated from the `<automated>` block of every task in `09-01` to `09-23`. "W0 (in-plan)" means the test file or script is created by that plan before or within the task (Wave 0 infrastructure is listed below). "Human" marks tasks that also carry a `<human-check>` or a blocking-human checkpoint.

| Task ID | Plan | Wave | Requirement | Threat Ref | Type | Automated Command | File Exists | Human | Status |
|---------|------|------|-------------|------------|------|-------------------|-------------|-------|--------|
| 09-01-01 | 01 | 1 | SET-01, MOB-03 | T-09-01, T-09-02, T-09-SC | auto | `cd src/vizenlink_nvr/web && node -e "const l=require('./package-lock.json');const p=l.packages;const need={'node_modules/react':'19.','node_modules/typescript':'6.0.','node_modules/vite':'8.','node_modules/tailwindcss':'4.','node_modules/react-router':'8.','node_modules/shadcn':'4.23.0','node_modules/uqr':'0.1.','node_modules/vitest':'5.'};for(const[k,v]of Object.entries(need)){if(!p[k]\|\|!p[k].version.startsWith(v)){console.error('bad',k,p[k]&&p[k].version);process.exit(1)}}if(!(p[''].devDependencies\|\|{}).shadcn){console.error('shadcn must be a devDependency');process.exit(1)}console.log('lockfile ok')"` | W0 (in-plan) |  | ⬜ pending |
| 09-01-02 | 01 | 1 | SET-01, MOB-03 | T-09-01, T-09-02, T-09-SC | human gate | blocking-human checkpoint | n/a | yes | ⬜ pending |
| 09-01-03 | 01 | 1 | SET-01, MOB-03 | T-09-01, T-09-02, T-09-SC | tracer | `npm --prefix src/vizenlink_nvr/web run build && uv run pytest tests/integration/test_web_bundle_served.py -q` | W0 (in-plan) |  | ⬜ pending |
| 09-02-01 | 02 | 1 | LIVE-01, AUTH-01, MOB-01 | T-09-60, T-09-03, T-09-04, T-09-05, T-09-06, T-09-07 | tracer | `uv run pytest tests/integration/test_cam_proxy.py -q && uv run ruff check src/vizenlink_nvr/api/cam_proxy.py tests/integration/test_cam_proxy.py && uv run mypy src/vizenlink_nvr/api/cam_proxy.py && uv run pytest tests/contract/test_openapi_spec.py -q` | W0 (in-plan) |  | ⬜ pending |
| 09-02-02 | 02 | 1 | LIVE-01, AUTH-01, MOB-01 | T-09-60, T-09-03, T-09-04, T-09-05, T-09-06, T-09-07 | auto | `uv run pytest tests/integration/test_auth_site_timezone.py tests/integration/test_auth_setup_wizard.py tests/contract/test_openapi_spec.py -q && uv run mypy src/vizenlink_nvr/services/settings.py src/vizenlink_nvr/api/v1/auth.py` | W0 (in-plan) |  | ⬜ pending |
| 09-02-03 | 02 | 1 | LIVE-01, AUTH-01, MOB-01 | T-09-60, T-09-03, T-09-04, T-09-05, T-09-06, T-09-07 | auto | `grep -q "revision: 5" .planning/phases/09-ui-redesign/09-UI-SPEC.md && grep -q "allow_system_disk" .planning/phases/09-ui-redesign/09-UI-SPEC.md && grep -q "site_timezone" .planning/phases/09-ui-redesign/09-UI-SPEC.md && grep -q "Revision 5 amendments" .planning/phases/09-ui-redesign/09-UI-SPEC.md && grep -q "/cameras/:serial/health" .planning/phases/09-ui-redesign/09-UI-SPEC.md && grep -q "View camera health" .planning/phases/09-ui-redesign/09-UI-SPEC.md && grep -q "store camera passwords securely" .planning/phases/09-ui-redesign/09-UI-SPEC.md` | W0 (in-plan) |  | ⬜ pending |
| 09-03-01 | 03 | 1 | CAM-03, CAM-06 | T-09-61, T-09-52, T-09-53, T-09-54 | tracer | `uv run pytest tests/integration/test_api_cameras_vault.py -q && uv run mypy src/vizenlink_nvr/services/runtime.py && uv run ruff check src/vizenlink_nvr/services/runtime.py tests/integration/test_api_cameras_vault.py` | W0 (in-plan) |  | ⬜ pending |
| 09-03-02 | 03 | 1 | CAM-03, CAM-06 | T-09-61, T-09-52, T-09-53, T-09-54 | auto | `uv run pytest tests/integration/test_api_cameras_vault.py tests/integration/test_api_cameras.py tests/integration/test_phase3_tracer.py tests/integration/test_camera_settings_api.py tests/contract/test_openapi_spec.py -q && uv run mypy src/vizenlink_nvr/api/v1/cameras.py && uv run ruff check src/vizenlink_nvr/api/v1/cameras.py tests/integration/test_api_cameras_vault.py tests/integration/test_api_cameras.py tests/integration/test_phase3_tracer.py` | W0 (in-plan) |  | ⬜ pending |
| 09-04-01 | 04 | 2 | HLTH-01, HLTH-05 | T-09-08, T-09-09 | tracer | `npm --prefix src/vizenlink_nvr/web run build && grep -q -- "--primary-text:" src/vizenlink_nvr/web/dist/assets/*.css && grep -q "\.dark" src/vizenlink_nvr/web/dist/assets/*.css && grep -q "nvr_theme" src/vizenlink_nvr/web/dist/index.html` | W0 (in-plan) | yes | ⬜ pending |
| 09-04-02 | 04 | 2 | HLTH-01, HLTH-05 | T-09-08, T-09-09 | auto | `npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && { git diff --quiet -- src/vizenlink_nvr/web/src/legacy/Header.tsx \|\| test -s .planning/phases/09-ui-redesign/owner-Header.tsx.patch; }` | W0 (in-plan) |  | ⬜ pending |
| 09-04-03 | 04 | 2 | HLTH-01, HLTH-05 | T-09-08, T-09-09 | auto | `uv run pytest tests/unit/test_ci_workflow.py -q && uv run python -c "import yaml,sys;d=yaml.safe_load(open('.github/workflows/ci.yml'));sys.exit(0 if 'web' in d['jobs'] and 'test' in d['jobs'] else 1)"` | exists |  | ⬜ pending |
| 09-05-01 | 05 | 3 | AUTH-01, AUTH-06 | T-09-10, T-09-11, T-09-59, T-09-SC | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/test/ui-overrides.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && git diff --quiet HEAD -- src/vizenlink_nvr/web/package-lock.json src/vizenlink_nvr/web/package.json src/vizenlink_nvr/web/tsconfig.json src/vizenlink_nvr/web/vite.config.ts src/vizenlink_nvr/web/index.html src/vizenlink_nvr/web/src/main.tsx && test ! -e src/vizenlink_nvr/web/src/index.css` | W0 (in-plan) |  | ⬜ pending |
| 09-05-02 | 05 | 3 | AUTH-01, AUTH-06 | T-09-10, T-09-11, T-09-59, T-09-SC | auto | `npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && git diff --quiet HEAD -- src/vizenlink_nvr/web/package-lock.json src/vizenlink_nvr/web/package.json src/vizenlink_nvr/web/tsconfig.json src/vizenlink_nvr/web/vite.config.ts src/vizenlink_nvr/web/index.html src/vizenlink_nvr/web/src/main.tsx && test ! -e src/vizenlink_nvr/web/src/index.css` | W0 (in-plan) |  | ⬜ pending |
| 09-05-03 | 05 | 3 | AUTH-01, AUTH-06 | T-09-10, T-09-11, T-09-59, T-09-SC | auto | `uv run ruff check tools/crop_brand.py && uv run ruff format --check tools/crop_brand.py && NVR_MOBILE_BRANDING_DIR=/Users/gokul/mobilecctvapp/assets/branding npm --prefix src/vizenlink_nvr/web test -- src/test/brand.test.tsx && npm --prefix src/vizenlink_nvr/web run build && ! grep -rnF "vizenlinkvms" src/vizenlink_nvr/web/src tools/crop_brand.py` | W0 (in-plan) | yes | ⬜ pending |
| 09-06-01 | 06 | 4 | AUTH-01, AUTH-02 | T-09-12, T-09-13, T-09-14 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/auth/auth-gate.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-06-02 | 06 | 4 | AUTH-01, AUTH-02 | T-09-12, T-09-13, T-09-14 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/lib/safe-next.test.ts src/features/auth && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-06-03 | 06 | 4 | AUTH-01, AUTH-02 | T-09-12, T-09-13, T-09-14 | auto | `npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-07-01 | 07 | 5 | AUTH-06, AUTH-03 | T-09-15, T-09-16, T-09-17 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/components/shell && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-07-02 | 07 | 5 | AUTH-06, AUTH-03 | T-09-15, T-09-16, T-09-17 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/components/shell && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-08-01 | 08 | 6 | AUTH-03, SET-01, MOB-03 | T-09-62, T-09-55, T-09-56 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/app src/components/shell && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-08-02 | 08 | 6 | AUTH-03, SET-01, MOB-03 | T-09-62, T-09-55, T-09-56 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/app src/components/shell && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-08-03 | 08 | 6 | AUTH-03, SET-01, MOB-03 | T-09-62, T-09-55, T-09-56 | auto | `npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/LegacyApp.tsx && test ! -e src/vizenlink_nvr/web/src/legacy/Header.tsx` | W0 (in-plan) | yes | ⬜ pending |
| 09-09-01 | 09 | 7 | HLTH-07, HLTH-06, EVT-05 | T-09-18, T-09-19 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/components/shell/alerts.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-09-02 | 09 | 7 | HLTH-07, HLTH-06, EVT-05 | T-09-18, T-09-19 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/components/shell/status.test.tsx && npm --prefix src/vizenlink_nvr/web run typecheck && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-09-03 | 09 | 7 | HLTH-07, HLTH-06, EVT-05 | T-09-18, T-09-19 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/lib/time.test.ts src/components/shell/shortcuts.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-10-01 | 10 | 8 | AUTH-01, AUTH-02, AUTH-06 | T-09-20, T-09-21, T-09-SC | tracer | `uv run ruff check tools/e2e_serve.py && uv run ruff format --check tools/e2e_serve.py && npm --prefix src/vizenlink_nvr/web run e2e:smoke -- --project=first-run` | W0 (in-plan) |  | ⬜ pending |
| 09-10-02 | 10 | 8 | AUTH-01, AUTH-02, AUTH-06 | T-09-20, T-09-21, T-09-SC | auto | `npm --prefix src/vizenlink_nvr/web run build && npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/auth.spec.ts e2e/shell.spec.ts` | W0 (in-plan) |  | ⬜ pending |
| 09-10-03 | 10 | 8 | AUTH-01, AUTH-02, AUTH-06 | T-09-20, T-09-21, T-09-SC | auto | `uv run pytest tests/unit/test_ci_workflow.py -q` | exists |  | ⬜ pending |
| 09-11-01 | 11 | 8 | LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06 | T-09-22, T-09-23, T-09-24 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/services/player.test.ts && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-11-02 | 11 | 8 | LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06 | T-09-22, T-09-23, T-09-24 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/live && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-11-03 | 11 | 8 | LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06 | T-09-22, T-09-23, T-09-24 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/services/grid_storage.test.ts` | W0 (in-plan) |  | ⬜ pending |
| 09-12-01 | 12 | 8 | PLAY-01, PLAY-04, PLAY-08 | T-09-25, T-09-26 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/lib/timeline.test.ts src/features/playback/timeline && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-12-02 | 12 | 8 | PLAY-01, PLAY-04, PLAY-08 | T-09-25, T-09-26 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/playback/timeline && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-13-01 | 13 | 9 | PLAY-02, PLAY-03, PLAY-04, PLAY-05, PLAY-06, PLAY-07 | T-09-27, T-09-28 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/playback/playback.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-13-02 | 13 | 9 | PLAY-02, PLAY-03, PLAY-04, PLAY-05, PLAY-06, PLAY-07 | T-09-27, T-09-28 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/playback && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-13-03 | 13 | 9 | PLAY-02, PLAY-03, PLAY-04, PLAY-05, PLAY-06, PLAY-07 | T-09-27, T-09-28 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/playback && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/PlaybackView.tsx` | W0 (in-plan) | yes | ⬜ pending |
| 09-14-01 | 14 | 8 | EVT-02, EVT-03, EVT-05, EVT-07, PLAY-05 | T-09-29, T-09-30 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/events && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-14-02 | 14 | 8 | EVT-02, EVT-03, EVT-05, EVT-07, PLAY-05 | T-09-29, T-09-30 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/events && npm --prefix src/vizenlink_nvr/web run gates` | W0 (in-plan) |  | ⬜ pending |
| 09-14-03 | 14 | 8 | EVT-02, EVT-03, EVT-05, EVT-07, PLAY-05 | T-09-29, T-09-30 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/events && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/EventFeed.tsx` | W0 (in-plan) | yes | ⬜ pending |
| 09-15-01 | 15 | 8 | GAL-01, GAL-02 | T-09-31, T-09-32 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/gallery && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-15-02 | 15 | 8 | GAL-01, GAL-02 | T-09-31, T-09-32 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/gallery && npm --prefix src/vizenlink_nvr/web run gates` | W0 (in-plan) |  | ⬜ pending |
| 09-15-03 | 15 | 8 | GAL-01, GAL-02 | T-09-31, T-09-32 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/gallery && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/GalleryView.tsx` | W0 (in-plan) | yes | ⬜ pending |
| 09-16-01 | 16 | 8 | HLTH-01, HLTH-02, HLTH-04, HLTH-05, HLTH-06, HLTH-08, AUTH-06 | T-09-33, T-09-34 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/dashboard && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-16-02 | 16 | 8 | HLTH-01, HLTH-02, HLTH-04, HLTH-05, HLTH-06, HLTH-08, AUTH-06 | T-09-33, T-09-34 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/dashboard && npm --prefix src/vizenlink_nvr/web run gates` | W0 (in-plan) |  | ⬜ pending |
| 09-16-03 | 16 | 8 | HLTH-01, HLTH-02, HLTH-04, HLTH-05, HLTH-06, HLTH-08, AUTH-06 | T-09-33, T-09-34 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/dashboard && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/Dashboard.tsx` | W0 (in-plan) | yes | ⬜ pending |
| 09-17-01 | 17 | 8 | SET-01, SET-02, SET-03, SET-04, SET-08, AUTH-06 | T-09-36, T-09-57 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras/cameras.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-17-02 | 17 | 8 | SET-01, SET-02, SET-03, SET-04, SET-08, AUTH-06 | T-09-36, T-09-57 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-18-01 | 18 | 9 | SET-05, SET-06, SET-07, HLTH-09, AUTH-06 | T-09-35, T-09-37, T-09-58 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-18-02 | 18 | 9 | SET-05, SET-06, SET-07, HLTH-09, AUTH-06 | T-09-35, T-09-37, T-09-58 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/CameraSettingsView.tsx && test ! -e src/vizenlink_nvr/web/src/features/cameras/tabs/LegacyBridgeTab.tsx` | W0 (in-plan) | yes | ⬜ pending |
| 09-19-01 | 19 | 8 | MOB-03 | T-09-38, T-09-39, T-09-40 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/devices && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-19-02 | 19 | 8 | MOB-03 | T-09-38, T-09-39, T-09-40 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/devices && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && test ! -e src/vizenlink_nvr/web/src/legacy/MobilePairingModal.tsx` | W0 (in-plan) |  | ⬜ pending |
| 09-20-01 | 20 | 9 | AUTH-03, LIVE-01, CAM-02, CAM-03 | T-09-41, T-09-42, T-09-43, T-09-44 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras/add && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-20-02 | 20 | 9 | AUTH-03, LIVE-01, CAM-02, CAM-03 | T-09-41, T-09-42, T-09-43, T-09-44 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras/add && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-20-03 | 20 | 9 | AUTH-03, LIVE-01, CAM-02, CAM-03 | T-09-41, T-09-42, T-09-43, T-09-44 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/cameras/add && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && uv run pytest tests/integration/test_api_cameras_create_streams.py tests/integration/test_api_cameras_vault.py -q` | W0 (in-plan) | yes | ⬜ pending |
| 09-21-01 | 21 | 8 | AUTH-02, AUTH-06 | T-09-45, T-09-46 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/profile src/components/shell && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-21-02 | 21 | 8 | AUTH-02, AUTH-06 | T-09-45, T-09-46 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/profile && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-22-01 | 22 | 9 | AUTH-04, AUTH-05, AUTH-03 | T-09-47, T-09-48, T-09-49 | tracer | `npm --prefix src/vizenlink_nvr/web test -- src/features/users && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-22-02 | 22 | 9 | AUTH-04, AUTH-05, AUTH-03 | T-09-47, T-09-48, T-09-49 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/users && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) |  | ⬜ pending |
| 09-22-03 | 22 | 9 | AUTH-04, AUTH-05, AUTH-03 | T-09-47, T-09-48, T-09-49 | auto | `npm --prefix src/vizenlink_nvr/web test -- src/features/users && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build` | W0 (in-plan) | yes | ⬜ pending |
| 09-23-01 | 23 | 10 | LIVE-02, PLAY-01, HLTH-02, GAL-01, AUTH-06 | T-09-50, T-09-51 | tracer | `test ! -e src/vizenlink_nvr/web/src/legacy && npm --prefix src/vizenlink_nvr/web run build && npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates` | W0 (in-plan) |  | ⬜ pending |
| 09-23-02 | 23 | 10 | LIVE-02, PLAY-01, HLTH-02, GAL-01, AUTH-06 | T-09-50, T-09-51 | auto | `npm --prefix src/vizenlink_nvr/web run build && npm --prefix src/vizenlink_nvr/web run e2e:run -- e2e/visual.spec.ts e2e/perf.spec.ts` | W0 (in-plan) |  | ⬜ pending |
| 09-23-03 | 23 | 10 | LIVE-02, PLAY-01, HLTH-02, GAL-01, AUTH-06 | T-09-50, T-09-51 | auto | `npm --prefix src/vizenlink_nvr/web run build && npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run e2e && npm --prefix src/vizenlink_nvr/web audit --omit=dev --audit-level=high && uv run pytest -q` | W0 (in-plan) | yes | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test infrastructure that does not exist today, and the plan that creates it before anything depends on it:

- [ ] `src/vizenlink_nvr/web/vite.config.ts` `test` block and `src/test/setup.ts` (jest-dom, `matchMedia`, `ResizeObserver`, pointer-capture and media stubs) — 09-04 T2
- [ ] `package.json` scripts `test`, `test:watch`, `gates`, `typecheck` — 09-04 T2; `e2e`, `e2e:smoke`, `e2e:run` — 09-10 T1
- [ ] `scripts/gates.mjs` + `scripts/gates.test.mjs` (R1-R10; R0 added in 09-23 T1) — 09-04 T2
- [ ] `src/test/contrast.test.ts` — 09-04 T2
- [ ] `.github/workflows/ci.yml` `web` job (Node 24, `npm ci`, build, test, gates, audit, bundle pytest) — 09-04 T3; Playwright in CI — 09-10 T3
- [ ] `src/test/ui-overrides.test.tsx` — 09-05 T1-T2; `src/test/brand.test.tsx` + `src/assets/brand/provenance.json` — 09-05 T3
- [ ] `src/features/auth/auth-gate.test.tsx`, `src/lib/safe-next.test.ts`, `login.test.tsx`, `setup.test.tsx` — 09-06
- [ ] `src/components/shell/shell.test.tsx`, `user-menu.test.tsx` — 09-07; `src/app/routes.test.tsx` — 09-08
- [ ] `src/lib/time.test.ts` and the shell status/alerts/shortcuts tests — 09-09
- [ ] `playwright.config.ts`, `tools/e2e_serve.py` (runtime-backed, loopback only), `e2e/fixtures.ts`, `e2e/global.setup.ts`, `e2e/first-run.spec.ts`, `e2e/auth.spec.ts`, `e2e/shell.spec.ts` — 09-10
- [ ] `src/services/player.test.ts`, `src/services/grid_storage.test.ts` — 09-11
- [ ] `src/lib/timeline.test.ts` — 09-12
- [ ] `tests/integration/test_web_bundle_served.py` — 09-01 T3; `test_cam_proxy.py`, `test_auth_site_timezone.py` — 09-02; `test_api_cameras_vault.py` — 09-03; `test_api_cameras_create_streams.py` — 09-20
- [ ] `e2e/visual.spec.ts`, `e2e/perf.spec.ts` — 09-23 T2

Existing infrastructure reused unchanged: pytest, `tests/conftest.py` (`NVR_SECRETS_BACKEND=file`), `tests/contract/test_openapi_spec.py`, `tools/check_api_breaking_changes.py`, `tests/unit/test_ci_workflow.py` (extended, not replaced).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dependency set approval before install | T-09-SC | Package legitimacy is an owner judgment | 09-01 Task 2 blocking-human checkpoint |
| No theme flash on first paint; legacy pages usable after Tailwind preflight | D-06 | Visual | 09-04 Task 1 human-check |
| Logo legibility on all four grounds | D-03 | Visual | 09-05 Task 3 human-check |
| Login/Setup visual conformance at 390 px, both themes | AUTH-01 | Visual | 09-06 Task 3 human-check |
| Sidebar, theme switch and legacy app at the shell split | D-07, D-12 | Visual | 09-07 Task 2 and 09-08 Task 3 human-checks |
| Live video through `/cam`, outage recovery, no peer-connection growth | LIVE-01, LIVE-04 | Needs a real camera, MediaMTX and browser WebRTC | 09-11 Task 1 and Task 2 human-checks |
| Timeline encodings, gestures and screen-reader output | PLAY-01, PLAY-08 | Perceptual and assistive-tech checks | 09-12 Task 2 human-check |
| Camera settings parity with the mobile app; reboot and reset on hardware; viewer health route | SET-01..07 | Real camera behaviour and destructive flows | 09-17 Task 2 and 09-18 Task 2 human-checks |
| Web-added camera records; fail-closed vault path is visible | CAM-02, CAM-03, D-18 | Real recorder and hardware | 09-20 Task 3 human-check |
| Final visual sign-off and 10-minute real-hardware session | All | Human judgment | 09-23 Task 3 human-check (end-of-phase checkpoint) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the only non-automated task is the 09-01 blocking-human package checkpoint)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (each test file is created in the plan that first runs it)
- [x] No watch-mode flags (`vitest run`, `playwright test`; `test:watch` is never used in a verify)
- [ ] Feedback latency < 120 s (to confirm on first execution; Playwright tasks are the risk)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
