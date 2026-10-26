# Feature Landscape

**Domain:** LAN network video recorder (NVR/VMS) for VizenLink/NuraEye IP cameras; home (2-8 cameras) and community/small business (8-32 cameras, target ~16 on mid-range hardware)
**Researched:** 2026-10-26
**Overall confidence:** MEDIUM-HIGH (internal sources HIGH; competitor feature sets MEDIUM, from docs and release notes via web search plus domain knowledge)

## How to read this document

- Feature IDs (`CAM-01`, `LIVE-03`, ...) are stable handles for requirements definition.
- **Complexity:** Low (days), Med (1-2 weeks), High (multi-week or needs spikes).
- **Tier tags:** `TS` = table stakes (missing, and users leave), `DF` = differentiator, `AF` = anti-feature (deliberately not built in v1).
- **Target:** `v1` = the first shippable NVR, `v1.x` = fast follow, `v2` = later milestone.
- Evidence tags: `[OLD]` = exists in the old VMS (`nuraeye-rt/vms`); `[CAM]` = backed by `camera_api` / `SETTINGS_API_GUIDE.md`; `[SEED]` = in the product-vision seed doc or the `vms-*` scenarios; `[MKT]` = seen in Frigate, UniFi Protect, Synology Surveillance Station, Blue Iris, or Hikvision/Dahua-class NVRs.

## Findings that change the plan (read first)

1. **The old VMS retention UI looks cosmetic.** `settings.html` has Retention Days, Disk Overwrite Threshold and an overwrite checkbox, and they are saved to `nuraeye_user_data.json`. A grep of `python/*.py` and `main.py` found no code that reads them or deletes old segments. Treat retention enforcement as a build-from-scratch feature. Core Value ("never miss footage") depends on disk-full handling being correct.
2. **Camera-side event correlation is unreliable for an NVR.** The camera's alert history is a 100-entry RAM ring buffer that does not survive reboot (SETTINGS_API_GUIDE, Recordings). The NVR must keep its own persistent event index and link events to its own segments. It must not lean on the camera's `trigger` field.
3. **Cameras already record to SD and expose a REST clip list, date summary, and download.** This enables a feature no generic NVR has: back-filling NVR gaps from camera SD (the idea behind Synology "Edge Recording"). It also creates a duplicate-footage problem (FEAT-044), so the NVR copy must be authoritative.
4. **The old VMS search view filters on gender and age.** The seed doc lists age and gender classification as a non-goal, and PROJECT.md puts AI out of scope. Do not port that part of search.
5. **LAN-only v1 makes some "standard" features low value.** Expiring share links, push notifications, and remote access all assume a reachable audience. See Anti-Features.
6. **Mobile playback has a known constraint.** The camera's self-signed HTTPS cert broke native `video_player` streaming (BUG-004), so the mobile app downloads then plays. The NVR must serve Range-capable MP4/HLS, and its TLS story needs a decision, or the mobile app inherits the same workaround.
7. **Camera clocks are untrustworthy.** Cameras have no battery-backed RTC and report `clock_sync_state` (`synced` or `uncertain`). Index segments by NVR receipt time and flag camera clock drift. The timeline must never silently trust camera timestamps.

---

## 1. Camera onboarding

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| CAM-01 | WS-Discovery LAN scan listing VizenLink/NuraEye cameras (model, name, IP) with "Add" | TS | Low | v1 | `[OLD]` `ws_discovery_scanner.py`, `/discovery/start,stop,status`. Port it. `[SEED]` FEAT-162 wants zero-config add. |
| CAM-02 | Manual add by IP/host (HTTP/HTTPS toggle) as fallback when multicast is blocked | TS | Low | v1 | `[OLD]` has `addManually`. VLANs and Wi-Fi isolation break WS-Discovery often. |
| CAM-03 | Credential entry plus connection test with a clear failure reason (unreachable vs. bad credentials vs. unsupported) | TS | Low | v1 | `[OLD]` has auth modal and retry. Reuse typed errors from `camera_api` semantics. |
| CAM-04 | Detect default camera credentials and force or strongly prompt a password change | TS | Low | v1 | `[OLD]` "Security Action Required" flow. Keep. Cheap and high trust value. Maps to `[CAM]` Device Identity (password). |
| CAM-05 | Capability probe at add time (`GetCapabilities`: `localStorageCapable`, `supportedRecordingModes`, `supportedEventTypes`, `osdSupported`, `maskSupported`, `hasSpeaker`...) cached per camera, with re-probe on demand | TS | Med | v1 | `[CAM]` Capabilities. Drives every later settings screen. Re-probe is needed (the SD-capability staleness bug is documented). |
| CAM-06 | Atomic add with no half-added state: if the camera drops mid-pairing, roll back or mark it clearly and allow retry | TS | Med | v1 | `[SEED]` SCN-584. Needs transactional registration (camera config, MediaMTX path, DB row). |
| CAM-07 | Auto-discover stream profiles (High/Medium/Low) and pick main stream for recording and sub stream for grid by default | TS | Med | v1 | `[CAM]` Video Encoder (three profiles). Feeds LIVE and REC. |
| CAM-08 | Camera naming, location label, and grouping (zone or site tags) | TS | Low | v1 | `[CAM]` Device Identity. Groups are required for bulk actions at 16+ cameras. |
| CAM-09 | Remove camera with choice: keep or delete its recordings | TS | Low | v1 | `[OLD]` `/camera/unregister`. Add the keep/delete decision (the old one is ambiguous). |
| CAM-10 | Detect a camera already claimed by another NVR; guided release or re-claim | DF | Med | v1.x | `[SEED]` SCN-583. Needs a claim marker on the camera. This may require camera-side support, so confirm with the owner (camera_api changes need explicit confirmation). |
| CAM-11 | Batch add of multiple discovered cameras with per-camera result and retry-failed-only | DF | Med | v1.x | `[SEED]` FEAT-167. Matters for the community tier (8-32 cameras). |
| CAM-12 | Bulk naming template (prefix plus sequence or location list) | DF | Low | v1.x | `[SEED]` SCN-598. |
| CAM-13 | Resolve changed camera IPs automatically (DHCP renumbering) by MAC or UUID via re-discovery | DF | Med | v1.x | `[OLD]` has `get_mac`. This is a top real-world cause of "camera offline" on home LANs. Strong reliability payoff for the Core Value. |
| CAM-14 | QR or label-assisted add | DF | Low | v2 | `[SEED]` FEAT-160 is a mobile-side feature. Not needed for the NVR web UI. |
| CAM-15 | Third-party/generic ONVIF camera support | AF | - | never in v1 | Explicitly out of scope in PROJECT.md. |

