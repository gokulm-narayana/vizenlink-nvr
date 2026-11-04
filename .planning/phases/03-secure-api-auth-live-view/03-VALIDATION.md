# Phase 3: Secure API, Auth & Live View - Validation Strategy

**Date:** 2026-11-04
**Status:** Validated (100% Passed)

## Validation Strategy Overview

Phase 3 introduces the first network listeners exposed to the LAN. Validation requires rigorous unit, contract, and integration tests ensuring that:
1. No video stream or API endpoint is accessible anonymously.
2. Credentials and passwords use salted Argon2id hashes, are never leaked in logs/errors, and default credentials cannot exist.
3. Server-side RBAC and camera whitelisting strictly constrain what each user can see and do.
4. MediaMTX rejects unauthorized stream reads and accepts authorized ephemeral signed media tokens.
5. Live view displays truthful state badges, defaults to sub-streams in grids, and auto-switches to main-stream on zoom.
6. Audit logs record every administrative, operational, and security-critical event.
7. The OpenAPI 3.1 specification is versioned and guarded against breaking changes in CI.

---

## Requirements Validation Matrix

| Requirement | Description | Test Type | Automated Test Target | Status |
|:---|:---|:---|:---|:---:|
| **AUTH-01** | First run walks through Owner account, timezone, storage location (no default credentials) | Integration | `tests/integration/test_auth_setup_wizard.py` | **PASSED** |
| **AUTH-02** | Local accounts (Argon2id hashes), password change, brute-force rate-limiting | Unit & Integration | `tests/unit/test_argon2_hashing.py`<br>`tests/integration/test_auth_sessions.py`<br>`tests/integration/test_auth_rate_limiting.py` | **PASSED** |
| **AUTH-03** | Roles (Owner, Operator, Viewer) enforced server-side on every API call and video stream | Integration | `tests/integration/test_rbac_authorization.py`<br>`tests/integration/test_media_auth_webhook.py` | **PASSED** |
| **AUTH-04** | Admin can add, edit, disable users and reset passwords | Integration | `tests/integration/test_user_management.py` | **PASSED** |
| **AUTH-05** | Admin can restrict a user to specific cameras | Integration | `tests/integration/test_user_camera_restrictions.py` | **PASSED** |
| **AUTH-06** | User can switch between Simple (default) and Advanced views | Frontend / Unit | `tests/unit/test_view_mode_toggle.py` | **PASSED** |
| **AUTH-07** | Audit log records logins, failures, camera ops, setting changes, user changes | Integration | `tests/integration/test_audit_logging.py` | **PASSED** |
| **AUTH-08** | User accounts can store linked VizenLink (Cognito) identity in data model | Unit | `tests/unit/test_user_model.py` | **PASSED** |
| **LIVE-01** | Watch single camera live (WebRTC, HLS fallback) with fullscreen | Integration | `tests/integration/test_mediamtx_http_auth.py`<br>`tests/integration/test_media_auth_webhook.py` | **PASSED** |
| **LIVE-02** | Multiview grid in 1×1, 2×2, 3×3, 4×4 with pagination | Unit / Component | `tests/unit/test_live_grid_layout.py` | **PASSED** |
| **LIVE-03** | Grid tiles use sub stream; enlarged tile switches to main stream | Integration | `tests/integration/test_sub_stream_auto_switch.py` | **PASSED** |
| **LIVE-04** | True tile state (connecting, live, offline; never frozen) and auto-reconnect | Unit & Integration | `tests/unit/test_tile_state_machine.py` | **PASSED** |
| **LIVE-05** | Tile controls: snapshot, maximize, mute, name overlay, recording badge | Unit / Component | `tests/unit/test_tile_controls.py` | **PASSED** |
| **LIVE-06** | User can arrange cameras into grid slots and last layout is remembered | Unit / Storage | `tests/unit/test_layout_persistence.py` | **PASSED** |
| **MOB-01** | Documented versioned REST API (OpenAPI 3.1, `/api/v1`) with breaking-change check | Contract / Tool | `tests/contract/test_openapi_spec.py`<br>`tools/check_api_breaking_changes.py` | **PASSED** |
| **HLTH-02** | Dashboard summarizes cameras online, recording, issues, storage, active alerts | Integration | `tests/integration/test_dashboard_summary.py` | **PASSED** |
| **HLTH-07** | In-app alerts for camera offline > N minutes, disk nearly full, recording gaps | Unit & Integration | `tests/unit/test_inapp_alerts.py` | **PASSED** |
| **HLTH-08** | Camera offline/recovery history (start, end, duration) | Integration | `tests/integration/test_camera_outage_history.py` | **PASSED** |

---

## Security Verification Invariants

1. **Zero Anonymous Access:**
   - Probing `/api/v1/cameras` or `/api/v1/recording` without a session cookie returns HTTP 401 Unauthorized.
   - Probing MediaMTX RTSP, HLS, or WebRTC endpoints without a signed media token returns HTTP 401 / 403.
2. **Brute Force Lockout Invariant:**
   - 5 failed login attempts for an account triggers an active 15-minute lock.
   - 6th attempt is rejected with HTTP 429 Too Many Requests or lock error even with correct credentials until the lockout duration expires.
3. **Viewer Restriction Invariant:**
   - A user with role `viewer` assigned to Camera A cannot fetch details or obtain media tokens for Camera B. Attempting to access Camera B returns HTTP 403 Forbidden.
4. **Sub-Stream Resource Invariant:**
   - All multi-tile grid views request only `stream=sub` tokens. Main stream token requests are strictly limited to enlarged or full-screen tiles.
5. **No Password Leakage:**
   - Database stores only Argon2id hash strings (`$argon2id$...`).
   - Passwords never appear in logs, CLI output, REST responses, or query params.

---

## Automated Phase Gate Verification Result

Phase Gate Tool: `tools/phase_gate.py`
Execution Date: 2026-11-04
Result: **10/10 steps passed (100% green)**

```
==> Step 1/10: Default pytest suite ... PASS
==> Step 2/10: Fetch MediaMTX binary ... PASS
==> Step 3/10: MediaMTX integration tests ... PASS
==> Step 4/10: Drift check against camera_api.lock.json ... PASS
==> Step 5/10a: Alembic upgrade head on temporary database ... PASS
==> Step 5/10b: Alembic schema drift check ... PASS
==> Step 6/10: Recording core pipeline tracer & password safety check ... PASS
==> Step 7/10: Ruff linter check ... PASS
==> Step 8/10: Mypy type check ... PASS
==> Step 9/10: OpenAPI 3.1 breaking change guard ... PASS
==> Step 10/10: Phase 3 end-to-end pipeline tracer ... PASS

Phase Gate Result: 10/10 steps passed.
```
