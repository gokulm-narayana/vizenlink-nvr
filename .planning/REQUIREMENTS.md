# Requirements: VizenLink NVR

**Defined:** 2026-10-26
**Core Value:** Never miss footage — every added camera records reliably 24/7 (plus events), and that footage is always findable on a timeline from both the web UI and the mobile app.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases. Feature IDs from `.planning/research/FEATURES.md` noted in brackets.

### Foundations

- [ ] **FND-01**: NVR runs as a supervised service where MediaMTX and the NVR core restart independently, so recording survives a core crash
- [ ] **FND-02**: NVR database (SQLite) is the single source of truth for cameras and recording config; MediaMTX state is reconciled from it at startup, on change, after MediaMTX restart, and periodically
- [ ] **FND-03**: All timestamps are stored as UTC with the NVR clock authoritative; times display in the site's configured IANA time zone, correct across DST changes
- [ ] **FND-04**: MediaMTX is configured default-deny (no anonymous publish/read/playback, control API on loopback only, unused protocols off)
- [ ] **FND-05**: Python camera layer mirrors `camera_api` contracts (typed Success/Failure/Timeout results, capability flags, camera-ID check, SOAP-fault handling) and is checked against them by contract tests and golden fixtures in CI
- [ ] **FND-06**: Same codebase runs on Linux (incl. Raspberry Pi 64-bit, Jetson), Windows and macOS

### Camera Onboarding

- [ ] **CAM-01**: User can scan the LAN (WS-Discovery) and see VizenLink/NuraEye cameras with model, name and IP [CAM-01]
- [ ] **CAM-02**: User can add a camera manually by IP/host when discovery is blocked [CAM-02]
- [ ] **CAM-03**: User sees a clear reason when adding fails (unreachable vs wrong credentials vs unsupported) [CAM-03]
- [ ] **CAM-04**: User is forced to change a camera's default password before it is added [CAM-04]
- [ ] **CAM-05**: NVR probes and caches each camera's capabilities at add time, with re-probe on demand [CAM-05]
- [ ] **CAM-06**: Adding a camera is atomic — a failure mid-add leaves no half-added camera, and the user can retry [CAM-06]
- [ ] **CAM-07**: NVR auto-selects main stream for recording and sub stream for grids from the camera's profiles [CAM-07]
- [ ] **CAM-08**: User can name a camera and give it a location label/group [CAM-08]
- [ ] **CAM-09**: User can remove a camera and choose to keep or delete its recordings [CAM-09]
- [ ] **CAM-10**: Cameras are identified by serial, and the NVR re-finds a camera whose IP changed (DHCP) without misfiling footage [CAM-13]

### Live View

- [ ] **LIVE-01**: User can watch a single camera live (WebRTC, HLS fallback) with fullscreen [LIVE-01]
- [ ] **LIVE-02**: User can view a multiview grid in 1×1, 2×2, 3×3, 4×4 layouts with pagination [LIVE-02]
- [ ] **LIVE-03**: Grid tiles use the sub stream; an enlarged tile switches to the main stream [LIVE-03]
- [ ] **LIVE-04**: Each tile shows its true state (connecting, live, offline) — never a frozen frame presented as live — and reconnects automatically [LIVE-04]
- [ ] **LIVE-05**: Tile controls: snapshot, maximize, mute, name overlay, recording indicator [LIVE-05]
- [ ] **LIVE-06**: User can arrange cameras into grid slots and the last layout is remembered [LIVE-06]
- [ ] **LIVE-07**: User can record a manual clip from live view (start/stop, auto-stop at max duration) into the gallery [LIVE-09]

### Recording & Storage

- [ ] **REC-01**: Each camera records 24/7 to fixed-length fMP4 segments with no remux step [REC-01]
- [ ] **REC-02**: User can set per-camera recording mode: Continuous / Event / Scheduled / Off [REC-02]
- [ ] **REC-03**: User can define a weekly recording schedule (days × time windows) [REC-03]
- [ ] **REC-04**: Event mode keeps footage around each event with configurable pre-roll and post-roll (default ~10 s each) [REC-04]
- [ ] **REC-05**: NVR enforces retention (N days and/or size cap), deleting oldest first; NVR is the only component that deletes footage [REC-06]
- [ ] **REC-06**: User can set retention per camera, with a storage estimate [REC-13]
- [ ] **REC-07**: When the disk fills, NVR overwrites oldest footage instead of stopping, keeping a hard free-space reserve [REC-07]
- [ ] **REC-08**: User can set the recording storage location; NVR refuses to record onto the system disk if the recording drive is missing [REC-08]
- [ ] **REC-09**: Every segment is indexed in the database, and the index is reconciled with the files on disk at startup and periodically [REC-09]
- [ ] **REC-10**: A dropped camera stream reconnects with backoff and recording resumes without manual action [REC-10]
- [ ] **REC-11**: User can toggle audio recording per camera (when the camera has a microphone) [REC-11]
- [ ] **REC-12**: User can lock recordings/events so retention never deletes them [REC-12]