**Dependencies:** CAM-01/02 -> CAM-03 -> CAM-05 -> CAM-07 -> (REC, LIVE). CAM-06 wraps the whole chain. CAM-11 requires CAM-06 to be idempotent.

---

## 2. Live view and multiview

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| LIVE-01 | Single-camera live view via MediaMTX relay (WebRTC preferred, HLS fallback), with fullscreen | TS | Med | v1 | `[OLD]` `getWebRtcUrlForLayout`. The relay means one camera connection serves many viewers. This also sidesteps the camera's concurrent-viewer limit (FEAT-142). |
| LIVE-02 | Multiview grid with 1x1, 2x2, 3x3, 4x4 layouts and pagination | TS | Med | v1 | `[OLD]` multiview-controller (layouts 1/4/9/16, pagination). Matches `[SEED]` FEAT-046. |
| LIVE-03 | Automatic sub-stream in grid, main stream when a tile is enlarged | TS | Med | v1 | Required to hit ~16 cameras on mid-range hardware and browser decode limits. `[CAM]` has the Low/Medium profiles. Drives the CAM-07 default. |
| LIVE-04 | Per-tile state: connecting, live, offline (never a frozen last frame shown as live), auto-reconnect | TS | Med | v1 | `[SEED]` SCN-161, FEAT-122 freshness (Live/Delayed/Last Known/Unavailable). Cheap to design in, painful to retrofit. |
| LIVE-05 | Tile controls: snapshot, maximize, mute, camera name overlay, recording indicator | TS | Low | v1 | `[OLD]` tile context menu (snapshot, change camera, fullscreen). |
| LIVE-06 | Drag or select cameras into grid slots; remember last layout | TS | Low | v1 | `[OLD]` has assign-camera modal. |
| LIVE-07 | Named saved views ("Front of house", "Parking") | DF | Low | v1.x | Hikvision/Dahua "views". Cheap and valuable for the community tier. |
| LIVE-08 | Auto-sequence (tour) through camera pages | DF | Low | v1.x | `[MKT]` standard on professional NVR UIs and security-room workflows. |
| LIVE-09 | Manual clip record from live (start/stop, auto-stop max duration) saved to gallery | DF | Med | v1 | `[OLD]` `camera_live_stream_clip_start/stop`. `[SEED]` FEAT-045. See GAL-02. |
| LIVE-10 | Digital zoom (client-side pan and zoom on the video element) | DF | Low | v1.x | `[SEED]` FEAT-011. Do client-side only; do not call camera settings. |
| LIVE-11 | Viewer-count and "limit reached" messaging | DF | Low | v1.x | `[SEED]` FEAT-142. Mostly moot if all viewers go through the relay. |
| LIVE-12 | Day/night and privacy-mode state badges on tile | DF | Low | v2 | Needs polling or events from camera. Nice, not core. |
| LIVE-13 | PTZ controls | AF | - | not v1 | No PTZ appears in `camera_api` or SETTINGS_API_GUIDE. Do not build speculatively. |
| LIVE-14 | Two-way talk from web UI | AF | - | not v1 | Browser mic access requires a secure context (HTTPS). `[CAM]` The mobile app already does it. Revisit only if the TLS story is solved. |
| LIVE-15 | Video wall / multi-monitor | AF | - | never in v1 | Out of scope in PROJECT.md. |

**Dependencies:** LIVE-01 needs the MediaMTX path from CAM-06/CAM-07. LIVE-03 needs CAM-07. LIVE-04 depends on HEALTH-01 (online state). LIVE-09 -> GAL-01/02.

---

## 3. Recording, retention, and storage

