# Plan 01-26 Summary: Stream Fallback, Capability Cache, and Registry Display

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Stream selection rules with the D-23 fallback, capability cache, list/show rendering and status counts**
   - Extended `src/vizenlink_nvr/services/streams.py`:
     - Added warning logging when selected profile uses H.265 codec (`Phase 3 compatibility`).
     - Verified natural token sorting and profile selection: drops `Profile_3` / `MOBILE_ONLY_PROFILE_TOKEN` even if largest; skips profiles missing resolution; selects largest main and next sub (or sets `sub_is_main=True` for single profile).
     - Verified D-23 fallback: when `live-stream-uri` returns transport `webrtc`, stream resolution falls back to ONVIF Media2 `GetStreamUri` with `source="onvif_fallback"`.
   - Updated `src/vizenlink_nvr/services/onboarding.py`:
     - Cached raw JSON capabilities verbatim in `camera_capabilities`.
     - Parsed capabilities with `parse_capabilities(strict=False)` and logged `missing_required` fields at WARNING level without aborting onboarding.
     - Persisted parsed `camera_id_check` flag to `camera.camera_id_check`.
   - Updated `src/vizenlink_nvr/services/status.py`:
     - Added `cameras_total` and `cameras_by_state` using `camera_counts` to `StatusReport`.
   - Updated `src/vizenlink_nvr/cli/cameras_registry.py`:
     - Ensured `nvr cameras list --json` and `nvr cameras show --serial <serial> --json` cleanly serialize without exposing secret keys (`password`, `ciphertext`, `nonce`, `key_id`).
   - Created and expanded tests:
     - `tests/unit/test_stream_selection.py` (marked `PRF-03`): single profile, 3 profiles with `Profile_3` largest, natural token order, invalid size drop, H.265 warning log.
     - `tests/integration/test_streams_persisted.py` (marked `LST-04`): verifies clean columns (no `@` or `://`), default ports 554/555, `stream_url` construction, WebRTC fallback to ONVIF Media2 with `source="onvif_fallback"`, and `STREAMS_UNAVAILABLE` on fallback failure.
     - `tests/integration/test_capabilities_probe.py`: verbatim raw JSON caching, clock timestamping, missing WAN flags tolerance, and `camera_id_check` persistence.
     - `tests/integration/test_registry.py`: verifies list/show JSON never contains secret keys, and status reports camera counts.
     - `tests/integration/test_time_model.py`: verifies `cameras show` renders `added_at` with DST transitions (`EDT (-04:00)` and `EST (-05:00)`) in `America/New_York`.

### Verification Evidence:
- `uv run pytest tests/unit/test_stream_selection.py tests/integration/test_streams_persisted.py tests/integration/test_capabilities_probe.py tests/integration/test_registry.py tests/integration/test_time_model.py -x -q`: 24 passed in 0.56s.
- `uv run mypy src`: Success: no issues found in 64 source files.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 116 files already formatted.
- Passwords never entered logs, arguments, or plain text outputs; all listeners bound loopback.
