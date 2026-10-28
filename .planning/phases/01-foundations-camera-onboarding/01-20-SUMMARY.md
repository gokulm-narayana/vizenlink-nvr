# Plan 01-20 Summary: Capabilities and Live-Stream URI Contracts

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Capabilities rules and live-stream-uri (CAP-01..06, LST-01..03)**
   - Updated `src/vizenlink_nvr/camera/nuraeye/capabilities.py`:
     - Added `missing_required: list[str]` to `Capabilities`.
     - In strict mode, missing `wan_command_capable` or `wan_live_view_capable` fails with reason starting with `"GetCapabilities response missing"` (CAP-01).
     - In non-strict mode, missing flags default to `False` and are tracked in `Capabilities.missing_required`.
   - Created `src/vizenlink_nvr/camera/nuraeye/live_stream_uri.py`:
     - Profile token constants `MAIN_PROFILE_TOKEN = "Profile_1"`, `SUB_PROFILE_TOKEN = "Profile_2"`, `MOBILE_ONLY_PROFILE_TOKEN = "Profile_3"`.
     - `LiveStreamUri` frozen dataclass with `transport`, `port`, `url`, `scheme`, and `path`.
     - `parse_live_stream_uri` parsing transport, validating URLs with `urllib.parse.urlsplit`, checking valid schemes, and reporting failures for unknown transports, unparseable URLs, or missing fields (LST-01..03, CAM-07).
   - Updated `src/vizenlink_nvr/camera/nuraeye/client.py`:
     - Added `get_live_stream_uri(profile_token, timeout=8.0)` dispatching authenticated `POST /nuraeye/live-stream-uri` and parsing with `parse_live_stream_uri`.
   - Implemented simulator route `sim/fake_camera/routes/rest_live_stream.py`:
     - Handles `POST /nuraeye/live-stream-uri` requiring bearer token.
     - Profile mapping: `Profile_1` (554, `/high`), `Profile_2` (555, `/medium`), `Profile_3` (556, `/mobile`).
     - Supports `rest_settings(cam).live_stream_mode == "webrtc"` returning `transport: "webrtc"`, port 8444, `/webrtc` signaling URL.
     - Rejects unknown profile tokens with HTTP 400.
   - Created 3 golden fixtures in `contracts/fixtures/nuraeye/`:
     - `capabilities_minimal.json` (source: `capabilities_client_test.dart` L57-59).
     - `live_stream_uri_rtsp.json` (source: `camera-rest-api.md` L1412-1421).
     - `live_stream_uri_webrtc.json` (source: `live_stream_uri_client_test.dart` L18-23).
   - Created `tests/contract/test_live_stream_uri.py` testing LST-01 (Profile 1/2/3 mapping, WebRTC mode, fixture parsing), LST-02 (invalid responses: unknown transport, unparseable url, missing port), and LST-03 (400, 404, 501 error handling with no fallback).
   - Expanded `tests/contract/test_capabilities.py` covering CAP-01, CAP-02 (minimal fixture defaults), CAP-03, CAP-04, CAP-05 (raw preserves unknown fields and typed superset), and CAP-06 (runtime key auditor verifying every field read exists in OpenAPI capabilities schema).

### Verification Evidence:
- `uv run pytest tests/contract/test_capabilities.py tests/contract/test_live_stream_uri.py -x -q`: 21 passed in 0.23s.
- `uv run pytest tests/contract -x -q`: 64 passed in 2.29s.
- `grep -ho 'behavior("[A-Z0-9-]*")' tests/contract/*.py | sort -u`: All required behavior tags present.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 90 files formatted.
- `uv run mypy src/vizenlink_nvr/camera`: Success: no issues found in 15 source files.
- `uv run pytest -q`: 117 passed, 1 skipped, 6 deselected in 3.78s.
- Reference repositories remained untouched.