### Playback & Export

- [ ] **PLAY-01**: User can view a per-camera 24 h timeline with recorded spans, gaps and event markers; click/drag to seek; zoom [PLAY-01]
- [ ] **PLAY-02**: Date picker shows which days have footage [PLAY-02]
- [ ] **PLAY-03**: Transport controls: play/pause, ±10 s skip, speed, mute, fullscreen [PLAY-03]
- [ ] **PLAY-04**: Playback continues across segment boundaries without a visible seam and skips over gaps [PLAY-04]
- [ ] **PLAY-05**: User can jump from an event straight to its recording (padded by pre-roll) [PLAY-05]
- [ ] **PLAY-06**: User can mark in/out on the timeline and export an MP4 clip [PLAY-06]
- [ ] **PLAY-07**: User can save a snapshot from a playback frame [PLAY-07]
- [ ] **PLAY-08**: Timeline distinguishes a recording outage gap from footage removed by retention [PLAY-09]

### Events

- [ ] **EVT-01**: NVR ingests camera events into its own persistent event index (v1 source: ONVIF PullPoint behind a pluggable event-source interface; NuraEye LAN feed slot reserved) [EVT-01, REC-05]
- [ ] **EVT-02**: User can see an event list with thumbnail, type, camera and time, and open any event in playback [EVT-02]
- [ ] **EVT-03**: User can filter events by camera, type and date range [EVT-03]
- [ ] **EVT-04**: An event snapshot is captured and stored at trigger time [EVT-04]
- [ ] **EVT-05**: User gets in-app live event notifications with an unread badge [EVT-05]
- [ ] **EVT-06**: NVR monitors each camera's event subscription (alive, last event time, auto-resubscribe) and warns when event-mode recording is at risk [EVT-06]
- [ ] **EVT-07**: Event times from a camera with an uncertain clock are re-stamped with NVR time [HEALTH-09]

### Camera Settings

- [ ] **SET-01**: User can edit device identity (name, location, time zone, password) and view model, firmware, serial [SET-01]
- [ ] **SET-02**: User can edit video encoder settings per stream within the camera's allowed ranges [SET-02]
- [ ] **SET-03**: User can edit imaging settings (brightness, contrast, day/night, IR, WDR, anti-flicker, mirror/flip, etc.) as the camera supports [SET-03]
- [ ] **SET-04**: User can configure OSD name and timestamp overlays [SET-04]
- [ ] **SET-05**: User can reboot a camera and see it reconnect [SET-05]
- [ ] **SET-06**: Owner/Admin can factory-reset a camera with double confirmation [SET-06]
- [ ] **SET-07**: User can view camera health (uptime, reboot reason, clock sync, firmware) [SET-10]
- [ ] **SET-08**: Settings screens only show options the camera's capabilities support, following `camera_api` semantics [CAM-05]

### Users & Access

- [ ] **AUTH-01**: First run walks the owner through creating the Owner account, time zone and storage location (no default credentials) [AUTH-01]
- [ ] **AUTH-02**: Users log in with local accounts (Argon2id hashes), can change their password, and repeated failures are rate-limited [AUTH-02]
- [ ] **AUTH-03**: Roles Owner/Admin, Operator and Viewer are enforced server-side on every API call and every video stream [AUTH-03]
- [ ] **AUTH-04**: Admin can add, edit, disable users and reset passwords [AUTH-05]
- [ ] **AUTH-05**: Admin can restrict a user to specific cameras [AUTH-07]
- [ ] **AUTH-06**: User can switch between Simple (default) and Advanced views; Simple hides advanced settings [AUTH-06]
- [ ] **AUTH-07**: Audit log records logins, failed logins, camera add/remove, setting changes, exports, deletions, and user/role changes [AUD-01]
- [ ] **AUTH-08**: User accounts can store a linked VizenLink (Cognito) identity (data model only; linking UI in v1.x) [AUTH-09]

### Health & Monitoring

