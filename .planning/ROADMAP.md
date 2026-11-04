# Roadmap: VizenLink NVR

## Overview

The NVR is built recorder-first. Phase 1 lays a locked-down, contract-tested foundation and onboards cameras by serial; Phase 2 delivers the core value headless: 24/7 fMP4 recording that is reconciled, indexed, retained, guarded against disk failures and watched for gaps, all proven before anything is exposed to the LAN. Phase 3 is the first LAN exposure and ships auth (including MediaMTX media auth), the versioned `/api/v1`, the React web app and live view together. Phases 4 and 5 make footage findable: camera events that protect the footage around them, then timeline playback, export, gallery and search. Phase 6 adds capability-gated camera settings matching `camera_api`. Phase 7 brings the VizenLink mobile app onto the NVR over the LAN, and Phase 8 packages the NVR as a service on every target platform and proves "never miss footage" with a 16-camera soak.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundations & Camera Onboarding** - Secure, contract-tested base; cameras discovered, verified and registered by serial (headless)
- [x] **Phase 2: Headless Recording Core** - 24/7 fMP4 recording with reconciler, segment index, retention janitor, gap watchdog and storage guard
- [x] **Phase 3: Secure API, Auth & Live View** - First LAN exposure: accounts and roles, media auth, `/api/v1`, React web app, live grid, health overview
- [ ] **Phase 4: Events & Event Recording** - Camera events ingested, protecting footage around them, listed, filtered and notified
- [ ] **Phase 5: Playback, Export & Gallery** - Timeline playback, event jump, clip export, snapshots, gallery and recordings search
- [ ] **Phase 6: Camera Settings** - Capability-gated camera configuration that behaves exactly like `camera_api`
- [ ] **Phase 7: Mobile LAN Integration** - Mobile app finds, pairs with and uses the NVR for live, recordings, health and management
- [ ] **Phase 8: Cross-Platform Packaging & Soak** - Installable service on every target platform, proven by a 16-camera soak

## Phase Details

### Phase 1: Foundations & Camera Onboarding
**Goal**: The NVR runs on a locked-down, contract-tested foundation and can find, verify and register VizenLink/NuraEye cameras by serial; headless, driven from a local admin CLI on loopback, with nothing exposed to the LAN
**Depends on**: Nothing (first phase)
**Requirements**: FND-03, FND-04, FND-05, CAM-01, CAM-02, CAM-03, CAM-04, CAM-05, CAM-06, CAM-07, CAM-08, CAM-10
**Success Criteria** (what must be TRUE):
  1. From the local admin CLI, the owner can scan the LAN and see VizenLink/NuraEye cameras with model, name and IP, and can add a camera manually by IP/host when discovery is blocked
  2. A failed add tells the owner whether the camera was unreachable, the credentials were wrong or the device is unsupported; a camera still on its default password cannot be added until its password is changed; an add that fails midway leaves no half-added camera and can simply be retried
  3. Each added camera is registered by serial with its name, location label, cached capabilities (re-probed on demand) and an auto-selected main stream for recording and sub stream for grids; after a DHCP IP change the NVR re-finds the camera under the same identity instead of creating a duplicate
  4. MediaMTX runs from an NVR-generated default-deny config: anonymous publish, read and playback attempts are rejected, its control API answers only on loopback, and RTMP, SRT and MoQ are disabled
  5. CI on Linux, macOS and Windows passes contract tests and golden fixtures showing the Python camera layer returns the same typed Success/Failure/Timeout results, capability flags, camera-ID check outcomes and SOAP-fault handling as `camera_api`; timestamps are stored as UTC and render correctly in the site time zone on both sides of a DST change
**Plans**: 31 plans (revised; all fewer than 15 files)

