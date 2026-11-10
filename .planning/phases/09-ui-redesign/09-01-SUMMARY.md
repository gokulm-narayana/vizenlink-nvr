# Plan 09-01 Summary: Dependency Approval Gate & Stack Bump (React 19, Vite 8, TypeScript 6)

## What was built
- Updated `src/vizenlink_nvr/web/package.json` to include the complete dependency manifest for Phase 9, with `shadcn` in `devDependencies` and `"engines": { "node": ">=24.15.0" }`.
- Resolved `package-lock.json` with `npm install --package-lock-only --ignore-scripts` and verified zero production vulnerabilities via `npm audit --omit=dev --package-lock-only`.
- Stopped at Task 2 blocking-human checkpoint; received explicit owner approval to install the exact lockfile and retain `uqr`.
- Ran `npm ci` installing the approved tree cleanly.
- Added `src/vizenlink_nvr/web/src/vite-env.d.ts` with triple-slash reference to `vite/client` types.
- Fixed TS2367 errors in `src/vizenlink_nvr/web/src/App.tsx` by declaring `type AppTab = ViewTab | "settings" | "devices"` and casting `<Header currentTab={currentTab as ViewTab} />`, without modifying the owner's uncommitted `Header.tsx`.
- Created `tests/integration/test_web_bundle_served.py` asserting that FastAPI serves `/`, all hashed `/assets/...` with non-HTML content types, deep-link SPA fallback, and `/api/v1/...` 404 JSON.
- Committed via private index (`cbcf623`): exactly 5 files, leaving owner's unstaged edits intact.

## Approved Direct Dependencies

| Package | Resolved Version | Type |
|---|---|---|
| `react` | `19.3.1` | dependency |
| `react-dom` | `19.3.1` | dependency |
| `react-router` | `8.5.1` | dependency |
| `@tanstack/react-query` | `5.106.1` | dependency |
| `zustand` | `5.0.16` | dependency |
| `lucide-react` | `1.70.0` | dependency |
| `react-hook-form` | `7.91.0` | dependency |
| `@hookform/resolvers` | `7.0.3` | dependency |
| `zod` | `4.6.7` | dependency |
| `radix-ui` | `1.8.1` | dependency |
| `class-variance-authority` | `0.7.1` | dependency |
| `cn` | `0.5.2` | dependency |
| `tw-animate-css` | `1.4.0` | dependency |
| `sonner` | `2.0.8` | dependency |
| `react-day-picker` | `10.0.2` | dependency |
| `date-fns` | `4.4.0` | dependency |
| `@fontsource-variable/inter` | `5.3.0` | dependency |
| `uqr` | `0.1.3` | dependency |
| `typescript` | `6.0.3` | devDependency |
| `vite` | `8.3.6` | devDependency |
| `@vitejs/plugin-react` | `6.2.1` | devDependency |
| `tailwindcss` | `4.3.4` | devDependency |
| `@tailwindcss/vite` | `4.3.4` | devDependency |
| `shadcn` | `4.23.0` | devDependency |
| `vitest` | `5.1.0` | devDependency |
| `jsdom` | `30.1.3` | devDependency |
| `@testing-library/react` | `16.3.3` | devDependency |
| `@testing-library/dom` | `10.4.2` | devDependency |
| `@testing-library/jest-dom` | `7.0.1` | devDependency |
| `@testing-library/user-event` | `14.6.8` | devDependency |
| `@playwright/test` | `1.65.0` | devDependency |
| `@types/node` | `24.19.2` | devDependency |
| `@types/react` | `19.3.0` | devDependency |
| `@types/react-dom` | `19.3.0` | devDependency |

## Automated Verification Commands Run & Real Output

1. **Lockfile validation:**
   ```bash
   cd src/vizenlink_nvr/web && node -e "const l=require('./package-lock.json');const p=l.packages;const need={'node_modules/react':'19.','node_modules/typescript':'6.0.','node_modules/vite':'8.','node_modules/tailwindcss':'4.','node_modules/react-router':'8.','node_modules/shadcn':'4.23.0','node_modules/uqr':'0.1.','node_modules/vitest':'5.'};for(const[k,v]of Object.entries(need)){if(!p[k]||!p[k].version.startsWith(v)){console.error('bad',k,p[k]&&p[k].version);process.exit(1)}}if(!(p[''].devDependencies||{}).shadcn){console.error('shadcn must be a devDependency');process.exit(1)}console.log('lockfile ok')"
   # Output: lockfile ok (PASS)
   ```

2. **Production security audit:**
   ```bash
   npm --prefix src/vizenlink_nvr/web audit --omit=dev --package-lock-only
   # Output: found 0 vulnerabilities (PASS)
   ```

3. **Web build:**
   ```bash
   npm --prefix src/vizenlink_nvr/web run build
   # Output:
   # vite v8.3.6 building client environment for production...
   # ✓ 37 modules transformed.
   # dist/index.html                  0.50 kB │ gzip:  0.36 kB
   # dist/assets/index-CPbRgggU.js  335.80 kB │ gzip: 93.05 kB
   # ✓ built in 64ms (PASS)
   ```

4. **Integration test:**
   ```bash
   uv run pytest tests/integration/test_web_bundle_served.py -q
   # Output: 1 passed in 0.63s (PASS)
   ```

5. **Commit check:**
   ```bash
   git show --name-only --format= HEAD
   # Output:
   # src/vizenlink_nvr/web/package-lock.json
   # src/vizenlink_nvr/web/package.json
   # src/vizenlink_nvr/web/src/App.tsx
   # src/vizenlink_nvr/web/src/vite-env.d.ts
   # tests/integration/test_web_bundle_served.py
   ```

## Deviations from plan
None. Exact instructions followed.

## Follow-ups
Proceed to Plan 09-02 (Backend: /cam proxy and site_timezone on auth status).

