# Phase 07: Mobile LAN Integration - Validation Strategy

## 1. Automated Verification Commands
- **Unit Tests:**
  - `uv run pytest tests/unit/test_mdns_discovery.py -v`
  - `uv run pytest tests/unit/test_mobile_auth.py -v`
  - `uv run pytest tests/unit/test_mobile_api_unit.py -v`
- **Integration Tests:**
  - `uv run pytest tests/integration/test_mobile_api.py -v`
  - `uv run pytest tests/integration/test_phase7_tracer.py -v`
- **Frontend Build:**
  - `cd src/vizenlink_nvr/web && npm run build`
- **Local Phase Gate:**
  - `uv run python tools/phase_gate.py` (all 14 steps green)

## 2. Requirements Traceability Matrix
| Requirement | Covered By | Automated Test |
|---|---|---|
| **MOB-02** | `NvrMdnsAdvertiser` in `src/vizenlink_nvr/network/mdns.py` | `test_mdns_discovery.py`, `test_phase7_tracer.py` |
| **MOB-03** | `MobileAuthService` in `src/vizenlink_nvr/services/mobile_auth.py`, `POST /api/v1/mobile/pair`, `POST /api/v1/mobile/pair-qr`, device revocation | `test_mobile_auth.py`, `test_mobile_api.py`, `test_phase7_tracer.py` |
| **MOB-04** | `GET /api/v1/mobile/cameras/{id}/live-stream` default `sub` stream | `test_mobile_api.py`, `test_phase7_tracer.py` |
| **MOB-05** | `GET /api/v1/mobile/cameras/{id}/recording-dates`, `GET /api/v1/mobile/cameras/{id}/recordings` | `test_mobile_api.py`, `test_phase7_tracer.py` |
| **MOB-06** | `GET /api/v1/mobile/status` (recorder health, disk space, per-camera status) | `test_mobile_api.py`, `test_phase7_tracer.py` |
| **MOB-07** | Camera add/remove and recording mode changes with RBAC | `test_mobile_api.py`, `test_phase7_tracer.py` |

## 3. Phase Gate Step 14
Step 14 in `tools/phase_gate.py` will execute `tests/integration/test_phase7_tracer.py`, validating the entire mobile lifecycle end-to-end.
