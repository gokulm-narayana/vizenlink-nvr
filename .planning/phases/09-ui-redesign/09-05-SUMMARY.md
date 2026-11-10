# Phase 09 Plan 05 Summary: shadcn/ui Component Set, UI-SPEC Contract Overrides, Inter Font, and VizenLink Brand Assets

## 1. What Was Built
- **shadcn/ui Configuration & Component Set (`components.json`, `src/components/ui/*`):**
  - Initialized `shadcn@4.23.0` non-interactively with `-p nova`, mapped to `src/styles/globals.css`, neutral base, Lucide icons, `@/` aliases.
  - Added full planned inventory: `sidebar`, `button-group`, `toggle-group`, `toggle`, `tabs`, `card`, `badge`, `alert`, `alert-dialog`, `dialog`, `sheet`, `popover`, `calendar`, `select`, `native-select`, `input`, `input-group`, `label`, `field`, `switch`, `slider`, `checkbox`, `radio-group`, `table`, `progress`, `skeleton`, `spinner`, `empty`, `tooltip`, `dropdown-menu`, `avatar`, `scroll-area`, `separator`, `sonner`, `kbd`, `pagination`, `collapsible`.
  - Re-exported `{ cn } from "cn"` in `src/lib/utils.ts`.
- **UI-SPEC Contract Overrides Applied:**
  - `button.tsx`: `font-semibold`, 36px default height (`h-9`), 6px radius (`rounded-md`), `bg-primary text-primary-foreground hover:bg-primary-hover`, `pointer-coarse:min-h-11 pointer-coarse:min-w-11`.
  - `alert-dialog.tsx`, `dialog.tsx`, `sheet.tsx`: removed all `backdrop-blur` utilities, solid scrims (`bg-black/60`), titles `text-xl font-semibold`, close buttons accessible with labels, no bare Cancel/Close labels.
  - `card.tsx`: 1px border with `rounded-lg`, no shadow, `CardTitle` is `text-sm font-semibold`.
  - `badge.tsx`: `rounded-full`, `font-semibold`, secondary variant uses `bg-secondary text-foreground`.
  - `input.tsx`, `native-select.tsx`, `select.tsx`, `textarea.tsx`: fixed to `text-sm` (no `text-base` or `md:text-sm`), 36px control height (`h-9`), `rounded-md`.
  - `progress.tsx`, `toggle-group.tsx`, `sidebar.tsx`: added `// dynamic-style:` comments for runtime style attributes.
  - `sonner.tsx`: removed `next-themes` dependency import and `useTheme()`; accepted `theme?: "light" | "dark" | "system"` prop.
  - `sidebar.tsx`: width constants `15rem` (expanded), `18rem` (mobile), `4rem` (icon); removed cookie persistence; toggles on bare `[` key ignoring inputs/textareas/selects/contenteditable; `SidebarTrigger` has `aria-label="Toggle sidebar"`.
  - `use-mobile.ts`: initial state synchronously resolved from `window.matchMedia("(max-width: 767px)").matches`.
- **VizenLink Brand Assets & BrandLogo (`tools/crop_brand.py`, `src/assets/brand/`, `BrandLogo.tsx`, `favicon.png`):**
  - Created reproducible PIL cropping tool `tools/crop_brand.py` taking `--src`, `--out`, `--favicon`.
  - Extracted mark (aspect 1.48, 189x128), wordmark (aspect 10.42, 500x48), full lockup (aspect 1.31, 627x480), and 32x32 transparent favicon from `/Users/gokul/mobilecctvapp/assets/branding`.
  - Confirmed sidebar header fit: 47.3px mark + 8px gap + 124.9px wordmark = 180.3px <= 208px.
  - Generated `provenance.json` with SHA-256 hashes for sources and outputs.
  - Implemented `BrandLogo` with `mark`, `lockup`, and `full` variants swapping theme images via CSS classes (`dark:hidden`, `hidden dark:block`), with explicit dimensions and `decoding="async"`.
  - Added `@fontsource-variable/inter` import to `globals.css` and favicon link to `index.html`.

## 2. Restored Paths & Working Tree Integrity
- After each shadcn CLI invocation (`init` and `add`), `package.json` and `package-lock.json` were restored via `git checkout -- package.json package-lock.json` followed by `npm ci`.
- No unapproved package was added to `package.json` or `package-lock.json`.
- The mobile repo `/Users/gokul/mobilecctvapp` was read-only; its `git status --porcelain` remained identical before and after.
- Neither this plan nor any script accessed the old VMS repo (`vizenlinkvms`).

## 3. Verification Commands & Outputs

### Task 1 Verification
```bash
npm --prefix src/vizenlink_nvr/web test -- src/test/ui-overrides.test.tsx && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && git diff --quiet HEAD -- src/vizenlink_nvr/web/package-lock.json src/vizenlink_nvr/web/package.json src/vizenlink_nvr/web/tsconfig.json src/vizenlink_nvr/web/vite.config.ts src/vizenlink_nvr/web/index.html src/vizenlink_nvr/web/src/main.tsx && test ! -e src/vizenlink_nvr/web/src/index.css
```
- **Exit Code:** 0
- **Output:** 2 passed, gates green (0 violations), build green.

### Task 2 Verification
```bash
npm --prefix src/vizenlink_nvr/web test && npm --prefix src/vizenlink_nvr/web run gates && npm --prefix src/vizenlink_nvr/web run build && git diff --quiet HEAD -- src/vizenlink_nvr/web/package-lock.json src/vizenlink_nvr/web/package.json src/vizenlink_nvr/web/tsconfig.json src/vizenlink_nvr/web/vite.config.ts src/vizenlink_nvr/web/index.html src/vizenlink_nvr/web/src/main.tsx && test ! -e src/vizenlink_nvr/web/src/index.css
```
- **Exit Code:** 0
- **Output:** 101 passed, gates green across 47 non-legacy files, build green.

### Task 3 Verification
```bash
uv run ruff check tools/crop_brand.py && uv run ruff format --check tools/crop_brand.py && NVR_MOBILE_BRANDING_DIR=/Users/gokul/mobilecctvapp/assets/branding npm --prefix src/vizenlink_nvr/web test -- src/test/brand.test.tsx && npm --prefix src/vizenlink_nvr/web run build && ! grep -rnF "vizenlinkvms" src/vizenlink_nvr/web/src tools/crop_brand.py
```
- **Exit Code:** 0
- **Output:**
  - Ruff check & format: all clean
  - Vitest brand test (with `NVR_MOBILE_BRANDING_DIR` source re-hash): 5 passed
  - Build: green
  - No `vizenlinkvms` string present in source or crop tool

## 4. Commits
- `cd9b4b0` feat(09-05): install shadcn/ui component inventory with UI-SPEC overrides
- `bed3088` feat(09-05): VizenLink logo crops from the mobile app and BrandLogo (D-03)

