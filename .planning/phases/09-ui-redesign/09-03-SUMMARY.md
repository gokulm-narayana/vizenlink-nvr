# Phase 9 Plan 03: Fail-Closed Camera Vault Summary

## Overview
Executed Plan 09-03 to complete the third approved backend addition (D-18):
1. **Operational Vault on Runtime** (`src/vizenlink_nvr/services/runtime.py`): added `vault: Vault | None = None` to `Runtime`. `open_runtime` opens the operational vault when the canary status is "ok", catching failures gracefully without failing runtime open.
2. **Fail-Closed `_resolve_vault`** (`src/vizenlink_nvr/api/v1/cameras.py`): removed the silent all-zero in-memory test key fallback. `_resolve_vault` now checks `request.app.state.runtime.vault` and raises HTTP 503 (`Camera credentials can't be stored because the NVR credential vault is unavailable.`) when unavailable.
3. **Explicit Vault Injection in Tests**: updated existing camera API tests (`test_api_cameras.py`, `test_phase3_tracer.py`) to explicitly inject a test vault into `create_app(runtime=...)`, preserving test determinism without production fallback.
4. **Integration Tests** (`tests/integration/test_api_cameras_vault.py`): added comprehensive tests covering production runtime vault opening, round-trip credential encryption/decryption matching recorder behavior, and 503 fail-closed behavior across all missing-vault permutations.

## Commits
All tasks committed via private-index protocol:
1. `c37cb59`: `feat(09-03): open the operational vault on Runtime for API credential sealing (D-18)`
   - `src/vizenlink_nvr/services/runtime.py`
   - `tests/integration/test_api_cameras_vault.py`
2. `6d502c9`: `fix(09-03): fail closed when POST /cameras has no runtime vault (D-18)`
   - `src/vizenlink_nvr/api/v1/cameras.py`
   - `tests/integration/test_api_cameras_vault.py`
   - `tests/integration/test_api_cameras.py`
   - `tests/integration/test_phase3_tracer.py`

## Commands Run & Real Output

### Task 1 Automated Verify Command
```bash
uv run pytest tests/integration/test_api_cameras_vault.py -q && uv run mypy src/vizenlink_nvr/services/runtime.py && uv run ruff check src/vizenlink_nvr/services/runtime.py tests/integration/test_api_cameras_vault.py
```
**Output:**
```
...                                                                      [100%]
3 passed in 0.58s
Success: no issues found in 1 source file
All checks passed!
```
**Result:** PASS

### Task 2 Automated Verify Command
```bash
uv run pytest tests/integration/test_api_cameras_vault.py tests/integration/test_api_cameras.py tests/integration/test_phase3_tracer.py tests/integration/test_camera_settings_api.py tests/contract/test_openapi_spec.py -q && uv run mypy src/vizenlink_nvr/api/v1/cameras.py && uv run ruff check src/vizenlink_nvr/api/v1/cameras.py tests/integration/test_api_cameras_vault.py tests/integration/test_api_cameras.py tests/integration/test_phase3_tracer.py
```
**Output:**
```
..............                                                           [100%]
14 passed in 18.30s
Success: no issues found in 1 source file
All checks passed!
```
**Result:** PASS

### Web Build
```bash
npm --prefix src/vizenlink_nvr/web run build
```
**Output:**
```
> vizenlink-nvr-web@1.0.0 build
> tsc && vite build

vite v8.3.6 building client environment for production...
✓ 37 modules transformed.
rendering chunks (1)...computing gzip size...
dist/index.html                  0.50 kB │ gzip:  0.36 kB
dist/assets/index-CPbRgggU.js  335.80 kB │ gzip: 93.05 kB

✓ built in 58ms
```
**Result:** PASS

## Follow-ups for Owner
1. `nvr run` (in `src/vizenlink_nvr/cli/app.py`, which is an uncommitted owner file) builds the FastAPI app. For web-based Add Camera to work in production, `nvr run` will need to pass `runtime=rt` to `create_app` once the CLI lifespan/runtime wiring is finalized.
2. `src/vizenlink_nvr/api/v1/camera_settings.py` contains a lazy test vault fallback in `get_vault` that was kept as-is since modifying `camera_settings.py` was out of scope for D-18.

