# Plan 04-05 Summary: Events REST API & OpenAPI Baseline

## Executed Tasks
1. **Implemented `/api/v1/events` Router & Models**:
   - `GET /api/v1/events`: Paginated event listings with camera, type, lock, and time window filters. Viewers are strictly scoped to permitted cameras (`AUTH-05`).
   - `GET /api/v1/events/{id}`: Detailed event inspection with viewer permission validation.
   - `GET /api/v1/events/{id}/snapshot`: Serves event JPEG snapshot with traversal prevention (`EventSnapshotManager`).
   - `POST /api/v1/events/{id}/lock` & `POST /api/v1/events/{id}/unlock`: Operator/owner-restricted endpoints that toggle `is_locked`, invoke `SegmentProtectionService` to protect or release underlying recording segments, and emit audit entries.
   - `GET /api/v1/events/subscriptions/status`: Exposes PullPoint subscription supervisor state and clock drift metrics across cameras.
2. **Wired Router into FastAPI App & Updated OpenAPI 3.1 Baseline**:
   - Included `events_router` in `v1_router` in `src/vizenlink_nvr/api/app.py`.
   - Updated `contracts/openapi_v1_baseline.json`. Verified backward compatibility with `tools/check_api_breaking_changes.py`.
3. **Integration Testing**:
   - Authored `tests/integration/test_api_events.py` covering owner queries, viewer RBAC scoping, detail/snapshot access control, locking/unlocking segment protection, and subscription statuses.
   - Verified 5/5 tests passing cleanly.

## Key Changes
- `src/vizenlink_nvr/api/v1/events.py`
- `src/vizenlink_nvr/api/app.py`
- `contracts/openapi_v1_baseline.json`
- `tests/integration/test_api_events.py`
