# Handoff — 2026-11-11 17:15 — recorder-runtime-wired

**Account/session:** Claude Code (VS Code), verification account — owner asked to "search all and fix them all", then "fix them all"
**GSD position:** Phase 10 (UI v2 - Old VMS Parity) still in progress, built ad hoc (no PLAN.md). This session was fix work outside a GSD command, at the owner's explicit request.

## What this session did
- Reviewed the owner's large uncommitted change set (another agent's work: web camera onboarding via `/api/v1/cameras/onboard`, camera features/accounts/recordings APIs, search, assistant, compare playback, settings parity). Typecheck, Vitest and design gates were already green.
- Fixed tests broken by those changes: settings/tracer tests hung on new unmocked camera reads (`get_osd_options`, `get_system_timezone`, live `/nuraeye/health`); one ruff B904 in `api/cam_proxy.py`.
- Onboarding: an already-registered address is now refused **before** any camera sign-in (`services/onboarding.py`), so a repeat add can't spend the camera's login attempts. Test in `tests/integration/test_api_discovery.py`.
- **Resolved the CRITICAL finding from the previous handoff:** `nvr run` now starts the recorder. New `src/vizenlink_nvr/services/recorder.py` (`RecorderSupervisor`), started from the app lifespan only when `create_app(recorder_port=...)` is set (`nvr run` sets it; tests don't):
  - MediaMTX: own config `mediamtx/mediamtx-recorder.yml`, restarted if it exits (verified: kill -9 → back in ~10 s), adopts our own MediaMTX after a core restart (matched by `authHTTPAddress`), refuses a foreign process on the API port.
  - Reconcile every 30 s (schedules, storage health), creates default `continuous` recording settings for every active camera.
  - Outages via `OutageTracker` from MediaMTX `available`/`ready` (60 s grace).
  - Index scan at startup + every 30 min; janitor every 5 min; ONVIF PullPoint events with EVT-07 restamp (no auto-protection).
- Other real bugs fixed on the way:
  - New cameras never recorded (no RecordingSettings row → `should_record_now` False).
  - MediaMTX auth webhook returned 422 to every call (MediaMTX sends `null` fields) — `api/v1/auth.py` validator.
  - MediaMTX path case mismatch: reconciler used `cam/<serial lower>`, proxy/tokens/mobile used the stored serial. New `media/config.py::camera_path_name()` used everywhere; webhook compares lower-case; proxy rewrites the WHEP `Location` back to the caller's serial so viewer PATCH/DELETE pass `verify_camera_access`.
  - Segment hook ran `nvr` from PATH with the default data dir → now `<python> -m vizenlink_nvr recording hook-segment-complete --data-dir <dir>` (new `src/vizenlink_nvr/__main__.py`; frozen builds use the executable). Verified with `env -i`.
  - `/health` `mediamtx_ok` was hard-coded true → real recorder state.
  - `nvr run` never called `configure_logging()` → no app logs at all. Now called; httpx/httpcore set to WARNING.
  - Settings page on an offline camera: fail fast on the first read timeout instead of ~12 × 8 s.
  - Flaky `tests/integration/test_16camera_soak.py` (viewers raced recorders) fixed with per-camera events.
- Live smoke with a throwaway data dir (port 8811, stopped afterwards): MediaMTX up, path `cam/vzl-smoke-1/main` record=true with the absolute hook, settings row created, outage opened, hook indexed a segment.

## Decisions made (and why)
- MediaMTX API calls stay authenticated through the NVR webhook (control password) rather than `authHTTPExclude: [api]` as STACK.md suggests: stricter, and `tests/mediamtx/test_default_deny.py` expects anonymous API → 401. Works because the NVR is serving before MediaMTX finishes starting.
- With `--host` not loopback, only the WebRTC media UDP socket listens on the LAN (`webrtcLocalUDPAddress :8189`, `webrtcAdditionalHosts` = LAN IPv4 via ifaddr). Signalling/API/RTSP/HLS/playback stay loopback behind the authenticated NVR.
- Do not change `Camera.state` for reachability: `compute_desired_paths` only includes `active` cameras, so marking offline would delete the path and the camera would never come back. Outages go to `camera_outages` instead.
- Events are stored but not auto-protected: protection is only on explicit lock (REC-12); auto-protecting every motion event would block retention and fill the disk.
- Event snapshots left off: `EventSnapshotManager` uses Basic auth (cameras need Digest + self-signed TLS) and writes a placeholder JPEG on failure; better none than fake images.

## Current state
- Working: backend 550 passed / 1 skipped; `-m mediamtx` 9 passed (incl. new real-binary recorder test); ruff clean. Frontend unchanged this session (was 399/399, typecheck + gates green).
- **Nothing committed.** All of the owner's earlier work plus this session's fixes are in the working tree. Only this handoff is committed.
- Owner's NVRs on ports 8801 and 8802 (`data/real-nvr`) run old code; they must be restarted to record. Only one NVR per machine can own MediaMTX's default ports; the second will report "another program" on the API port.
- Not exercised with a real camera producing video.

## Next step
- Owner: restart `nvr run`, choose a writable storage folder (system disk needs "allow system disk"), add a real camera, confirm segments appear under `<storage>/cam/<serial>/main/...` and in Playback.
- Then commit the working tree (suggest splitting: owner's feature work vs. `fix(recorder): ...`).
- Then resume Phase 10 remaining items (see previous handoff: camera issue actions, profile sessions, evidence review, synced playback) and camera-settings parity steps 2-7.

## Open questions / waiting on
- Mobile live (`api/v1/mobile.py` live-stream): URLs point at `http://<host>:8889/...` but MediaMTX is loopback-only, and the HLS URL uses 8889 instead of 8888. Needs a decision: proxy through the NVR port (like web) or expose MediaMTX on the LAN.
- UI "online" badge still = registry `state == active`; should it use the new outage data?
- Event snapshots: port Digest/TLS snapshot fetch from `camera_api`, or keep off?
- Remove-camera bug from previous handoff still open (DELETE cascades footage even with keep_recordings=true).
