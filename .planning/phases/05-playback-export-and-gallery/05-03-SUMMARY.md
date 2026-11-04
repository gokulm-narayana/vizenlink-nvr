# Plan 05-03 Summary: HTTP Byte-Range Seeking & MediaMTX Playback Auth

## Executed Tasks
1. **Built `RangeFileResponse`**:
   - Created `src/vizenlink_nvr/media/playback_streamer.py` implementing HTTP 206 Partial Content byte-range streaming for recorded fMP4 segments.
   - Supports standard byte ranges (`bytes=start-end`, `bytes=start-`, `bytes=-suffix`) and sets `Accept-Ranges: bytes`, `Content-Range`, and `Content-Length`.
   - Handles out-of-bounds requests with 416 Range Not Satisfiable.
2. **Added Segment Video Streaming Endpoint**:
   - Added `GET /api/v1/playback/segment/{segment_id}` in `src/vizenlink_nvr/api/v1/playback.py`.
   - Strictly enforces viewer RBAC permissions (`AUTH-05`).
   - Updated `contracts/openapi_v1_baseline.json`.
3. **Updated MediaMTX Playback Webhook Auth**:
   - Updated `mediamtx_auth_webhook` in `src/vizenlink_nvr/api/v1/auth.py` to allow `action in ("read", "playback")`, authenticating MediaMTX playback server requests (`:9996`) with ephemeral signed media tokens.
4. **Integration Testing**:
   - Authored `tests/integration/test_playback_streaming.py` verifying full file streaming, range slicing, out-of-bounds handling, viewer restrictions, and MediaMTX playback auth.
   - All 4 tests passing cleanly.

## Key Changes
- `src/vizenlink_nvr/media/playback_streamer.py`
- `src/vizenlink_nvr/api/v1/playback.py`
- `src/vizenlink_nvr/api/v1/auth.py`
- `contracts/openapi_v1_baseline.json`
- `tests/integration/test_playback_streaming.py`

