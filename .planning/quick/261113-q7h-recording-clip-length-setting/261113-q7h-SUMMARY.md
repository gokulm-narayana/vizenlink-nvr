---
quick_id: 261113-q7h
status: complete
date: 2026-11-13
commit: none (working tree only)
---

# Summary: recorder-wide clip length setting

## Changed
- `services/settings.py`: `CLIP_MINUTES_KEY`, `CLIP_MINUTES_CHOICES` (1, 5, 10, 15, 30, 60), `read_clip_minutes` (default 1, unknown values fall back to 1).
- `media/reconciler.py`: `compute_desired_paths` sets `recordSegmentDuration` of each camera's main path from the setting (sub paths are not recorded and stay at 60 s). The running recorder picks it up on its next 30 s reconcile.
- `services/watchdog.py`: `check_camera_gaps` window defaults to 2 clips + 30 s from the setting (still 150 s at the default).
- `api/v1/recording.py`: new `GET /api/v1/recording/options` and `PUT /api/v1/recording/options` (422 for a length not offered; audit action `recording.update_options`). Additive: no existing route or payload changed.
- `web/src/features/settings/RecordingPage.tsx`: "Clip length" card at the top of Settings > Recording.
- Tests: `test_api_recording.py`, `test_reconciler_logic.py`, `test_gap_watchdog.py`, `settings.test.tsx`.

## Trade-offs the UI states
- A clip is indexed when it finishes, so with N-minute clips the newest footage can take up to N minutes to appear in Playback.
- A camera that stops recording is reported after about 2 clips, so longer clips mean later gap alarms (61 min at 30-minute clips). This weakens "never miss footage" detection; 1 minute stays the default.
- Crash loss is unchanged (`recordPartDuration` 1 s).

## Verified
- Backend 574 passed, 1 skipped; ruff clean on touched files. Vitest 439 passed; typecheck, gates, build OK.

## Not verified
- A running MediaMTX with real video after changing the setting (whether the path restart on change leaves a visible gap, and how long).
- `contracts/openapi_v1_baseline.json` was not regenerated; the two routes are additive.
