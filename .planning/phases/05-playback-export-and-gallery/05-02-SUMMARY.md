# Plan 05-02 Summary: Timeline Index & Calendar Query API

## Executed Tasks
1. **Implemented TimelineService**:
   - Created `src/vizenlink_nvr/services/timeline.py` aggregating:
     - Recorded video segments within the requested query window.
     - Camera outages from `CameraOutage` to visibly distinguish outage intervals from footage removed by retention (`PLAY-08`).
     - Event markers from `Event` to display alert flags on the timeline (`PLAY-01`, `PLAY-05`).
     - Distinct calendar recording days for date-picker population (`PLAY-02`).
     - Recording search by camera, date/time, and event type (`GAL-03`).
2. **Built `/api/v1/playback` Endpoints**:
   - `GET /api/v1/playback/timeline`: 24-hour timeline query with segments, outages, and event markers.
   - `GET /api/v1/playback/days`: Available dates in month.
   - `GET /api/v1/playback/search`: Search recordings by event type and time window.
   - `POST /api/v1/playback/segments/{id}/lock` & `/unlock`: Evidence lock toggle protecting segments from retention and low-water pruning (`REC-12`).
   - Wired router into `src/vizenlink_nvr/api/app.py` and updated `contracts/openapi_v1_baseline.json`.
3. **Integration Testing**:
   - Authored `tests/integration/test_playback_timeline.py` verifying timeline query, outage visualization, days discovery, event-based recordings search, segment locking, and viewer RBAC restrictions.
   - Verified 5/5 tests passing cleanly.

## Key Changes
- `src/vizenlink_nvr/services/timeline.py`
- `src/vizenlink_nvr/api/v1/playback.py`
- `src/vizenlink_nvr/api/app.py`
- `contracts/openapi_v1_baseline.json`
- `tests/integration/test_playback_timeline.py`