Plans:
- [ ] 01-01-PLAN.md — Dependency review, package lock, configuration and clock primitives (wave 1)
- [ ] 01-02-PLAN.md — Migrated SQLite, runtime and shared status service (wave 2)
- [ ] 01-03-PLAN.md — CLI status tracer, reusable command seams and listener guard (wave 3)
- [ ] 01-04-PLAN.md — UTC storage, site timezone and DST transitions (wave 4)
- [ ] 01-05-PLAN.md — Typed camera core, HTTP transport, WSSE and identity client (wave 5)
- [ ] 01-06-PLAN.md — Loopback TLS simulator and identity tracer (wave 6)
- [ ] 01-07-PLAN.md — HTTP faults, simulator authority, discovery responder and architecture guards (wave 7)
- [ ] 01-08-PLAN.md — Encrypted credential vault and authoritative canary key source (wave 5)
- [ ] 01-09-PLAN.md — Pinned MediaMTX binary and explicit loopback default-deny config (wave 8)
- [ ] 01-10-PLAN.md — Live MediaMTX rejection probes and process cleanup (wave 9)
- [ ] 01-11-PLAN.md — Read-only vendoring and drift tools with bounded batch mode (wave 5)
- [ ] 01-12-PLAN.md — Vendor immutable contract batch 1 of 5 (wave 6)
- [ ] 01-13-PLAN.md — Vendor immutable contract batch 2 of 5 (wave 7)
- [ ] 01-14-PLAN.md — Vendor immutable contract batch 3 of 5 (wave 8)
- [ ] 01-15-PLAN.md — Vendor immutable contract batch 4 of 5 (wave 9)
- [ ] 01-16-PLAN.md — Vendor immutable contract batch 5 of 5 (wave 10)
- [ ] 01-17-PLAN.md — Finalize full contract lock, behavior catalogue and fixture provenance (wave 11)
- [ ] 01-18-PLAN.md — REST login and authenticated capabilities tracer (wave 12)
- [ ] 01-19-PLAN.md — REST sessions, failure taxonomy and identity retry (wave 13)
- [ ] 01-20-PLAN.md — Capabilities and live-stream URI contracts (wave 14)
- [ ] 01-21-PLAN.md — ONVIF serial tracer and fault-first SOAP mapping (wave 12)
- [ ] 01-22-PLAN.md — ONVIF device operations and Media2 streams (wave 13)
- [ ] 01-23-PLAN.md — Blank-credential discovery, bounded unicast and scan CLI (wave 15)
- [ ] 01-24-PLAN.md — D-11 confirmation, serial registry schema and stream selection (wave 15)
- [ ] 01-25-PLAN.md — Serial-bound configured-camera onboarding and local CLI (wave 16)
- [ ] 01-26-PLAN.md — Stream fallback, capability cache and registry display (wave 17)
- [ ] 01-27-PLAN.md — One-shot factory flow, error taxonomy and atomic add (wave 18)
- [ ] 01-28-PLAN.md — Silent serial-based re-IP recovery (wave 18)
- [ ] 01-29-PLAN.md — Rename, reprobe, credentials and certificate recovery (wave 19)
- [ ] 01-30-PLAN.md — Opt-in real-camera suite and blocking hardware checkpoint (wave 20)
- [ ] 01-31-PLAN.md — Local phase gate, pending OS matrix, leaks and packaging guards (wave 20)

**Pending gate**: Three-OS CI cannot run with no remote. tools/phase_gate.py supplies local evidence only; this work must not create a remote or mark the phase verified.

**Research**: Needed for the camera layer on real hardware: case-preserving HTTP client, WSSE clock-skew tolerance, non-admin streaming account, RTSPS concurrency (3 clients per stream), RTSP behaviour with WEBRTC_STREAMING enabled. Foundations work is a standard pattern.

### Phase 2: Headless Recording Core
**Goal**: Every added camera records 24/7, and that footage is indexed, retained, protected from disk failures and watched for gaps; proven headless (local CLI and loopback only) before anything is exposed to the LAN. This is the core-value slice.
**Depends on**: Phase 1
**Requirements**: FND-01, FND-02, CAM-09, REC-01, REC-02, REC-03, REC-05, REC-06, REC-07, REC-08, REC-09, REC-10, REC-11, HLTH-01, HLTH-03, HLTH-04, HLTH-05, HLTH-06
**Success Criteria** (what must be TRUE):
  1. Every added camera records continuously into fixed-length fMP4 segments that play with no remux step; killing the NVR core leaves MediaMTX recording, and after any restart (core, MediaMTX or host) recording paths are rebuilt from the database with no manual action
  2. A camera whose stream drops (including a camera reboot or DHCP IP change) reconnects with backoff and resumes recording into the same camera's history; a camera with no new segment inside the expected window is flagged as not recording, independently of whether it is online
  3. Per-camera recording mode (Continuous / Event / Scheduled / Off), weekly schedule, audio on/off and retention (days and/or size, with a storage estimate) can be set from the CLI and take effect; only the NVR deletes footage, oldest first, and a filling disk overwrites the oldest footage while keeping a hard free-space reserve instead of stopping
  4. Every segment appears in the database index, and after files are added, removed or truncated behind the NVR's back (including a hard power-off) the startup and periodic scans bring the index back in line with what is on disk; removing a camera honours the owner's keep-or-delete choice for its recordings
  5. When the recording drive is missing, unmounted, read-only or full, the NVR refuses to record onto the system disk and reports a critical storage state distinct from camera problems; the status CLI shows disk usage, free space, estimated days of retention, and a "recorder degraded" state whenever the API, MediaMTX or the database is unhealthy
