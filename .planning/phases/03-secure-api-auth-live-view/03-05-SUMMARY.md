# Plan 03-05: Core REST API Endpoints & OpenAPI 3.1 Breaking-Change Guard Summary

**Execution Date:** 2026-11-04  
**Status:** Completed  
**Requirements:** MOB-01, HLTH-02

---

## 1. Summary of Delivered Capabilities

1. **Camera Registry REST Endpoints (`src/vizenlink_nvr/api/v1/cameras.py`):**
   - `GET /api/v1/cameras`: Lists cameras; viewers strictly receive only their permitted cameras per `AUTH-05`.
   - `GET /api/v1/cameras/{serial}`: Returns full camera view; enforces viewer RBAC access checks.
   - `POST /api/v1/cameras`: Onboards a camera with atomic validation and AES-GCM credential sealing. Restricted to Operator+.
   - `DELETE /api/v1/cameras/{serial}`: Removes camera with option to preserve or purge disk recordings. Restricted to Owner.
   - `POST /api/v1/cameras/{serial}/reprobe`: Triggers live hardware reprobe. Restricted to Operator+.
   - `POST /api/v1/cameras/{serial}/media-token`: Issues signed 15-minute ephemeral media tokens.

2. **Recording Configuration REST Endpoints (`src/vizenlink_nvr/api/v1/recording.py`):**
   - `GET /api/v1/recording/status`: Returns current recording policy, weekly schedule, retention limits, and audio status across accessible cameras.
   - `PATCH /api/v1/recording/{serial}`: Updates recording mode (`continuous`, `scheduled`, `event`, `off`), schedule JSON, audio toggle, and retention limits. Enforces camera audio capability checks. Restricted to Operator+.

3. **Storage Telemetry & Management REST Endpoints (`src/vizenlink_nvr/api/v1/storage.py`):**
   - `GET /api/v1/storage/status`: Returns storage volume mountpoint, disk capacity, free bytes, reserve bytes, and health status (`ok`, `system_disk_refused`, `unmounted`, `read_only`, `full`).
   - `POST /api/v1/storage/set-path`: Updates active recording volume while enforcing root filesystem protection guard (`allow_system_disk`). Restricted to Owner.
   - `POST /api/v1/storage/scan`: Triggers background storage volume indexing reconciliation. Restricted to Operator+.

4. **Health & Telemetry REST Endpoints (`src/vizenlink_nvr/api/v1/health.py`):**
   - `GET /api/v1/health`: Evaluates and aggregates database, MediaMTX, storage, and registered camera statuses (`healthy`, `degraded`, `critical`).

5. **OpenAPI 3.1 Specification & Automated Breaking-Change Guard:**
   - Saved baseline OpenAPI 3.1 specification at `contracts/openapi_v1_baseline.json`.
   - Built `tools/check_api_breaking_changes.py` detecting removed routes/methods, newly required parameters, schema mutations, and removed success status codes.
   - Verified backward compatibility via `tests/contract/test_openapi_spec.py`.

6. **Automated Verification:**
   - `tests/integration/test_api_cameras.py`: 1 passed.
   - `tests/integration/test_api_recording.py`: 1 passed.
   - `tests/integration/test_api_storage.py`: 1 passed.
   - `tests/contract/test_openapi_spec.py`: 2 passed.

