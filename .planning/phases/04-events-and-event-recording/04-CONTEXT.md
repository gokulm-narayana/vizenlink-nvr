# Phase 4: Events & Event Recording - Context

**Gathered:** 2026-11-04  
**Status:** Ready for planning  

<domain>
## Phase Boundary

Phase 4 bridges real-time camera alerts with the NVR storage and playback pipeline:
- Camera event ingestion via a pluggable event-source architecture:
  - Default v1 provider: ONVIF PullPoint event subscription client (`CreatePullPointSubscription`, `PullMessages`, `Renew`, `Unsubscribe`).
  - Reserved architecture slot for direct NuraEye LAN push/alert feeds.
- Clock sanity evaluation (`HLTH-09`):
  - Detect camera clock drift relative to NVR UTC clock.
  - Re-stamp event trigger times with NVR UTC time when camera clock is uncertain or unsynced (`EVT-07`).
- Trigger-time event snapshot capture & storage (`EVT-04`):
  - Capture real-time snapshot JPEG at trigger time and store under `{storage_path}/events/{camera_serial}/{YYYY}/{MM}/{DD}/{event_id}.jpg`.
- Event-mode segment protection (`REC-04`):
  - When in `Event` mode, keep footage across `[event_start - pre_roll, event_end + post_roll]` (configurable, default 10s pre-roll and 10s post-roll).
  - Protect underlying fMP4 segments (`is_protected = True`, `protection_reason = 'event:<event_id>'`) so retention preserves evidence while pruning idle footage.
- Subscription supervisor & health tracking (`EVT-06`):
  - Monitor subscription health per camera (state: `active`, `reconnecting`, `failed`, last event timestamp).
  - Auto-resubscribe with exponential backoff on stream drops or camera reboots.
  - In-app warning alerts when event-mode recording is at risk due to broken subscription.
- REST API `/api/v1/events` (`EVT-02`, `EVT-03`):
  - List events with filtering (camera, event type, date range), pagination, and viewer camera permission scoping.
  - Event detail and snapshot image endpoints.
  - Event locking/unlocking endpoints (`POST /api/v1/events/{id}/lock`).
  - Event subscription status endpoint (`GET /api/v1/events/subscriptions/status`).
- React Web UI Live Event Feed & Alerts (`EVT-02`, `EVT-05`):
  - Events tab / drawer in web UI with thumbnail cards, metadata badges, and filters.
  - Live in-app alert banner & toast notifications with unread counter badge.

Requirements: `EVT-01`, `EVT-02`, `EVT-03`, `EVT-04`, `EVT-05`, `EVT-06`, `EVT-07`, `REC-04`, `HLTH-09`.

Out of this phase:
- Interactive timeline scrubber and video clip export belong to Phase 5.
- Camera settings editing (brightness, OSD, motion detection sensitivity zones) belongs to Phase 6.
- Mobile LAN mDNS pairing belongs to Phase 7.
</domain>

<decisions>
## Implementation Decisions

### 1. Event Data Model & Database Schema (Migration 0005)
- **D-51: `events` table schema.**
  - `id`: integer primary key autoincrement.
  - `camera_serial`: foreign key to `camera.serial`.
  - `event_type`: canonicalized event string (`motion`, `line_crossing`, `tamper`, `person`, `vehicle`, `generic`).
  - `source`: event source (`onvif_pullpoint`, `nuraeye_lan`).
  - `start_time`: UTC datetime of event trigger.
  - `end_time`: UTC datetime of event completion (or null if momentary).
  - `snapshot_path`: relative path to trigger snapshot JPEG file.
  - `is_locked`: boolean (default `False`). When `True`, retention janitor never deletes this event or its protected footage.
  - `clock_sync_state`: `synced` vs `uncertain`.
  - `raw_topic`: original ONVIF Topic or payload string.
  - `details_json`: JSON string storing extended event parameters (bounding boxes, rule name).
  - `created_at`: UTC timestamp.
- **D-52: Pre-roll and Post-roll configuration.**
  - Add `pre_roll_seconds` (default 10) and `post_roll_seconds` (default 10) to `recording_settings`.

### 2. ONVIF PullPoint Client & Pluggable Interface
- **D-53: Pluggable `EventSource` interface.**
  - `EventSource` protocol defining `start()`, `stop()`, and an async generator/callback for `EventRecord`.
  - `OnvifPullPointSource` implements ONVIF PullPoint standard with WS-Security authentication.
  - Supports topic filtering (e.g. `tns1:RuleEngine/CellMotionDetector/Motion`, `tns1:RuleEngine/LineDetector/LineCrossed`, `tns1:Device/Trigger/DigitalInput`).
- **D-54: Camera clock drift compensation (EVT-07, HLTH-09).**
  - During subscription setup and periodic pull, query camera UTC time (`GetSystemDateAndTime`).
  - If camera clock deviates from NVR clock by more than 5 seconds or camera reports unsynced NTP, mark `clock_sync_state = 'uncertain'` and overwrite event timestamps with NVR `utc_now()`.

### 3. Snapshot Capture at Trigger Time
- **D-55: Snapshot trigger mechanism (EVT-04).**
  - Upon receiving an event trigger:
    - Primary: Fetch high-resolution snapshot via camera ONVIF snapshot URI (`GetSnapshotUri`).
    - Fallback: Extract current frame from local MediaMTX RTSP stream via `ffmpeg`/`pyav` or MediaMTX frame grab if camera snapshot URI is unreachable.
  - Save file to `{storage_root}/events/{camera_serial}/{YYYY}/{MM}/{DD}/{event_id}.jpg`.

### 4. Event-Mode Segment Protection
- **D-56: Segment protection window (REC-04).**
  - When event triggers, compute protected span: `[event.start_time - pre_roll, (event.end_time or event.start_time) + post_roll]`.
  - Query all segments in `segments` table overlapping this span: set `is_protected = True`, `protection_reason = f"event:{event.id}"`.
  - If segments are currently recording (active segment), protect upon completion.

### 5. Web UI & Live Notification
- **D-57: Real-time event notifications in SPA.**
  - UI polls `/api/v1/events?since={last_seen}` every 3 seconds or listens to Server-Sent Events (SSE).
  - Active unread badge in navigation header displays count of unread events.
  - Event feed displays thumbnail, camera name, relative timestamp, and event badge.
</decisions>

