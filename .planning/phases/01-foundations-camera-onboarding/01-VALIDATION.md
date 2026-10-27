---
phase: "1"
slug: "foundations-camera-onboarding"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-26"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.1 (`asyncio_mode = "auto"`) + pytest-timeout 2.4.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`. Doesn't exist yet; Wave 0 installs it. |
| **Quick run command** | `uv run pytest -x -q`. Default markers exclude `hardware` and `mediamtx`. |
| **Full suite command** | `uv run pytest && uv run pytest -m mediamtx`. Run `uv run python tools/fetch_mediamtx.py` once first. |
| **Hardware suite** | `uv run pytest -m hardware` after the owner supplies host/password securely in the environment. Destructive tests also need `NVR_HW_ALLOW_WRITE=1` or `NVR_HW_ALLOW_RESET=1`. |
| **Drift check** | `uv run python tools/drift_check.py --self` in CI. Locally, add `--upstream /Users/gokul/Desktop/vizenlinkvms/nuraeye-rt --mobile /Users/gokul/mobilecctvapp`. |
| **Estimated runtime** | Under 30 s for the quick suite (in-process simulator, injected clocks). |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -x -q`.
- **After every plan wave:** Run the full default suite plus `uv run pytest -m mediamtx`. CI runs the 3-OS matrix (Python 3.13 on Linux, macOS and Windows, plus Linux on Python 3.11).
- **Before owner verification:** three-OS CI is an explicit PENDING external gate while no remote exists; local phase_gate.py is host-only evidence, drift check clean, `alembic check` clean, and a hardware report HW-01..HW-14 attached. HW-04 is run once with `NVR_HW_ALLOW_RESET=1`.
- **Max feedback latency:** 30 seconds (quick suite).

---

## Per-Task Verification Map

Plan and task IDs are filled in by the planner. The requirement-to-test mapping below is binding.

| Requirement | Plan / Task | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|-------------|----------|-----------|-------------------|-------------|--------|
| FND-03 | 01-04 T1; 01-26 T1 | UTC storage; site-zone rendering across both DST transitions | unit/integration | `uv run pytest tests/integration/test_time_model.py -x` | ❌ W0 | ⬜ pending |
| FND-04 | 01-09 T1; 01-10 T1; 01-31 T1 | Default-deny config; live proof against the pinned binary | unit + mediamtx | `uv run pytest tests/unit/test_mediamtx_config.py && uv run pytest -m mediamtx` | ❌ W0 | ⬜ pending |
| FND-05 | 01-05–01-07; 01-11–01-22; 01-31 T3 | Mirror, fixtures, lock, header case, SOAP faults, 421 | contract | `uv run pytest tests/contract -x` | ❌ W0 | ⬜ pending |
| CAM-01 | 01-23 T1–T2 | Scan lists cameras; no credentials sent while scanning | integration | `uv run pytest tests/integration/test_scan.py` | ❌ W0 | ⬜ pending |
| CAM-02 | 01-25 T1 | Manual add by host | integration | `uv run pytest tests/integration/test_add_manual.py` | ❌ W0 | ⬜ pending |
| CAM-03 | 01-27 T2 | Failure reasons: unreachable, wrong credentials, unsupported, blocked | integration | `uv run pytest tests/integration/test_add_error_taxonomy.py` | ❌ W0 | ⬜ pending |
| CAM-04 | 01-27 T1 | Forced password change; exactly one factory probe | integration | `uv run pytest tests/integration/test_factory_flow.py` | ❌ W0 | ⬜ pending |
| CAM-05 | 01-26 T1; 01-29 T2 | Capabilities probed, cached, re-probed | integration | `uv run pytest tests/integration/test_capabilities_probe.py tests/integration/test_reprobe.py` | ❌ W0 | ⬜ pending |
| CAM-06 | 01-27 T3 | Atomic add | integration | `uv run pytest tests/integration/test_atomic_add.py` | ❌ W0 | ⬜ pending |
| CAM-07 | 01-24 T2; 01-26 T1 | Main/sub selection; Profile_3 never chosen; WebRTC → ONVIF fallback (D-23) | unit + integration | `uv run pytest tests/unit/test_stream_selection.py tests/integration/test_streams_persisted.py` | ❌ W0 | ⬜ pending |
| CAM-08 | 01-29 T1 | Name and location written to the camera; group stays NVR-only | integration | `uv run pytest tests/integration/test_rename.py` | ❌ W0 | ⬜ pending |
| CAM-10 | 01-28 T1–T2 | Serial identity; re-IP heal without duplicates | integration | `uv run pytest tests/integration/test_reip.py` | ❌ W0 | ⬜ pending |
| cross-cutting | 01-31 T2; 01-08 T1–T2; 01-07 T2 | No secret leakage; credentials at rest; architecture import rules | unit | `uv run pytest tests/unit/test_no_secrets_leak.py tests/unit/test_credentials_at_rest.py tests/unit/test_architecture_rules.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml`, `uv.lock`, `.python-version`, `.github/workflows/ci.yml`, `.gitignore` (data dirs, `tests/hardware/reports/`)
- [ ] `tests/conftest.py` with:
  - the simulator fixture (TLS camera plus UDP responder);
  - a fake clock;
  - a `tmp_path` data dir;
  - `NVR_SECRETS_BACKEND=file`;
  - a session-wide check that no MediaMTX process is left running.
- [ ] `sim/fake_camera/` (behaviours per RESEARCH Pattern 12)
- [ ] `contracts/camera_api/` copies, `camera_api.lock.json`, `behaviors.yaml`, `fixtures/`, `contracts/mobile_app/` (D-28), `tools/vendor_contracts.py`, `tools/drift_check.py`
- [ ] `src/vizenlink_nvr/db/migrations/` (`env.py` with `render_item`, `0001_initial`)
- [ ] `tools/fetch_mediamtx.py` and `media/pins.json`
- [ ] Framework install: `uv sync`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-camera scan, add, wrong password, re-IP, 2-client RTSPS limit, WSSE skew, header case (HW-01..HW-14) | CAM-01..CAM-10, FND-05 | Needs the user's physical camera on the LAN | `uv run pytest -m hardware` after the blocking owner checkpoint; attach the report from `tests/hardware/reports/` |
| Factory-password flow on real hardware (HW-04) | CAM-04 | Soft-resets the user's only camera (approved, opt-in only: D-24) | Same as above, plus `NVR_HW_ALLOW_RESET=1`. The test warns before resetting. |
| MediaMTX default-deny on the target box | FND-04 | Proves the deployed config, not just CI | `nvr mediamtx check --probe` |
| Windows/macOS behaviours flagged `[ASSUMED]` in RESEARCH (ACLs, keyring blocking, Local Network prompt) | FND-05, D-14 | Need those OSes | Covered by the CI matrix; verify the CI logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

## Revision gates

No git remote exists or may be created by this work. Three-OS CI stays PENDING until separately enabled by the owner. A green local tools/phase_gate.py is local evidence only. Hardware/reset gates stay pending without explicit run authorization. Phase verification belongs to a separate owner session.
