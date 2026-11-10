# Phase 09 Plan 04 Summary: Design-Token Foundation, Vitest Harness, Design Gates, Legacy UI Isolation, and Web CI Job

## 1. What Was Built
- **Design Tokens & Tailwind v4 Integration (`src/styles/tokens.css` & `src/styles/globals.css`):**
  - Populated all light and dark theme semantic color tokens according to UI-SPEC Color table (`#5B6EF5` dark indigo, `#4656E8` light AA shade, status hues, surface grounds, and video overlay tokens).
  - Defined `@theme inline` mapping variables, plain `@theme` scale (`text-xs`, `text-sm`, `text-xl`, `text-display`, `font-normal`, `font-semibold`, Inter font family).
  - Configured `:focus-visible` (2px solid `var(--ring)`, 4px offset), base layer borders, and `prefers-reduced-motion` reduction.
  - Implemented pre-paint theme initializer script in `index.html` resolving `localStorage.nvr_theme` and system preference before stylesheet evaluation.
- **Owner's Header.tsx Patch & Legacy UI Isolation (`src/legacy/`):**
  - Saved owner's uncommitted `Header.tsx` diff to `.planning/phases/09-ui-redesign/owner-Header.tsx.patch` and committed it as `docs(09-04): save owner's uncommitted Header.tsx diff before the legacy move` (`f77186d`).
  - Moved legacy UI components and `App.tsx` to `src/legacy/` (`LegacyApp.tsx`), updated imports to `./X`, and verified `git diff -- src/vizenlink_nvr/web/src/legacy/Header.tsx` preserves the owner's uncommitted diff unstaged.
- **Vitest & Quality Harness (`src/test/setup.ts`, `src/test/contrast.test.ts`, `scripts/gates.mjs`, `scripts/gates.test.mjs`):**
  - Configured jsdom test environment with stubs for `matchMedia`, `ResizeObserver`, `IntersectionObserver`, pointer capture, media play/pause, and object URLs.
  - Built WCAG 2.2 contrast suite asserting all UI-SPEC pairings within 0.1 of listed ratios, meeting 4.5:1 (text) and 3.0:1 (non-text), worst-case video overlay compositing, and a negative control on decorative border.
  - Implemented design gates R1..R10 via `scripts/gates.mjs` with unit tests in `scripts/gates.test.mjs`. Note: `src/components/ui/` internals are explicitly exempt from R10 (spacing steps).
- **CI Web Workflow (`.github/workflows/ci.yml` & `tests/unit/test_ci_workflow.py`):**
  - Added `web` job on Ubuntu with Node 24 (`24.x` with >= 24.15 check), running `npm ci`, `npm run build`, `npm test`, `npm run gates`, `npm audit --omit=dev --audit-level=high`, and `test_web_bundle_served.py`.
  - Added unit test `test_ci_web_job()` verifying all required job parameters and steps.

## 2. Verification Commands & Outputs

### Task 1 Verification
```bash
npm --prefix src/vizenlink_nvr/web run build && grep -q -- "--primary-text:" src/vizenlink_nvr/web/dist/assets/*.css && grep -q "\.dark" src/vizenlink_nvr/web/dist/assets/*.css && grep -q "nvr_theme" src/vizenlink_nvr/web/dist/index.html
```
- **Exit Code:** 0
- **Output:** Built dist bundle with tokens and pre-paint theme script.

### Task 2 Verification
```bash
npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && { git diff --quiet -- src/vizenlink_nvr/web/src/legacy/Header.tsx || test -s .planning/phases/09-ui-redesign/owner-Header.tsx.patch; }
```
- **Exit Code:** 0
- **Output:**
  - Vitest: 92 passed (81 contrast tests + 11 gate tests)
  - Gates: 0 violations across 6 non-legacy files
  - Build: green

### Task 3 Verification
```bash
uv run pytest tests/unit/test_ci_workflow.py -q && uv run python -c "import yaml,sys;d=yaml.safe_load(open('.github/workflows/ci.yml'));sys.exit(0 if 'web' in d['jobs'] and 'test' in d['jobs'] else 1)"
```
- **Exit Code:** 0
- **Output:** 2 passed in 0.03s.

## 3. Deviations from Plan
- None. `tsconfig.json` compiler options were augmented with `"types": ["node"]` so TypeScript compiler recognizes `node:fs` and `node:path` in test files while keeping `"paths": { "@/*": ["./src/*"] }` and no `baseUrl`.

## 4. Commits
- `f77186d` docs(09-04): save owner's uncommitted Header.tsx diff before the legacy move
- `4b2c3fa` feat(09-04): vitest harness, contrast test, design gates, legacy UI isolated
- `d244489` ci(09-04): add web build, test, gates and audit job on Node 24