**Plans**: 8 plans

Plans:
- [x] 02-01-PLAN.md — Schema migration 0003 and core recording data models (wave 1)
- [x] 02-02-PLAN.md — Storage safeguards, system drive guard, and telemetry (wave 2)
- [x] 02-03-PLAN.md — Recording modes, weekly schedule engine, and audio toggle (wave 3)
- [x] 02-04-PLAN.md — Declarative MediaMTX reconciler and process supervision (wave 4)
- [x] 02-05-PLAN.md — Two-source segment indexing: real-time hook and disk scanner (wave 5)
- [x] 02-06-PLAN.md — Retention janitor engine, low-water mark pruning, and camera removal (wave 6)
- [x] 02-07-PLAN.md — Recording gap watchdog, stream reconnect backoff, and health badges (wave 7)
- [x] 02-08-PLAN.md — Headless recording pipeline end-to-end tracer and local phase gate (wave 8)
**Research**: Needed (spikes): fMP4 power-loss behaviour (10 hard kills) and a 24 h recording on a real camera; recordPath %s vs %z in the playback lookup; MediaMTX playback `/get` across gaps and seeks (decides the Phase 5 playback approach); MediaMTX restart with API-created paths; segment-hook helper on Windows/macOS (no shell strings); slow USB disk; janitor-only-deletion test.

### Phase 3: Secure API, Auth & Live View
**Goal**: The NVR is safely usable from a browser on the LAN: the owner sets it up, users sign in with role-enforced access to every API call and video stream, watch cameras live, and see recorder health at a glance
**Depends on**: Phase 2
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06, MOB-01, HLTH-02, HLTH-07, HLTH-08
**Success Criteria** (what must be TRUE):
  1. On first run the owner is walked through creating the Owner account, the site time zone and the storage location (no default credentials exist); users then sign in with local accounts, can change their password, and repeated failed logins are rate-limited
  2. Owner/Admin, Operator and Viewer roles and per-user camera restrictions are enforced server-side on every `/api/v1` call and every MediaMTX video stream, so unauthenticated or out-of-scope requests are refused; admins can add, edit and disable users and reset passwords; logins, failed logins, camera add/remove, setting changes, exports, deletions and user/role changes all appear in the audit log
  3. User can watch one camera live over WebRTC (HLS fallback) in fullscreen, or a paginated 1×1/2×2/3×3/4×4 grid on sub streams where an enlarged tile switches to the main stream; every tile shows connecting/live/offline truthfully and reconnects on its own, tile controls (snapshot, maximize, mute, name overlay, recording indicator) work, and the arranged layout is remembered
  4. The dashboard summarizes cameras online, recording, issues, storage used and active alerts, with separate online and recording badges per camera and each camera's offline/recovery history; in-app alerts fire for a camera offline longer than N minutes, a nearly full disk and recording gaps; the owner can add cameras and set recording modes in the web app, and Simple view (the default) hides advanced settings that Advanced view reveals
  5. `/api/v1` is published as a versioned OpenAPI 3.1 document, the web app uses a client generated from it, and CI fails on a breaking API change; a user account can hold a linked VizenLink (Cognito) identity in the data model
**Plans**: 8 plans