This is the Core Value area. Everything here is table stakes unless noted.

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| REC-01 | 24/7 continuous recording per camera in fixed-length segments (mpegts, 5 min default, remux to MP4 for playback and export) | TS | Med | v1 | `[OLD]` MediaMTX `record`, segment-complete webhook, `continuous/` and `clips/` folders. Port the approach. |
| REC-02 | Per-camera recording mode: Continuous / Event / Scheduled / Off | TS | Med | v1 | `[OLD]` `/camera/update_recording`. `[SEED]` FEAT-032. |
| REC-03 | Weekly schedule editor (days x time windows; overnight expressed as two windows); live view continues outside windows | TS | Med | v1 | `[CAM]` camera uses day-of-week plus start/end minute, max 2 windows/day. The NVR should mirror the same data shape so the schedule is portable between camera SD and NVR. Blue Iris profile/schedule confusion is a known pitfall, so keep it one concept (mode + windows). |
| REC-04 | Event-triggered recording with pre-roll and post-roll (defaults ~10 s pre and ~10 s post, configurable) | TS | High | v1 | `[OLD]` has pre/post-record buffer settings. `[SEED]` FEAT-036. Pre-roll is hard with MediaMTX because it records on or off per path. Recommended approach: record segments continuously to a staging area and keep only segments overlapping events (plus padding). This is a core architecture decision, so flag it for the architecture researcher. |
| REC-05 | Event source for REC-04: NuraEye LAN alerts API first, ONVIF events as fallback; alerts persisted in an NVR-owned event index | TS | High | v1 | PROJECT.md decision. See finding 2. Event-mode misses are a Core Value failure, so source health must be monitored (EVT-06). |
| REC-06 | Retention policy enforced by the NVR: keep N days AND/OR cap by size; delete oldest first | TS | Med | v1 | Finding 1. Synology rotates on whichever limit is hit first, which is the pattern to copy. |
| REC-07 | Disk-full handling: overwrite oldest rather than stop recording; configurable low-space threshold; never delete the segment currently being written | TS | Med | v1 | `[OLD]` has a threshold UI but no enforcement. `[SEED]` SCN-122 (mandatory recording continues). Frigate emergency-deletes when under about an hour of space remains. A hard reserve is better. |
| REC-08 | Configurable recording storage path (external disk or mount), with writable check at startup | TS | Low | v1 | `[MKT]` Blue Iris/Synology choose volumes. Multi-volume is v2. |
| REC-09 | Segment index in a database (camera, start, end, size, path, has-event, locked) with startup reconciliation against disk (rebuild or repair if files and index disagree) | TS | Med | v1 | `[OLD]` uses `segments.json`. A DB is far more robust. Synology has an explicit "Recording Index" re-sync. Needed for timeline accuracy and fast retention. |
| REC-10 | Automatic recovery: reconnect a dropped camera stream with backoff and resume recording with no manual action | TS | Med | v1 | Directly serves "never miss footage". Pair with gap marking (HEALTH-03). |
| REC-11 | Audio recording toggle per camera (only if the camera has a microphone) | TS | Low | v1 | `[CAM]` Audio, `hasMicrophone`. Legal sensitivity. Default off in Simple view; the capability flag gates the control. |
| REC-12 | Evidence lock (protect selected recordings or events from retention deletion) | DF | Med | v1.x | `[SEED]` FEAT-041. Synology notes it cannot lock during recording, so users want it. Design the `locked` flag in REC-09 in v1 and ship the UI in v1.x. |
| REC-13 | Retention override per camera (for example 30 days for the entrance, 7 days for the yard) with a storage estimate | DF | Med | v1.x | `[SEED]` FEAT-037/050. Frigate and Protect both support per-camera retention. Show estimated days remaining given current bitrates. |
| REC-14 | Back-fill gaps from camera SD (NVR was down or camera was unreachable) with dedup so a single timeline and single event remain | DF | High | v2 | Unique to owning both camera and NVR (finding 3). `[CAM]` RecordingsClient list, dates, and download. `[SEED]` FEAT-044 dedup, SCN-153. Timestamp reconciliation is the hard part. Requires spike research. |
| REC-15 | Mandatory vs. optional recording by SKU class (cannot disable on community cameras) | DF | Low | v2 | `[SEED]` FEAT-034. Needs a camera-reported SKU flag that does not exist yet. Defer. |
| REC-16 | Smart time-lapse, tiered retention (high-res short, low-res long), and offsite archive | AF | - | not v1 | `[MKT]` Synology. Complexity exceeds value for the target segments. |
| REC-17 | Motion-detection-on-NVR (pixel diff) recording trigger | AF | - | never | Nuisance-heavy. Camera AI events are the trigger by design. `[SEED]` PRN-003. |
| REC-18 | Transcoding on ingest | AF | - | never | Breaks Pi-class hardware. Record camera streams as-is (copy). |

**Dependencies:** REC-01 -> REC-09 -> (PLAY, REC-06, REC-07, REC-12, REC-13). REC-04 requires REC-05 and EVT-01. REC-14 requires REC-09 plus HEALTH-03 gap detection. REC-12 requires the REC-09 `locked` flag and a retention job that honors it.

---

## 4. Playback, timeline, and export

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| PLAY-01 | Per-camera 24 h timeline: recorded spans, gaps, event markers, click or drag to seek, zoom in and out | TS | High | v1 | `[OLD]` playback with zoom level, date picker. `[MKT]` Frigate History, Protect Timeline, Synology timeline. The segment index (REC-09) is the data source. Most UI-heavy table-stakes item. |
| PLAY-02 | Date picker showing which days have footage | TS | Low | v1 | `[CAM]` the camera exposes `getRecordingDates` for the same purpose, so mirror the semantics. |
| PLAY-03 | Transport controls: play/pause, +/-10 s skip, speed (0.5x-8x or more), frame step, mute, fullscreen | TS | Low | v1 | `[OLD]` has skip, speed, mute, fullscreen. |
| PLAY-04 | Continuous playback across segment boundaries with no visible seam; gap handling jumps to the next recording | TS | High | v1 | Segment stitching (HLS playlist built from the index, or MSE) is the technical core. Flag for architecture. |
| PLAY-05 | Jump from event to its recording at the trigger moment (padded by pre-roll) | TS | Med | v1 | `[SEED]` FEAT-039/036, requirement "alert linked to matching recording". |
| PLAY-06 | Clip export: mark in/out on the timeline, download MP4 | TS | Med | v1 | `[OLD]` `media_extract_video_clip`, with mark in/out buttons in playback. Port. Use stream-copy (keyframe-aligned cuts, fast) rather than re-encode. Warn that cuts snap to keyframes. |
| PLAY-07 | Snapshot from playback frame | TS | Low | v1 | `[OLD]` `takePlaybackSnapshot`. |
| PLAY-08 | Multi-camera synchronized playback (start with 4, up to 16) with shared transport | DF | High | v1.x | `[SEED]` FEAT-046/118. `[OLD]` playback already has tiles, but verify whether they are time-synced. Common on Hikvision/Dahua. Valuable for incident reconstruction in the community tier. |
| PLAY-09 | Timeline distinguishes "outage gap" from "beyond retention" | DF | Low | v1 | `[SEED]` FEAT-118. Cheap if designed into PLAY-01 and gives users honest answers about missing footage. |
| PLAY-10 | Export with integrity manifest (SHA-256 of clip plus camera, time, and exporting-user metadata) and audit entry | DF | Low | v1.x | `[SEED]` FEAT-040. Cheap (one hash and a JSON sidecar). Strong credibility for community and business evidence handling. |
| PLAY-11 | Export of multiple clips or an event bundle in one zip | DF | Med | v1.x | Frigate exports multiple review items grouped into cases. |
| PLAY-12 | Export job queue with progress, resume-after-failure, and "incomplete" marking | DF | Med | v1.x | `[SEED]` FEAT-040 scenarios. Needed once exports are long. |
| PLAY-13 | Playback speed-up and AI-based smart scrubbing (skip to events only) | AF | - | not v1 | Event-jump (PLAY-05) covers the need. |
| PLAY-14 | Export watermarking and redaction | AF | - | not v1 | `[SEED]` FEAT-195. Needs a transcode path and a privacy policy decision. |

