# Plan 01-30 Summary: Opt-In Real-Camera Test Suite & Hardware Checkpoint

## Status: COMPLETE (Hardware Execution Pending Owner Hardware)

### Tasks Completed:
1. **Task 1: Build complete gated real-camera harness HW-01..HW-14**
   - Created `tests/hardware/support/__init__.py`.
   - Created `tests/hardware/support/report.py`:
     - Implemented `HwReport` collecting per-test measured metrics and outcomes.
     - Automatically asserts no password strings (`NVR_HW_PASSWORD`) appear in generated markdown reports (D-20).
   - Created `tests/hardware/support/rtsps_client.py`:
     - Implemented `RtspsClient` providing RTSP-over-TLS client with RFC 2617 Digest auth (MD5, realm ONVIF, no qop) (D-26).
     - Supports `connect()`, `describe()`, `setup()`, `play()`, and `close()`.
   - Created `tests/hardware/support/camera_admin.py`:
     - Implemented `soft_factory_reset(conn)` sending ONVIF `SetSystemFactoryDefault` with FactoryDefault `Soft` (D-20, D-24).
     - Implemented `create_user(conn, username, password, level="User")` and `delete_user(conn, username)`.
     - Implemented `wait_until_answering(host, port, timeout=180.0)`.
   - Created `tests/hardware/conftest.py`:
     - Enforces `pytest.mark.hardware` marker on all tests in directory.
     - Implemented `hw_env` fixture: reads `NVR_HW_HOST`, `NVR_HW_PORT`, `NVR_HW_USER`, `NVR_HW_PASSWORD`; strictly gates execution requiring `NVR_HW_RUN_AUTHORIZED=1` (skips before any network socket operation).
     - Implemented `hw_write` fixture (gates on `NVR_HW_ALLOW_WRITE=1`).
     - Implemented `hw_reset` fixture (gates on `NVR_HW_ALLOW_RESET=1`).
     - Implemented `hw_report` session fixture.
     - Implemented `hw_camera_snapshot` session fixture: captures initial serial, name, and location, and restores them at session end only if mutations occurred.
   - Created test suites:
     - `tests/hardware/test_hw_discovery_onboarding.py`:
       - `test_gate_skips_when_not_authorized`: unit test proving no socket open without `NVR_HW_RUN_AUTHORIZED=1`.
       - `HW-01`: WS-Discovery multicast and unicast scans across real interfaces.
       - `HW-02`: Real camera onboarding via `nvr cameras add --password-stdin --json` into tmp data dir.
       - `HW-12`: Validates typed capabilities structure (`camera_id_check=True`, `default_password_in_use=False`).
       - `HW-14`: Certificate fingerprint checks on ports 443, 554, 555 and pinned connection verification.
     - `tests/hardware/test_hw_protocol.py`:
       - `HW-03`: One add with wrong password -> `WRONG_CREDENTIALS`, followed by immediate right password without lockout.
       - `HW-05`: Reprobe heals closed port back to real address; wrong id header yields 421.
       - `HW-06`: Exact-case wrong id -> 421 (asserted); lower-case wrong id recorded.
       - `HW-07`: Interleaved WSSE time skew logins (now-1h, now+1h, now-24h) interleaved with valid recovery logins.
     - `tests/hardware/test_hw_streams.py`:
       - `HW-10`: Live stream URIs for profiles with WebRTC fallback to Media2 GetStreamUri (D-23).
       - `HW-11`: Media2 profiles, sizes, encodings, and RTSPS DESCRIBE SDP codec inspection.
       - `HW-09`: Concurrency limit: maximum 2 concurrent streams per stream path; 3rd refused (D-26).
     - `tests/hardware/test_hw_writes.py`:
       - `HW-04`: Soft factory reset, 10s wait, `PasswordChangeRequired` verification, and initial provisioning (D-20, D-24).
       - `HW-08`: User-role account creation, RTSPS DESCRIBE with user credentials, and deletion cleanup.
       - `HW-13`: Rename and location sync via GetScopes, plus 32-character Unicode limit testing (A11), with snapshot restore.

2. **Task 2: Real-camera execution approval (Blocking Human Gate)**
   - Human gate presented to user.
   - User selected: `No physical camera available: mark real-camera tests (HW-01..HW-14) as pending/skipped, write hardware report, and proceed with Plan 01-30 Task 3 and Plan 01-31`.

3. **Task 3: Run only owner-authorized hardware checks and record measured report**
   - Synchronized session snapshot fixture in `tests/hardware/conftest.py`.
   - Executed `uv run pytest -m hardware tests/hardware -q -rs`:
     - 14 tests collected.
     - 14 tests skipped with `Hardware execution requires NVR_HW_RUN_AUTHORIZED=1 (checkpoint approval)`.
     - Zero socket operations occurred; zero network leaks; exit code 0.
     - All HW cases recorded as pending/skipped; no false hardware claims made.

### Verification Results:
- `uv run pytest -m hardware tests/hardware --collect-only -q`: 14 tests collected, exit code 0.
- `uv run pytest -m hardware tests/hardware -q -rs`: 14 skipped, exit code 0.
- `uv run ruff check tests/hardware`: passed with 0 errors.
- `uv run ruff format --check tests/hardware`: 9 files already formatted.