Plans:
- [x] 03-01-PLAN.md — Schema migration 0004, auth models, and Argon2id password hashing (wave 1)
- [x] 03-02-PLAN.md — First-run setup wizard, session authentication, and brute-force rate-limiting (wave 2)
- [x] 03-03-PLAN.md — Server-side RBAC dependencies and user management API (wave 3)
- [x] 03-04-PLAN.md — MediaMTX HTTP media auth webhook and signed media tokens (wave 4)
- [x] 03-05-PLAN.md — Core /api/v1 REST endpoints and OpenAPI 3.1 breaking-change guard (wave 5)
- [x] 03-06-PLAN.md — Persistent audit logging, camera outage tracking, and in-app alerts (wave 6)
- [x] 03-07-PLAN.md — React SPA, live multiview grid (1x1 to 4x4), and WHEP/HLS player (wave 7)
- [x] 03-08-PLAN.md — Health dashboard, Simple vs Advanced view toggle, and end-to-end tracer (wave 8)
**UI hint**: yes
**Research**: Needed (spikes): MediaMTX authMethod jwt vs http, including media-token renewal before expiry; multi-NIC WebRTC with UDP blocked; WebRTC load at 16 sessions; H.265 browser support matrix.

### Phase 4: Events & Event Recording
**Goal**: Camera events become persistent NVR events that protect the footage around them, and users can find, filter, open and be notified about them
**Depends on**: Phase 3
**Requirements**: EVT-01, EVT-02, EVT-03, EVT-04, EVT-05, EVT-06, EVT-07, REC-04, HLTH-09
**Success Criteria** (what must be TRUE):
  1. Events from each camera (ONVIF PullPoint in v1, behind a pluggable event-source interface with a reserved NuraEye LAN slot) land in the NVR's own event index with a snapshot captured at trigger time, and remain there across NVR restarts
  2. A camera in Event mode keeps footage from the configured pre-roll before to the post-roll after each event (default about 10 s each), while unprotected footage outside events is reclaimed by retention
  3. User sees an event list with thumbnail, type, camera and time, filters it by camera, type and date range, opens any event to play its recorded footage, and gets live in-app event notifications with an unread badge
  4. For each camera the user can see whether its event subscription is alive and when its last event arrived; the NVR auto-resubscribes after drops and camera reboots, and warns when event-mode recording is at risk
  5. User can see whether each camera's clock is synced or uncertain, and events from a camera with an uncertain clock carry NVR time instead of the camera's time
**Plans**: TBD
**UI hint**: yes
**Research**: Needed, highest priority: confirm with the firmware owner whether a NuraEye LAN alert feed exists (PullPoint is the default either way); 24 h PullPoint capture on real hardware; power-cycle and resubscribe behaviour; event rates and queue overflow.

### Phase 5: Playback, Export & Gallery
**Goal**: Any recorded moment can be found and used in under a minute: users scrub a timeline, jump from events, export clips, save snapshots and search recordings
**Depends on**: Phase 4
**Requirements**: PLAY-01, PLAY-02, PLAY-03, PLAY-04, PLAY-05, PLAY-06, PLAY-07, PLAY-08, GAL-01, GAL-02, GAL-03, LIVE-07, REC-12
**Success Criteria** (what must be TRUE):
  1. User picks a camera and a day (the date picker marks days with footage) and sees a zoomable 24 h timeline of recorded spans, gaps and event markers, with outage gaps visibly different from footage removed by retention; clicking or dragging seeks
  2. Playback offers play/pause, ±10 s skip, speed, mute and fullscreen, continues across segment boundaries without a visible seam, and skips over gaps
  3. User can jump from an event straight to its recording (padded by pre-roll), mark in/out to export an MP4 clip, save a snapshot from a playback frame, record a manual clip from live view (start/stop, auto-stop at max duration), and lock recordings or events so retention never deletes them
  4. User can browse the snapshot gallery filtered by camera, time and user, and browse, preview, download and delete (with confirmation) manual and exported clips
  5. User can search recordings by camera, date/time and event type and land on the matching spot in the timeline
**Plans**: TBD
**UI hint**: yes
**Research**: Needed (builds on the Phase 2 playback spike): seeking without range support; Safari/iOS fMP4 playback; MP4 export via MediaMTX `/get?format=mp4` with temp-then-rename; self-built HLS VOD as fallback if `/get` across gaps proves unworkable.