- [ ] **HLTH-01**: Each camera shows two independent badges: online/offline and recording/not recording [HEALTH-01]
- [ ] **HLTH-02**: Dashboard summarizes cameras online, recording, issues, storage used, active alerts [HEALTH-02]
- [ ] **HLTH-03**: NVR flags any camera with no new segment within the expected window (recording gap watchdog) [HEALTH-03]
- [ ] **HLTH-04**: User sees disk usage, free space and estimated days of retention at the current bitrate [HEALTH-04]
- [ ] **HLTH-05**: Storage failures (full, unwritable, read-only, unmounted) show as critical, distinct from camera problems [HEALTH-05]
- [ ] **HLTH-06**: Recorder service health (API, MediaMTX, DB) is visible with a "recorder degraded" state [HEALTH-06]
- [ ] **HLTH-07**: User gets in-app alerts for camera offline > N minutes, disk nearly full and recording gaps [HEALTH-08]
- [ ] **HLTH-08**: User can see each camera's offline/recovery history (start, end, duration) [HEALTH-07]
- [ ] **HLTH-09**: User can see whether each camera's clock is synced or uncertain [HEALTH-09]

### Gallery & Search

- [ ] **GAL-01**: User can browse a snapshot gallery (from live and playback) filtered by camera, time and user [GAL-01]
- [ ] **GAL-02**: User can browse, preview, download and delete (with confirmation) manual and exported clips [GAL-02]
- [ ] **GAL-03**: User can search recordings by camera, date/time and event type and jump to the timeline [SRCH-01]

### Mobile Integration (LAN)

- [ ] **MOB-01**: NVR publishes a documented, versioned REST API (OpenAPI 3.1, `/api/v1`) with breaking-change checks in CI [MOB-01]
- [ ] **MOB-02**: Mobile app can find the NVR on the LAN via mDNS, or by manual IP [MOB-02]
- [ ] **MOB-03**: Mobile app pairs with the NVR via login or QR, with per-device tokens the admin can revoke [MOB-03, AUTH-04]
- [ ] **MOB-04**: Mobile app can watch live through the NVR relay, using the sub stream by default [MOB-04]
- [ ] **MOB-05**: Mobile app can browse days with footage and play NVR recordings [MOB-05]
- [ ] **MOB-06**: Mobile app can see NVR health and storage per camera [MOB-06]
- [ ] **MOB-07**: Mobile app can add/remove cameras and change recording mode, permission-gated [MOB-07]

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### Next release (v1.x)

- **CAM-X1**: Detect a camera claimed by another NVR and guide release/re-claim
- **CAM-X2**: Batch add of discovered cameras with per-camera results
- **LIVE-X1**: Named saved views; auto-sequence tours; digital zoom; viewer-limit messaging
- **PLAY-X1**: Multi-camera synchronized playback
- **PLAY-X2**: Export integrity manifest (SHA-256 + metadata), multi-clip zip, export job queue
- **EVT-X1**: Event review status; repetitive-event grouping; webhook/MQTT event output
- **SET-X1**: Privacy masks; event preferences and response actions; camera SD settings; bulk settings apply
- **AUTH-X1**: Active sessions list; VizenLink (Cognito) account link UI
- **HLTH-X1**: NVR NTP sanity warning; fleet health table; "recheck now"/restart camera
- **MOB-X1**: Live event stream to mobile; NVR-offline fallback; mobile-initiated export

### Later (v2)

- **REC-X1**: Back-fill gaps from camera SD card with dedup
- **REC-X2**: Mandatory recording by SKU class
- **EVT-X2**: Incident notes, status, assignment
- **AUTH-X2**: Time-bounded access grants
- **SET-X2**: Manual deterrence trigger (siren/spotlight)
- **HLTH-X2**: Disk SMART monitoring
- **SRCH-X1**: Daily digest

## Out of Scope