**Dependencies:** PLAY-01 -> REC-09. PLAY-04 -> REC-01 segment format choice (mpegts vs. fMP4). PLAY-05 -> EVT-01 + REC-04. PLAY-06 -> PLAY-01. PLAY-08 -> PLAY-01 + PLAY-04 + LIVE-02 layout components. PLAY-10 -> PLAY-06 + AUD-02.

---

## 5. Events and alerts

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| EVT-01 | Ingest camera events (NuraEye alerts API; ONVIF fallback) into an NVR-owned persistent event index: camera, type, time, snapshot ref, linked segment | TS | High | v1 | Finding 2. Depends on the `[CAM]` event model (`supportedEventTypes`). The key table for everything below. |
| EVT-02 | Event list with thumbnail, type, camera, time; click to open in playback | TS | Med | v1 | `[OLD]` alerts view. `[SEED]` FEAT-116. |
| EVT-03 | Event filters: camera, type, date range (plus object class and severity where the camera provides them) | TS | Low | v1 | `[SEED]` FEAT-119. Pagination or incremental loading is required at 16 cameras. |
| EVT-04 | Event snapshot captured and stored at trigger time (not fetched later) | TS | Low | v1 | The camera snapshot endpoint `[CAM]` works only for live frames, so grab it at ingest. |
| EVT-05 | In-UI notifications: live event feed (SSE or WebSocket), unread badge, optional browser notification and sound | TS | Med | v1 | LAN-only v1 means no push gateway. `[SEED]` FEAT-133 live status sync across operators. |
| EVT-06 | Event-source health: alert subscription alive, last-event-received time, auto-resubscribe; warn if event-mode cameras have a dead feed | TS | Med | v1 | Event-only recording with a silent feed means silent data loss. Highest Core Value risk in this section. |
| EVT-07 | Review status (new, confirmed, dismissed) | DF | Low | v1.x | `[SEED]` FEAT-133. Useful for guards (community). Optional in Simple view. |
| EVT-08 | Repetitive event grouping or cooldown (collapse a person pacing for 5 minutes into one entry) | DF | Med | v1.x | `[SEED]` FEAT-121. Without it the event list becomes noise. At minimum use a per-camera cooldown on ingest. |
| EVT-09 | Incident notes and status (Open/Investigating/Resolved), assignment, collections | DF | High | v2 | `[SEED]` FEAT-126/127. Security-room workflow, not home. Defer. |
| EVT-10 | Outbound integration: webhook and MQTT publish of events | DF | Low | v1.x | `[MKT]` Frigate/Blue Iris, where this is the main hook for Home Assistant users. A very cheap way to reach integrators. |
| EVT-11 | Email/SMS/push outbound notifications | AF | - | not v1 | LAN-only. The mobile app already gets cloud alerts through its alerts_api/AWS IoT path. Do not build a second push system. SMTP email can be revisited with remote access. |
| EVT-12 | NVR-side AI analytics and rule authoring (zones, line crossing, loitering) | AF | - | not v1 | Out of scope in PROJECT.md. Camera does detection. Rule authoring stays in the mobile app and camera settings. |
| EVT-13 | Attribute search (gender, age, ethnicity-like) and "suspicious behavior" scoring | AF | - | never | The old VMS search has gender and age filters. `[SEED]` non-goals prohibit sensitive classification and undefined suspicion scores. |
| EVT-14 | Natural-language event search | AF | - | not v1 | `[SEED]` FEAT-129. Depends on AI indexing outside the platform-independent core. |

**Dependencies:** EVT-01 is the foundation for EVT-02..10, REC-04, and PLAY-05. EVT-06 depends on EVT-01. EVT-08 (cooldown at ingest) should land with EVT-01 to avoid noisy early data.

---

## 6. Camera settings (proxy `camera_api` semantics)

