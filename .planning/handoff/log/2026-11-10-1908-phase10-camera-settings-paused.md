# Handoff — 2026-11-10 12:54 — phase10-ui-v2-progress

**Account/session:** Claude Code (VS Code), verification account — owner chose "build it here" for Phase 10
**GSD position:** Phase 10 (UI v2 - Old VMS Parity) in progress, built ad hoc in batches (no PLAN.md files). Phases 11-13 added to ROADMAP, not started.

## What this session did
- Committed the 114 uncommitted post-Phase-9 files as a snapshot (ef45bdc) before starting.
- Phase 10 batches (commits 2165f52, 48eca47, f230af8, e085f01, fa06859):
  - Old VMS look: blue palette (#0056D2/#64B5F6), light default, neutral dark, old nav order/names (Dashboard, Cameras, Alerts, Multiview, Playback, Gallery, Settings), header theme toggle + name/role. "/" is the Dashboard; Live moved to "/live".
  - Dashboard redesigned to my recommendation (owner said the old one was ad hoc): status banner, 4 KPIs, camera list problems-first with last-footage time, recent alerts, storage, system (CPU/memory only in technical view).
  - Honest status: shared evaluator src/vizenlink_nvr/web/src/lib/recorder-status.ts. Backend /health now checks real storage; alert "storage_unavailable"; /recording/status reports is_recording/last_segment_at from the gap watchdog; new GET /health/system (psutil added).
  - Multiview: CH numbers, empty channels, right-click menu (radix ContextMenu), drag-to-swap, grid fullscreen, fit-to-screen in landscape.
  - Responsive pass at 390/768/1280/1920/2560 px: no horizontal scroll; sidebar icon rail <1024px; root font scales on 2200px+.
  - Alerts: migration 0008_event_review; severity derived from event type (src/vizenlink_nvr/events/severity.py); acknowledge/resolve/reopen/acknowledge-all/hide APIs (audited); Alerts page filters + Acknowledge all; /events/:id details page.
  - Fixes: sidebar links all rendered accent colour (NavLink className function stringified by SidebarMenuButton asChild); removed stray legacy src/App.tsx that broke the build; Add Camera "Find cameras" was never rendered; design gates 37 -> 0.

## Decisions made (and why)
- "Remove alert" hides (hidden_at) and never deletes the event: events protect footage (REC-04); locked alerts can't be hidden (409).
- Kept backend classification "degraded" for storage failure (pinned by test); the UI treats storage_ok=false as "Not recording".
- PTZ, zone/privacy-mask drawing, two-way talk excluded: not in camera_api (owner confirmed skip). AI search/chat out of v1 scope.
- Per-zone dashboard widget toggles dropped in the redesign (clutter).
- Tablet sidebar breakpoint 1024px (jsdom reports 1024, real tablets 768-1023).

## Current state
- Working: all 372 frontend unit tests, 497 backend tests, design gates, OpenAPI backward-compatible.
- Owner's running NVR (PID started by owner, port 8000) was NOT restarted (auto-mode denied); backend changes apply after the owner restarts `nvr run`. Migration 0008 runs on startup.
- Owner's storage path /private/var/lib/vizenlink-nvr/recordings is unwritable (Permission denied) — UI now shows "Not recording"; owner must pick a writable folder. Not changed for them.
- Owner password for user "Gokul" was reset this session (directly in SQLite with the app's Argon2 hasher); owner told to change it.
- Preview instance used for screenshots: tools/e2e_serve.py on port 8767, data .e2e/phase10-preview (throwaway).

## Next step
- Phase 10 remaining: (1) camera issue page actions (retry/reboot/refresh stream/reduce quality) on /cameras/:serial/health; (2) Profile: active sessions list + log out other devices, default start page; (3) evidence review step after snapshot/clip; (4) multi-camera synced playback (PLAY-X1).
- Then Phases 11-13 (see ROADMAP scope blocks).

## CRITICAL finding (verification 2026-11-10)
- `nvr run` (and the systemd/launchd/WinSW services, which call `run`) starts ONLY the web/API server and mDNS.
  Nothing starts MediaMTX, the recording reconciler, segment indexing, the retention janitor, the gap watchdog,
  the event subscription supervisor, or camera reachability/outage tracking (OutageTracker.record_offline/online
  are only called from tests). On the owner's machine only port 8000 listens; no MediaMTX ports.
  => The product as launched records nothing and live view (WHEP) cannot work. Components exist and are unit
  tested; the runtime wiring (app lifespan supervisor) is missing. Recommended as the top priority before more UI.

## Open questions / waiting on
- Owner restart of the NVR and choice of storage folder.
- Phase 10 has no PLAN.md/SUMMARY.md; decide whether to backfill them for /gsd-verify-work.

## Update — camera settings parity (paused by owner, resume in ~2 hours)
Commits since the first handoff: alerts review workflow, contract pull (camera_api 2026-11-04 drop, 10/49 files, ported),
real camera 'Check connection', verification fixes, consistent camera online status, exposure/gain/white balance (cd302d1).

Camera settings parity plan (owner asked for old-VMS camera settings; only build what camera_api defines):
1. DONE: MAC on Details; exposure mode/time/gain + white balance (Image tab).
2. NEXT: CBR/VBR — port from onvif_video_encoder_client.dart (Media2 VideoEncoder2Configuration, RateControl
   ConstantBitRate attribute; options ConstantBitRateSupported). Python mirror: camera/onvif/media2.py.
3. OSD date format, font size (OsdOptions fontSizeMin/Max), font colour/transparency (osd_client.dart).
4. Detection tab: event preferences (PersonDetected/Loitering/Tamper), loitering duration, response actions
   (siren/spotlight/warning) — event_preferences_client.dart, loitering_duration_client.dart,
   event_response_actions_client.dart (not yet in the vendored inventory: add them to tools/vendor_contracts.py).
5. Privacy masks (mask_client.dart) + rectangle drawing UI.
6. Movement Protection (movement_protection_client.dart) + audio.
7. Run sim/fake_camera instances for the demo so the settings tabs load.
Blocked / owner decision: line crossing, intrusion zones, day/night time schedule, IR LED / Smart IR controls,
strobe — NOT in camera_api (checked whole package + REST spec); ask firmware/camera_api owner.
Bug to fix before any 'Remove camera' UI: DELETE /cameras/{serial} cascades segments/events/gallery even with
keep_recordings=true (orphans footage). Needs a soft 'removed' camera state.
Still the top priority overall: `nvr run` never starts MediaMTX/recorder services (see CRITICAL finding above).

Running at pause: demo VMS on http://localhost:8800 (owner demo / demo-password-123; data .e2e/demo, seeded by
scratchpad demo_seed.py with a 60 s segment feeder). Preview instance on 8767 stopped.