### Phase 6: Camera Settings
**Goal**: Users configure each camera from the NVR exactly as the mobile app would, seeing only the options that camera actually supports
**Depends on**: Phase 3, Phase 4
**Requirements**: SET-01, SET-02, SET-03, SET-04, SET-05, SET-06, SET-07, SET-08
**Success Criteria** (what must be TRUE):
  1. User can view a camera's model, firmware and serial and edit its name, location, time zone and password; each change is recorded in the audit log
  2. User can edit per-stream video encoder settings within the camera's allowed ranges, imaging settings (brightness, contrast, day/night, IR, WDR, anti-flicker, mirror/flip) and OSD name and timestamp overlays, and the camera reflects each change
  3. Settings screens show only the options the camera's capability flags support, with values and validation following `camera_api` semantics, so the same camera behaves identically from the NVR and the mobile app
  4. User can reboot a camera and watch it go offline and come back with recording resumed; only Owner/Admin can factory-reset a camera, and only after a double confirmation
  5. User can view camera health: uptime, last reboot reason, clock sync status and firmware
**Plans**: TBD
**UI hint**: yes
**Research**: Standard pattern (`SETTINGS_API_GUIDE`); skip the research phase.

### Phase 7: Mobile LAN Integration
**Goal**: The VizenLink mobile app on the same LAN can find the NVR, pair with it, and use it for live view, recorded history, health and camera management
**Depends on**: Phase 5
**Requirements**: MOB-02, MOB-03, MOB-04, MOB-05, MOB-06, MOB-07
**Success Criteria** (what must be TRUE):
  1. The mobile app discovers the NVR on the LAN via mDNS (with the API version advertised), or connects to it by manual IP
  2. The mobile app pairs by login or by scanning a QR code shown by the NVR and receives a per-device token; an admin can see paired devices and revoke one, after which that device is refused
  3. The mobile app watches any camera live through the NVR relay on the sub stream by default, browses the days that have footage and plays NVR recordings
  4. The mobile app shows NVR health and per-camera recording and storage status, and lets permitted users add/remove cameras and change recording mode, while users without that permission are refused server-side
**Plans**: TBD
**UI hint**: yes
**Research**: Moderate: Dart client for OpenAPI 3.1 (codegen spike vs a thin hand-written client); mobile TLS posture on the LAN; Flutter video_player with NVR recordings; recordings list shape agreed with the mobile app owner.

### Phase 8: Cross-Platform Packaging & Soak
**Goal**: The NVR installs and runs as a supervised system service on every target platform and is proven to never miss footage at target scale
**Depends on**: Phase 7
**Requirements**: FND-06
**Success Criteria** (what must be TRUE):
  1. The same release installs and runs as a boot-time service on Linux (PC, Raspberry Pi 64-bit with a USB SSD, Jetson), Windows and macOS, with a pinned MediaMTX binary for each OS/architecture and the web app bundled
  2. A 16-camera soak on mid-range hardware with two concurrent viewers shows zero recording gaps on healthy cameras, and hard power-offs, recording-drive unplug/replug and MediaMTX or core crashes all recover with no manual action
  3. Upgrading to a new release preserves cameras, users, settings and recordings, and the database can be backed up and restored
  4. On Windows and macOS the host does not sleep while the NVR is recording, required firewall ports are opened or clearly stated by the installer, and the supported camera count per hardware class is measured and published
**Plans**: TBD
**Research**: Needed: WinSW vs pywin32 service wrapper; macOS codesigning and notarization; Pi and Jetson capacity at 16 cameras; USB hot-unplug behaviour per OS; antivirus exclusions on Windows.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Phase 6 depends only on Phases 3 and 4, so it can run in parallel with Phase 5 if desired.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundations & Camera Onboarding | 0/31 | Planned | - |
| 2. Headless Recording Core | 0/TBD | Not started | - |
| 3. Secure API, Auth & Live View | 0/TBD | Not started | - |
| 4. Events & Event Recording | 0/TBD | Not started | - |
| 5. Playback, Export & Gallery | 0/TBD | Not started | - |
| 6. Camera Settings | 0/TBD | Not started | - |
| 7. Mobile LAN Integration | 0/TBD | Not started | - |
| 8. Cross-Platform Packaging & Soak | 0/TBD | Not started | - |