Principle: the NVR is a settings client for the camera, not a second source of truth. All screens are built from capability and Options responses, never hard-coded lists `[CAM]`.

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| SET-01 | Device identity: name, location, time zone, password change, read-only device info (model, firmware, serial) | TS | Low | v1 | `[OLD]` `get_name/set_name/location/timezone/set_user`. `[CAM]` Device Identity and Information. |
| SET-02 | Video encoder per stream (resolution, fps, bitrate, codec within Options ranges) | TS | Med | v1 | `[OLD]` `get/set_video_encoder_configuration`. Directly affects storage use. Show the storage impact estimate. |
| SET-03 | Imaging: brightness, contrast, saturation, sharpness, day/night, IR, WDR/backlight, anti-flicker, mirror/flip, defaults reset | TS | Med | v1 | `[OLD]` imaging options and settings. `[CAM]` Day/Night, Night Vision Type, WDR, Image Quality, Mirror/Flip, Anti-Flicker. |
| SET-04 | OSD (name and timestamp overlays) | TS | Low | v1 | `[OLD]` `get/create/modify/delete_osd`. `[CAM]` OSD gated by `osdSupported`. |
| SET-05 | Reboot (with confirm, and track reconnect) | TS | Low | v1 | `[OLD]` `device/reboot`. `[SEED]` FEAT-098. |
| SET-06 | Factory reset (Owner/Admin only, double confirmation) | TS | Low | v1 | `[OLD]` `factory_reset`. Keep admin-gated and audited. `[SEED]` FEAT-161 notes a reserved label, so check the final name. |
| SET-07 | Privacy masks (draw regions on a snapshot) | DF | Med | v1.x | `[CAM]` Privacy Masks, gated by `maskSupported`. `[SEED]` FEAT-009. Admin-only edit; viewers see the masked image. Needs a drawing canvas component. |
| SET-08 | Event preferences (which event types the camera generates) and response actions (siren, spotlight, warning, mobile alert) | DF | Med | v1.x | `[CAM]` Event Preferences and Response Actions. Directly controls what the NVR can record in event mode, so link them in the UI ("Event recording needs PersonDetected enabled"). Warn for REC-05. |
| SET-09 | Camera-side local storage (SD) enable and status, camera-side recording mode | DF | Med | v1.x | `[CAM]` Local Storage / Recording Mode (`localStorageCapable`, no card, mode, 14 windows). Needed for REC-14 and for dual-recording clarity. Advanced view only. |
| SET-10 | Camera health read-out (uptime, reboot reason, clock sync, firmware) | DF | Low | v1 | `[CAM]` Camera Health. Also feeds HEALTH. |
| SET-11 | Manual deterrence trigger (siren/spotlight) with auto-stop | DF | Low | v2 | `[CAM]` Deterrence. Nice for guard workflows, not core. |
| SET-12 | Firmware update orchestration from the NVR | AF | - | not v1 | `[SEED]` FEAT-177. Staged rollout needs a firmware distribution channel that does not exist. Show the version only. |
| SET-13 | Bulk settings apply to a group with per-camera result | DF | Med | v1.x | `[SEED]` SCN-113. Matches the community tier. Required behavior: report per-camera success and failure, never group-level success only. |
| SET-14 | Network/Wi-Fi provisioning of the camera from the NVR | AF | - | never | Mobile app BLE/Wi-Fi flow handles it. |

**Dependencies:** All SET-* depend on CAM-05 (capabilities). SET-07, 09, and 10 depend on specific capability flags. SET-02 informs REC-13 storage estimates. SET-08 interacts with REC-05.

---

## 7. Users, roles, and authentication

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| AUTH-01 | First-run wizard that creates the Owner account (no default admin/admin credentials), sets time zone and storage path | TS | Med | v1 | Industry baseline today. Old VMS ships sample users in a JSON file, which must not carry over. |
| AUTH-02 | Local accounts with salted password hashing; password change; account lockout or rate limit on repeated failures | TS | Med | v1 | LAN-only does not remove the need, since anyone on the Wi-Fi can reach the login. |
| AUTH-03 | Roles: Owner/Admin, Operator, Viewer, enforced server-side on every API call (not just hidden UI) | TS | Med | v1 | PROJECT.md. `[SEED]` FEAT-147 per-action enforcement. Roles: Viewer = live and playback; Operator adds export, snapshots, clips, ack events, camera restart; Admin adds camera, settings, users, storage. |
| AUTH-04 | API tokens or sessions for the mobile app, revocable per device | TS | Med | v1 | The mobile LAN integration needs this. `[SEED]` FEAT-155 sessions list. |
| AUTH-05 | User management UI (add, edit, disable, reset password) | TS | Low | v1 | `[OLD]` Users & Roles tab. |
| AUTH-06 | Simple/Advanced view toggle (Simple default for home) | DF | Med | v1 | PROJECT.md decision. Simple = Live, Playback, Events, Add camera, basic status. Advanced = per-camera retention, schedules, settings, health tables. Must be a UI-visibility layer only, never a permission layer. |
| AUTH-07 | Per-user camera scope (only these cameras) | DF | Med | v1 | `[SEED]` FEAT-148 (residents see only theirs). Hardest to retrofit, since every API (live, playback, export, events, snapshots) needs a scope filter. Design the data model and the single enforcement choke point in v1; the UI can be minimal. |
| AUTH-08 | Active sessions list and remote sign-out | DF | Low | v1.x | `[SEED]` FEAT-155. |
| AUTH-09 | Optional VizenLink (Cognito) account link | DF | High | v1.x | PROJECT.md. NVR must be fully usable without it. Use it for identity convenience only; the offline path stays primary. Needs a spike for token validation without internet. |
| AUTH-10 | Time-bounded access grants (contractor access) | DF | Med | v2 | `[SEED]` FEAT-153. Low priority for LAN-only. |
| AUTH-11 | Mandatory MFA | AF | - | not v1 | `[SEED]` FEAT-151 targets admin remote access. LAN-only v1 does not warrant it. Revisit with remote access. |
| AUTH-12 | Approval workflows, installer no-footage mode, enterprise SSO/LDAP | AF | - | not v1 | `[SEED]` FEAT-152/154 are enterprise features beyond the 32-camera business tier. |

**Dependencies:** AUTH-01 -> AUTH-02 -> AUTH-03 -> (everything). AUTH-04 -> mobile API. AUTH-07 requires AUTH-03 plus a central authorization layer. AUD-01 requires AUTH-03.

---