| Feature | Reason |
|---------|--------|
| Remote (off-LAN) access, push gateway | v1 is LAN only; mobile keeps its own camera/AWS paths off-LAN |
| Third-party / generic ONVIF cameras | VizenLink/NuraEye only for v1 |
| NVR-side AI analytics, rule authoring, chatbot | AI stays separate from the platform-independent core |
| Attribute search (gender, age) / behaviour scoring | Explicit product non-goal |
| PTZ controls | Not supported by target cameras in v1 |
| Two-way talk from web UI | Needs HTTPS mic permission; mobile already has it |
| Video wall / multi-monitor | Admin-console feature, not this product |
| Email/SMS/push notifications | LAN-only v1; in-app alerts only |
| Expiring share links, cloud gallery sync | Requires remote access |
| Motion-pixel recording triggers on NVR | Camera provides events |
| Transcoding on ingest | Kills low-end hardware; stream copy only |
| Firmware update orchestration, camera Wi-Fi provisioning | Owned by mobile app / camera tooling |
| Licensing / enforced camera limits | Deferred; v1 targets ~16 cameras unenforced |
| Mandatory MFA, SSO/LDAP | Not needed for home/small-business v1 |
| Infrastructure dashboards (CPU/GPU/threads) | Not user value |
| Kafka WebSocket feed (old VMS) | Not core NVR functionality |
| 32-bit Raspberry Pi (armv7) | Wheel availability unverified; 64-bit only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 2 | Pending |
| FND-02 | Phase 2 | Pending |
| FND-03 | Phase 1 | Pending |
| FND-04 | Phase 1 | Pending |
| FND-05 | Phase 1 | Pending |
| FND-06 | Phase 8 | Pending |
| CAM-01 | Phase 1 | Pending |
| CAM-02 | Phase 1 | Pending |
| CAM-03 | Phase 1 | Pending |
| CAM-04 | Phase 1 | Pending |
| CAM-05 | Phase 1 | Pending |
| CAM-06 | Phase 1 | Pending |
| CAM-07 | Phase 1 | Pending |
| CAM-08 | Phase 1 | Pending |
| CAM-09 | Phase 2 | Pending |
| CAM-10 | Phase 1 | Pending |
| LIVE-01 | Phase 3 | Pending |
| LIVE-02 | Phase 3 | Pending |
| LIVE-03 | Phase 3 | Pending |
| LIVE-04 | Phase 3 | Pending |
| LIVE-05 | Phase 3 | Pending |
| LIVE-06 | Phase 3 | Pending |
| LIVE-07 | Phase 5 | Pending |
| REC-01 | Phase 2 | Pending |
| REC-02 | Phase 2 | Pending |
| REC-03 | Phase 2 | Pending |
| REC-04 | Phase 4 | Pending |
| REC-05 | Phase 2 | Pending |
| REC-06 | Phase 2 | Pending |
| REC-07 | Phase 2 | Pending |
| REC-08 | Phase 2 | Pending |
| REC-09 | Phase 2 | Pending |
| REC-10 | Phase 2 | Pending |
| REC-11 | Phase 2 | Pending |
| REC-12 | Phase 5 | Pending |
| PLAY-01 | Phase 5 | Pending |
| PLAY-02 | Phase 5 | Pending |
| PLAY-03 | Phase 5 | Pending |
| PLAY-04 | Phase 5 | Pending |
| PLAY-05 | Phase 5 | Pending |
| PLAY-06 | Phase 5 | Pending |
| PLAY-07 | Phase 5 | Pending |
| PLAY-08 | Phase 5 | Pending |
| EVT-01 | Phase 4 | Pending |
| EVT-02 | Phase 4 | Pending |
| EVT-03 | Phase 4 | Pending |
| EVT-04 | Phase 4 | Pending |
| EVT-05 | Phase 4 | Pending |
| EVT-06 | Phase 4 | Pending |
| EVT-07 | Phase 4 | Pending |
| SET-01 | Phase 6 | Pending |
| SET-02 | Phase 6 | Pending |
| SET-03 | Phase 6 | Pending |
| SET-04 | Phase 6 | Pending |
| SET-05 | Phase 6 | Pending |
| SET-06 | Phase 6 | Pending |
| SET-07 | Phase 6 | Pending |
| SET-08 | Phase 6 | Pending |
| AUTH-01 | Phase 3 | Pending |
| AUTH-02 | Phase 3 | Pending |
| AUTH-03 | Phase 3 | Pending |
| AUTH-04 | Phase 3 | Pending |
| AUTH-05 | Phase 3 | Pending |
| AUTH-06 | Phase 3 | Pending |
| AUTH-07 | Phase 3 | Pending |
| AUTH-08 | Phase 3 | Pending |
| HLTH-01 | Phase 2 | Pending |
| HLTH-02 | Phase 3 | Pending |
| HLTH-03 | Phase 2 | Pending |
| HLTH-04 | Phase 2 | Pending |
| HLTH-05 | Phase 2 | Pending |
| HLTH-06 | Phase 2 | Pending |
| HLTH-07 | Phase 3 | Pending |
| HLTH-08 | Phase 3 | Pending |
| HLTH-09 | Phase 4 | Pending |
| GAL-01 | Phase 5 | Pending |
| GAL-02 | Phase 5 | Pending |
| GAL-03 | Phase 5 | Pending |
| MOB-01 | Phase 3 | Pending |
| MOB-02 | Phase 7 | Pending |
| MOB-03 | Phase 7 | Pending |
| MOB-04 | Phase 7 | Pending |
| MOB-05 | Phase 7 | Pending |
| MOB-06 | Phase 7 | Pending |
| MOB-07 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 85 total
- Mapped to phases: 85
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-26*
*Last updated: 2026-10-26 after roadmap creation (traceability mapped)*
