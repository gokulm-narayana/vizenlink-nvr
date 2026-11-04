# Phase 08: Cross-Platform Packaging & Soak - Validation Strategy

## 1. Automated Verification Commands
- **Unit Tests:**
  - `uv run pytest tests/unit/test_service_packaging.py -v`
  - `uv run pytest tests/unit/test_power_management.py -v`
  - `uv run pytest tests/unit/test_backup_restore.py -v`
- **Integration Tests:**
  - `uv run pytest tests/integration/test_16camera_soak.py -v`
  - `uv run pytest tests/integration/test_phase8_tracer.py -v`
- **Local Phase Gate:**
  - `uv run python tools/phase_gate.py` (all 15 steps green)

## 2. Requirements Traceability Matrix
| Requirement | Covered By | Automated Test | Status |
|---|---|---|---|
| **FND-06 (Multi-OS Services)** | Service generators for Systemd, LaunchDaemon, Windows | `test_service_packaging.py`, `test_phase8_tracer.py` | PASS |
| **Sleep Inhibition** | `PowerManager` (macOS caffeinate, Linux inhibit, Windows kernel32) | `test_power_management.py`, `test_phase8_tracer.py` | PASS |
| **Backup & Restore** | `BackupService` (`nvr backup create/restore`) | `test_backup_restore.py`, `test_phase8_tracer.py` | PASS |
| **16-Camera Soak** | Concurrency soak simulation with 16 cameras and 2 viewers | `test_16camera_soak.py`, `test_phase8_tracer.py` | PASS |

## 3. Phase Gate Step 15
Step 15 in `tools/phase_gate.py` executes `tests/integration/test_phase8_tracer.py`, validating the entire packaging, backup, power, and soak lifecycle end-to-end.