## 8. Health and storage monitoring

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| HEALTH-01 | Per-camera status as two independent badges: online/reachable and recording/not recording | TS | Low | v1 | `[SEED]` FEAT-114: never merge into one "OK". A camera can be online and not recording (disk full, event mode, schedule off). |
| HEALTH-02 | Dashboard summary: cameras online, recording, issues, storage used, active alerts | TS | Med | v1 | `[OLD]` dashboard zones: Camera Summary, System & Storage, Camera Issues, Active Alerts. Keep that structure. |
| HEALTH-03 | Recording gap detection: record last-successful-segment time per camera; flag any camera with no new segment within 2x the segment duration | TS | Med | v1 | Directly measures the success metric ("zero recording gaps"). `[SEED]` FEAT-038 shows last successful recording timestamp. |
| HEALTH-04 | Disk usage, free space, and estimated days of retention remaining at current bitrate | TS | Med | v1 | `[OLD]` has a Disk Usage section. `[SEED]` FEAT-050 estimates remaining recording time. |
| HEALTH-05 | Storage failure detection (full, unwritable, read-only, unmounted) shown as critical, distinct from camera connectivity warnings, with the list of affected cameras | TS | Med | v1 | `[SEED]` FEAT-038. Write-probe on a timer. |
| HEALTH-06 | Recorder service health (API, MediaMTX, ffmpeg workers, DB) with auto-restart and a visible "recorder degraded" state | TS | Med | v1 | `[OLD]` has Restart Services. Cross-platform supervision is the hard part. |
| HEALTH-07 | Camera offline/recovery history (start, end, duration) queryable after the fact | DF | Low | v1 | `[SEED]` FEAT-085. Cheap if designed with HEALTH-01 state transitions. Gives managers answers ("was the camera down last night?"). |
| HEALTH-08 | In-app alerts for health problems (camera offline longer than N minutes, disk nearly full, recording gap) | TS | Low | v1 | Surface in the same notification path as EVT-05. |
| HEALTH-09 | Camera clock status (synced vs. uncertain) shown per camera, plus NVR-side drift check | DF | Low | v1 | `[CAM]` `clock_sync_state`. `[SEED]` FEAT-008. See finding 7. |
| HEALTH-10 | NVR host clock/NTP sanity warning | DF | Low | v1.x | If the NVR clock is wrong, every timestamp is wrong. Common on Pi without RTC. |
| HEALTH-11 | Fleet health table (uptime, firmware, last recording, reboot pattern) with export | DF | Med | v1.x | `[SEED]` FEAT-088/093. Community tier. |
| HEALTH-12 | "Recheck now" and one-click restart for a camera | DF | Low | v1.x | `[SEED]` FEAT-098. |
| HEALTH-13 | Online-but-unusable detection (black frame, blurred lens, tamper) | AF | - | not v1 | `[SEED]` FEAT-086/090. Needs image analysis or camera support. Relay camera tamper events as normal events if the camera emits them. |
| HEALTH-14 | Disk SMART monitoring | AF | - | v2 | Platform-specific (smartctl). Warn on filesystem errors only for v1. |
| HEALTH-15 | Infrastructure dashboards (CPU, GPU, threads) | AF | - | never | Out of scope in PROJECT.md. Show only NVR basics (CPU load or host health inside HEALTH-06). |

**Dependencies:** HEALTH-01 -> LIVE-04, dashboard. HEALTH-03/05 -> REC-09. HEALTH-07 -> HEALTH-01 history. HEALTH-08 -> EVT-05 path.

---

## 9. Gallery, search, and audit

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| GAL-01 | Snapshot gallery (manual snapshots from live and playback) with camera, time, user, and filters | TS | Low | v1 | `[OLD]` `save_snapshot`, `media_items_list`, gallery view with All/Snapshots/Clips tabs. `[SEED]` FEAT-132. |
| GAL-02 | Clip gallery (manual clips, exported clips), preview, download, delete with confirmation | TS | Low | v1 | `[OLD]` `media_item_add/delete`. Delete requires an explicit confirmation. |
| SRCH-01 | Recordings search: by camera, date/time, and event type, returning timeline jumps | TS | Med | v1 | PROJECT.md "recordings search (ported from old VMS)". Port the UI skeleton but not the attribute filters (EVT-13). |
| SRCH-02 | Cross-camera event-indexed jump: select a time and see all cameras at that moment | DF | Med | v1.x | `[SEED]` FEAT-039. Builds on PLAY-08. |
| SRCH-03 | Daily digest (events plus health issues) | DF | Med | v2 | `[SEED]` FEAT-128. |
| AUD-01 | Audit log: logins, failed logins, camera add/remove, setting changes, exports, deletions, user and role changes (append-only, filterable) | TS | Med | v1 | `[SEED]` FEAT-150/192. Without it community managers cannot answer "who exported this?". Minimal viable: table plus filter plus no edit or delete API. |
| AUD-02 | Export and share events logged with user, time, and clip IDs | DF | Low | v1.x | `[SEED]` FEAT-040. Part of PLAY-10. |
| GAL-03 | Expiring share links for people without accounts | AF | - | not v1 | Old VMS has `generate_share_link`. In a LAN-only product, a link only works for someone already on the LAN who could just log in. Revisit with remote access. `[SEED]` FEAT-047/199 has strict requirements (mandatory expiry, scoped, revocable, logged) that are all remote-access concerns. |
| GAL-04 | Cloud sync of gallery | AF | - | not v1 | `[SEED]` FEAT-043, cloud is a separate path. |

---

## 10. Mobile-app integration over LAN

The mobile app must be able to treat the NVR as a "super camera" with long history. This is a product feature in its own right: the REST API is a deliverable.

