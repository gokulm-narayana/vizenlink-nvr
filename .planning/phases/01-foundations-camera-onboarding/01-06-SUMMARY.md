# Plan 01-06 Summary: Loopback TLS simulator and identity tracer

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Prove identity over TLS simulator**
   - Created `sim/fake_camera/__init__.py`: Simulator package initialization.
   - Created `sim/fake_camera/certs.py`: Generates self-signed EC certificate (CN=localhost) with already-expired validity window (mirroring SR-11).
   - Created `sim/fake_camera/faults.py`: Primitives `Status`, `Delay`, `Silence`, `Drop`, `Malformed`, and `SoapFault`; plus `FaultPlan` queue manager with FIFO route matching and wildcard fallback.
   - Created `sim/fake_camera/state.py`: `Account`, `ActiveSession`, and `CameraState` containing accounts, session tokens with LRU eviction, failure/lockout counters, credentials classification (`none`, `blank`, `stored`, `other`), and `check_camera_id` (421 guard).
   - Created `sim/fake_camera/routes/__init__.py`: Route registry and `route` decorator with `pkgutil.iter_modules` auto-discovery of all routes in `fake_camera/routes/`.
   - Created `sim/fake_camera/routes/rest_identity.py`: Handles `POST /nuraeye/identity` challenge verification and replies with `yes-i-am-onchip-nuraeye` digest (or bad digest if `state.genuine = False`).
   - Created `sim/fake_camera/server.py`: Custom HTTP/1.1 TLS server on `127.0.0.1:0` with raw header preservation, `RecordedRequest` audit log, fault consumption, 421 camera ID check, and route dispatching.
   - Created `sim/fake_camera/pytest_plugin.py`: Async pytest fixture `fake_camera` factory tracking and cleaning up started fake cameras.
   - Updated `tests/conftest.py`: Added `pytest_plugins = ["fake_camera.pytest_plugin"]`.
   - Created `tests/contract/test_identity.py`: Verified `IDN-01` (genuine and non-genuine devices, verifying `X-VizenLink-Camera-Id` header) and `IDN-02` (404 error, missing reply, timeout on delay).

### Verification Evidence:
- `uv run pytest tests/contract/test_identity.py -x -v`: 5 passed in 0.23s.
- `uv run pytest -q`: 36 passed in 0.65s.
- `uv run ruff check src tests sim` & `uv run ruff format --check src tests sim`: 0 errors.
- `uv run mypy src`: 35 source files checked, 0 errors.
- `git commit`: `3afea56 feat(camera): implement loopback TLS simulator and identity probe tracer (plan 01-06)`.
