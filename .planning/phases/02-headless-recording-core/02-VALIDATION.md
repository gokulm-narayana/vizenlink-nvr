---
phase: "2"
slug: "headless-recording-core"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-28"
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: `02-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.1 (`asyncio_mode = "auto"`) + pytest-timeout 2.4.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/test_recording_*.py tests/unit/test_storage_*.py -x -q` |
| **Full suite command** | `uv run python tools/phase_gate.py` |
| **Estimated runtime** | ~60 seconds for full phase gate |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted pytest command.
- **After every plan wave:** Run `uv run pytest -q`.
- **Before phase verification:** Run `uv run python tools/phase_gate.py` (all 7 steps must be green).
- **Max feedback latency:** 15 seconds (quick unit suite).

---

## Per-Task Verification Map

| Requirement | Plan / Task | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|-------------|----------|-----------|-------------------|-------------|--------|
| FND-01 | 02-04 T2 | Independent MediaMTX process supervision; recording survives core crash | integration | `uv run pytest tests/integration/test_supervision.py -x` | ❌ W4 | ⬜ pending |
| FND-02 | 02-01 T1; 02-04 T1 | Declarative path reconciliation from SQLite to MediaMTX | integration | `uv run pytest tests/integration/test_reconciler_api.py -x` | ❌ W4 | ⬜ pending |
| CAM-09 | 02-06 T2 | Camera removal with keep-recordings or delete-recordings choice | integration | `uv run pytest tests/integration/test_camera_removal_recordings.py -x` | ❌ W6 | ⬜ pending |
| REC-01 | 02-04 T1; 02-08 T1 | 24/7 recording to fixed 60s fMP4 segments without remux step | integration | `uv run pytest tests/integration/test_fmp4_recording.py -x` | ❌ W8 | ⬜ pending |
| REC-02 | 02-03 T1 | Per-camera recording mode (Continuous / Event / Scheduled / Off) | unit/integration | `uv run pytest tests/unit/test_recording_modes.py -x` | ❌ W3 | ⬜ pending |
| REC-03 | 02-03 T1 | Weekly recording schedule grid and active window evaluation | unit | `uv run pytest tests/unit/test_recording_schedule.py -x` | ❌ W3 | ⬜ pending |
| REC-05 | 02-06 T1 | Retention janitor deletes oldest unprotected segments first | unit/integration | `uv run pytest tests/unit/test_retention_janitor.py -x` | ❌ W6 | ⬜ pending |
| REC-06 | 02-06 T1 | Per-camera retention configuration and storage estimation | unit | `uv run pytest tests/unit/test_retention_estimation.py -x` | ❌ W6 | ⬜ pending |
| REC-07 | 02-06 T1; 02-08 T1 | Free-space reserve low-water mark triggers automatic oldest pruning | integration | `uv run pytest tests/integration/test_disk_full_protection.py -x` | ❌ W6 | ⬜ pending |
| REC-08 | 02-01 T1; 02-02 T1 | Configurable storage path; system drive guard refuses root partition | unit/integration | `uv run pytest tests/unit/test_system_drive_guard.py -x` | ❌ W2 | ⬜ pending |
| REC-09 | 02-05 T1–T2 | Two-source indexing (real-time hook + periodic disk scanner reconciliation) | integration | `uv run pytest tests/integration/test_segment_indexing.py tests/integration/test_reconciliation_scanner.py -x` | ❌ W5 | ⬜ pending |
| REC-10 | 02-07 T1 | Stream drop detection, exponential backoff, and automatic reconnect | unit/integration | `uv run pytest tests/unit/test_stream_reconnect_backoff.py -x` | ❌ W7 | ⬜ pending |
| REC-11 | 02-03 T1 | Audio track recording toggle per camera | integration | `uv run pytest tests/unit/test_recording_modes.py -x` | ❌ W3 | ⬜ pending |
| HLTH-01 | 02-07 T2 | Dual independent badges: online/offline and recording/not_recording | unit/integration | `uv run pytest tests/unit/test_camera_health_badges.py -x` | ❌ W7 | ⬜ pending |
| HLTH-03 | 02-07 T1 | Recording gap watchdog detects missing segments (>150s) | unit/integration | `uv run pytest tests/unit/test_gap_watchdog.py -x` | ❌ W7 | ⬜ pending |
| HLTH-04 | 02-02 T1 | Storage status telemetry: disk space, free space, retention estimate | unit | `uv run pytest tests/unit/test_storage_service.py -x` | ❌ W2 | ⬜ pending |
| HLTH-05 | 02-02 T1 | Critical storage failure states (unmounted, read-only, full) | unit/integration | `uv run pytest tests/unit/test_storage_service.py -x` | ❌ W2 | ⬜ pending |
| HLTH-06 | 02-07 T2 | Recorder degraded health state when MediaMTX or DB degraded | unit/integration | `uv run pytest tests/integration/test_recorder_health.py -x` | ❌ W7 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Database migration `0003_recording_core.py` (tables: `recording_settings`, `segments`, `storage_settings`).
- [ ] Shared fixtures for simulated storage directories and mock disk usage in `tests/conftest.py`.
- [ ] Pinned MediaMTX binary available via `tools/fetch_mediamtx.py`.