| ID | Feature | Tier | Complexity | Target | Notes |
|----|---------|------|-----------|--------|-------|
| MOB-01 | Documented, versioned NVR REST API (OpenAPI) covering camera list/add/remove, recording mode, health, events, recording dates and list, clip download, snapshots | TS | High | v1 | PROJECT.md requirement. Prefer resource-style REST over the old `POST /api/vms/*` RPC style, and keep the `{success,data|error}` envelope or move to standard HTTP codes (decide once; the mobile `camera_api` uses typed results). |
| MOB-02 | NVR discovery on the LAN (mDNS/Bonjour and/or WS-Discovery announce) plus manual add by IP | TS | Med | v1 | Without it, home users cannot find the NVR. A QR on the NVR web UI that encodes URL plus pairing token is a cheap shortcut. |
| MOB-03 | Pairing/auth for the mobile app (AUTH-04): login or QR pairing; per-device revocation | TS | Med | v1 | Reuses AUTH-04. |
| MOB-04 | Live view through the NVR relay (WebRTC/HLS/RTSP) using the sub stream by default on phones | TS | Med | v1 | `[SEED]` FEAT-002 mobile substream. `[CAM]` mobile already uses RTSP and WebRTC. |
| MOB-05 | Recording browse and playback: dates with footage, clip list or timeline segments, Range-capable MP4/HLS playback | TS | Med | v1 | Finding 6. Mirror the camera `Recordings` API shape (dates, list, `trigger`) so the mobile app can reuse its screens with minimal change. |
| MOB-06 | NVR health and storage to mobile (status per camera, disk, recorder state) | TS | Low | v1 | PROJECT.md. |
| MOB-07 | Manage from mobile: add or remove cameras, change recording mode (permission-gated) | TS | Med | v1 | PROJECT.md. Enforce the same role model as the web. |
| MOB-08 | Live event stream to mobile (SSE/WebSocket) while on LAN | DF | Low | v1.x | Same feed as EVT-05. |
| MOB-09 | NVR-offline fallback: app falls back to direct-camera paths and labels the view as fallback | DF | Med | v1.x | `[SEED]` FEAT-143. The app already has direct camera paths, so this is mostly app logic plus NVR status endpoint. |
| MOB-10 | Mobile-initiated clip export | DF | Med | v1.x | Reuses PLAY-06. |
| MOB-11 | Remote (off-LAN) access, push gateway | AF | - | not v1 | Out of scope in PROJECT.md. Mobile keeps its existing AWS/WAN paths for cameras. |
| MOB-12 | The NVR re-implementing the camera WAN/KVS streaming path | AF | - | never | Duplicates `camera_api` WAN. |

**Dependencies:** MOB-01 is a hard dependency of every MOB-*. MOB-02/03 -> AUTH-04. MOB-05 -> REC-09 + PLAY-04 format decisions. MOB-07 -> AUTH-03.

---

## Table stakes summary (v1 cut)

Minimum set where a missing item makes a home user or a community guard leave:

1. **Add cameras:** CAM-01..09 (discovery, manual, test, default-password prompt, capabilities, rollback-safe add)
2. **See cameras:** LIVE-01..06 (single, grid, sub-stream, honest tile state)
3. **Record and keep:** REC-01..11 (segments, modes, schedule, event with pre/post-roll, enforced retention, disk-full overwrite, index, auto-recover)
4. **Find and export:** PLAY-01..07 (timeline, dates, stitching, event jump, clip export, snapshot)
5. **Know what happened:** EVT-01..06 (persisted events, list, filter, in-app alerts, source health)
6. **Configure cameras:** SET-01..06
7. **Control access:** AUTH-01..05 plus AUD-01
8. **Trust it:** HEALTH-01..06, 08
9. **Reuse content:** GAL-01..02, SRCH-01
10. **Mobile:** MOB-01..07

## Differentiators (ranked by value per effort for this product)

1. **Gap-proof recording with visible proof** (HEALTH-03 + PLAY-09 + HEALTH-07 + REC-10 + CAM-13). Directly delivers the Core Value and success metric. Most competitors do not show gaps this honestly.
2. **Tight camera integration**: capability-driven settings (SET-*), event-source health (EVT-06), and event preferences linked to recording mode (SET-08). Generic NVRs cannot do this.
3. **Simple/Advanced toggle with one role model** (AUTH-06): one product for home and business.
4. **Evidence package**: lock (REC-12) + export manifest (PLAY-10) + audit (AUD-01/02). Cheap and strong for the community tier.
5. **Camera-SD gap back-fill with dedup** (REC-14, v2). Unique to a vendor that owns both sides. High effort, so validate first with a spike.
6. **First-class mobile API** (MOB-*) with the same recording semantics as the camera SD.
7. **Integrator hooks** (EVT-10 webhook and MQTT). Low effort and opens Home Assistant users.

## Anti-Features (explicitly not built in v1)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|--------------------|
| Generic/third-party ONVIF cameras | Out of scope in PROJECT.md; doubles the test matrix | Keep the camera layer behind an interface so it could be added later |
| NVR-side AI analytics, rule authoring, Nura AI chatbot, attribute search (gender/age) | Out of scope in PROJECT.md; `[SEED]` non-goals on sensitive classification | Camera does detection; NVR stores and displays events |
| Kafka WebSocket feed | Not core NVR function (PROJECT.md) | Use the simple SSE/WebSocket event feed (EVT-05) |
| Remote access, cloud push, email/SMS alerts | LAN-only v1; the mobile app already has its cloud path | In-UI notifications plus webhook/MQTT out |
| Expiring share links | No audience in a LAN-only product | Authenticated download; revisit with remote access |
| Pixel-motion recording trigger on the NVR | Nuisance alerts; wastes CPU | Camera AI events |
| Transcoding on ingest or for export | Breaks Pi-class hardware | Stream-copy everywhere; sub-stream for low-bandwidth views |
| PTZ controls, two-way talk in web UI, video wall | No PTZ in `camera_api`; HTTPS-only mic; PROJECT.md | Mobile app handles talk |
| Enforced camera-count limits / licensing | Deferred (PROJECT.md) | Make the camera count a config value so it is easy to add later |
| Infra dashboards (CPU/GPU/thread stats) | Out of scope in PROJECT.md | Recorder health only (HEALTH-06) |
| Firmware push/orchestration, camera Wi-Fi provisioning | No distribution channel; mobile handles provisioning | Show firmware version only |
| Mandatory MFA, SSO/LDAP, approval workflows | Beyond LAN-only, 32-camera scope | Strong local passwords, lockout, audit |
| Default accounts (admin/admin) or sample users | Industry-wide security failure mode | First-run wizard (AUTH-01) |

## Feature dependency graph

