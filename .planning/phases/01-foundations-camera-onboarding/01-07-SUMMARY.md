# Plan 01-07 Summary: HTTP Choke Point, Simulator Authority, and Architecture Guards

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Complete HTTP choke point (header case, 421/unreachable events, silence timer, TLS pin, result mapping)**
   - Hardened `src/vizenlink_nvr/camera/http.py`:
     - Implemented silence detection timer (`silent_after` with streaming `client.stream(...)` cancellation) publishing `CameraUnreachableEvent` if headers do not arrive in time.
     - Implemented exact header case preservation and `X-VizenLink-Camera-Id` injection when serial is set.
     - Implemented 421 Misdirected Request event publishing and `Failure(ID_MISMATCH, "HTTP 421: Camera ID mismatch")` result mapping.
     - Implemented TLS pin verification failure catching without unreachable publishing, returning `Failure(TLS_CHANGED)`.
   - Created `tests/contract/test_http_choke_point.py`:
     - Verified `HTTP-01`, `HTTP-02`, `HTTP-03`, `HTTP-04`, `HTTP-05`, `HTTP-06`, `HTTP-08`, `HTTP-09`.
   - Updated `tests/contract/test_results.py`:
     - Verified `RES-01`, `RES-02`, `RES-06`, `RES-07`.
   - Updated `tests/contract/test_wsse.py`:
     - Verified `WSSE-01`, `WSSE-02`.

2. **Task 2: Simulator state (authority, lockout, WSSE classification), UDP discovery responder, architecture rules**
   - Updated `sim/fake_camera/state.py`:
     - Verified accounts and roles (`CameraRole.ADMINISTRATOR`, etc.).
     - Implemented LRU session eviction at 11th login (capacity 10).
     - Implemented lockout on 5 consecutive failures (15s doubling to 30s cap for administrator).
     - Implemented `set_password` rejecting "password" in any case and clearing `first_password_gate`.
     - Implemented camera-id precedence over authentication (wrong ID with wrong password yields 421, not 401).
   - Created `sim/fake_camera/discovery.py`:
     - Implemented `DiscoveryResponder` UDP datagram listener answering WS-Discovery Probes with `ProbeMatches` carrying `dn:NetworkVideoTransmitter`, XAddrs, and scopes (MAC, name, location).
   - Updated `sim/fake_camera/pytest_plugin.py`:
     - Added `discovery_responder` fixture auto-attaching created fake cameras.
   - Created `tests/unit/test_sim_state.py`:
     - Tested authority, LRU eviction, 5-failure lockout, password change rules, WSSE classification, and WS-Discovery.
   - Created `tests/unit/test_architecture_rules.py`:
     - AST verification that `vizenlink_nvr.camera` never imports db, services, cli, or secrets.
     - AST verification that `vizenlink_nvr.cli` never imports camera.
     - AST verification that no module-level asyncio primitives exist in top-level statements.

### Verification Evidence:
- `uv run pytest tests/contract/test_http_choke_point.py tests/contract/test_results.py tests/contract/test_wsse.py -x -q`: 18 passed.
- `uv run pytest tests/unit/test_sim_state.py tests/unit/test_architecture_rules.py -x -q`: 12 passed.
- `uv run pytest -q`: 58 passed in 1.45s across entire test suite.
- `grep -ho 'behavior("[A-Z0-9-]*")' tests/contract/*.py | sort -u`: All 16 contract behavior markers present.
- `uv run mypy src`: 35 source files checked, 0 errors.
- `uv run ruff check src tests sim` & `uv run ruff format --check src tests sim`: 0 errors.
- `git commit`: `a858a14 feat(camera): complete HTTP choke point, simulator authority, and architecture guards (plan 01-07)`.