```
CAM-01/02 -> CAM-03 -> CAM-05 (capabilities) -> CAM-07 (profiles) -> LIVE-01 -> LIVE-02/03
                              |                        |
                              v                        v
                         SET-* (all)              REC-01 (segments) -> REC-09 (index) -> PLAY-01 (timeline) -> PLAY-04 -> PLAY-06 (export)
                                                       |                    |                                      |
                                                       |                    +-> HEALTH-03/05 (gaps, storage)       +-> PLAY-10 (manifest) -> AUD-02
                                                       +-> REC-06/07 (retention, disk-full) -> REC-12 (lock), REC-13
EVT-01 (event index) -> REC-05 -> REC-04 (event rec + pre/post roll) -> PLAY-05 (jump to event)
EVT-01 -> EVT-02/03 -> EVT-05 (live feed) -> MOB-08
EVT-01 -> EVT-06 (source health)
AUTH-01 -> AUTH-02 -> AUTH-03 (roles) -> AUTH-04 (tokens) -> MOB-02/03 -> MOB-01..07
AUTH-03 -> AUTH-07 (camera scope: single enforcement choke point) -> applies to LIVE, PLAY, EVT, GAL, MOB
AUTH-03 -> AUD-01 (audit)
HEALTH-01 -> LIVE-04, HEALTH-02, HEALTH-07
REC-09 + HEALTH-03 -> REC-14 (SD back-fill, v2)
PLAY-01 + PLAY-04 + LIVE-02 -> PLAY-08 (sync multi-camera playback)
```

Notable cross-cutting dependencies:

- **Authorization choke point** (AUTH-03/07) must exist before the first data API ships. Retrofitting per-camera scope later means touching every endpoint.
- **Segment index plus segment format** (REC-01/09, PLAY-04) is the platform for timeline, export, retention, health gaps, mobile playback, and SD back-fill. Decide format (mpegts vs. fMP4) and the stitching approach (HLS playlist from the index vs. MSE) in the architecture phase.
- **Event index** (EVT-01) is the platform for event recording, event jump, filters, alerts, and mobile feeds.

## MVP recommendation

**v1 should include**, in build order:

1. Foundation: AUTH-01..03, AUD-01 (minimal), MOB-01 API skeleton, CAM-01..09, CAM-05 capability cache
2. Core Value: REC-01, 02, 06..10, HEALTH-01, 03..06, 08 (continuous recording, enforced retention, gap detection) before any polish
3. See and find: LIVE-01..06, PLAY-01..07, GAL-01..02
4. Events: EVT-01..06, REC-03..05
5. Settings: SET-01..06 (and SET-10 health read-out)
6. Mobile: MOB-02..07
7. Differentiators that are cheap in v1: AUTH-06 (Simple/Advanced), PLAY-09, HEALTH-07, HEALTH-09, AUTH-07 data model

**Defer to v1.x:** SET-07..09, 13; LIVE-07, 08, 10; PLAY-08, 10..12; REC-12, 13; CAM-10..13; EVT-07, 08, 10; AUTH-08, 09; HEALTH-10..12; MOB-08..10.

**Defer to v2:** REC-14 (SD back-fill), REC-15, EVT-09, AUTH-10, SRCH-03, SET-11, HEALTH-14.

**Biggest scope risk:** treating REC-04/05 (event recording with pre-roll) and PLAY-01/04 (timeline with seamless stitching) as ordinary features. They are the two High-complexity items on the Core Value path and need architecture decisions and prototypes before phase planning.

## Open questions

- Does the camera expose a SKU-class or recording-mandatory flag (REC-15)? Not in `SETTINGS_API_GUIDE.md`. Confirm with the camera team.
- Is there a way to mark a camera as claimed by an NVR (CAM-10)? If not, it needs a `camera_api` change, which requires explicit owner confirmation.
- Are the old VMS playback tiles time-synchronized (PLAY-08)? Verify by reading `playback-controller.js` (not examined in depth).
- Is the camera alert feed push (subscription) or poll-based on the LAN? This shapes EVT-06 and REC-05 reliability. It belongs in the stack and architecture research.
- What is the TLS plan for the NVR (self-signed vs. plain HTTP on LAN vs. locally trusted cert)? It affects MOB-05 playback and any future web two-way talk.
- Which of the old `/api/vms/*` routes are kept versus redesigned for MOB-01?

## Sources

- Internal (HIGH): `/Users/gokul/Desktop/Vizenlink_Vms/.planning/PROJECT.md`
- Internal (HIGH): old VMS `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms` (`python/server.py` routes; `views/` dashboard, cameras, multiview, playback, gallery, search, settings; `js/multiview-controller.js`, `js/settings-controller.js`)
- Internal (HIGH): `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md` (Local Storage, Recording Mode, Camera Health, Recordings, Event Preferences, Response Actions, Capabilities)
- Internal (MEDIUM-HIGH, draft): `/Users/gokul/mobilecctvapp/VizenLink_Home_Community_CCTV_Feature_Seed_v0.1.md` (a "research seed, not an approved spec") and `vms-*` scenarios in `/Users/gokul/mobilecctvapp/scenarios/` (all still `draft`, so treat them as intent, not committed requirements)
- External (MEDIUM): [Frigate exports](https://docs.frigate.video/usage/exports), [Frigate history/timeline](https://docs.frigate.video/usage/history)
- External (MEDIUM): [Synology Surveillance Station recording settings](https://www.synology.com/en-global/knowledgebase/Surveillance/help/SurveillanceStation/recording_settings_recording), [Synology recording and playback](https://www.synology.com/en-in/surveillance/feature/recording_playback), [Synology Surveillance Station spec](https://www.synology.com/en-eu/dsm/software_spec/surveillance_station)
- External (LOW-MEDIUM): [UniFi Protect 5.2 overview](https://lazyadmin.nl/home-network/unifi-protect-5-2-42-overview/) and app release notes (mixed app and firmware versions; verify against Ubiquiti release notes)
- External (LOW-MEDIUM, community-reported): [Blue Iris profiles and schedules (ipcamtalk)](https://www.ipcamtalk.com/threads/recording-alerts-schedule.532), [Blue Iris profile confusion thread](https://ipcamtalk.com/threads/confusion-about-profiles-continous-recording-and-alerts-not-in-working-hours.56662/latest)
- Domain knowledge (MEDIUM): Hikvision/Dahua NVR web UI conventions (sync playback, views, sequence/tour) and Scrypted (integration-hub model). Not re-verified in this session.
