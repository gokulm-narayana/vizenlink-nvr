# Phase 2: Headless Recording Core - Context

**Gathered:** 2026-10-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers the core recorder headless:
- 24/7 fMP4 recording via MediaMTX with zero remuxing overhead;
- MediaMTX process decoupling and declarative reconciliation from SQLite;
- Two-source segment indexing (real-time completion hook + reconciliation scanner);
- Storage safeguards (system drive guard, hard free space reserve, storage health states);
- Retention janitor (time-based and size-based pruning, oldest-unprotected first, sole deleter);
- Per-camera recording modes (Continuous, Scheduled, Event, Off) and audio toggles;
- Camera removal with keep/delete recordings choice (CAM-09);
- Recording gap watchdog and dual independent health badges (online/offline, recording/not recording);
- Automatic stream drop reconnection with exponential backoff;
- Local admin CLI commands for recording and storage operations on loopback.

Everything remains strictly headless and driven from the local admin CLI. No network listeners are exposed to the LAN.

Requirements: FND-01, FND-02, CAM-09, REC-01, REC-02, REC-03, REC-05, REC-06, REC-07, REC-08, REC-09, REC-10, REC-11, HLTH-01, HLTH-03, HLTH-04, HLTH-05, HLTH-06.

Out of this phase:
- LAN-exposed HTTP API `/api/v1` and user authentication belong to Phase 3.
- Web UI and live browser grid belong to Phase 3.
- Ingestion of camera events (ONVIF PullPoint) and event search belong to Phase 4.
- Timeline playback and video export belong to Phase 5.

</domain>

<decisions>
## Implementation Decisions

The user approved the core defaults and architectures established in research. Every decision below locks Phase 2 behavior.

### 1. Storage Location & Disk Safeguards
- **D-31: Storage directory structure.**
  Recordings are saved to `{storage_root}/{camera_serial}/{YYYY}/{MM}/{DD}/{YYYY-MM-DDTHH-MM-SS}Z.mp4`.
  Timestamps in directory names and filenames are always UTC with trailing `Z`.
  Storage root is configurable via CLI (`nvr storage set-path <PATH>`), defaulting to `<NVR_DATA_DIR>/recordings`.
- **D-32: System drive guard (REC-08, HLTH-05).**
  The NVR inspects mountpoints. If the configured storage path is on the host root mountpoint (`/` on Linux/macOS or `C:\` on Windows), the NVR refuses to start recording unless explicitly overridden with `--allow-system-disk`. If the recording volume is missing, unmounted, or read-only, the recorder halts with a critical storage error (`STORAGE_UNMOUNTED`, `STORAGE_READ_ONLY`) distinct from camera offline status.
- **D-33: Hard free-space reserve & overwrite (REC-07, HLTH-04).**
  The NVR enforces a hard minimum free space buffer: default `10 GB` (or 5% of total disk capacity, whichever is larger). When disk free space drops below this low-water mark, the Janitor proactively deletes the oldest unprotected segments across cameras to prevent write failure.

### 2. Segment Duration & MediaMTX Configuration
- **D-34: Segment duration & format (REC-01, REC-11).**
  MediaMTX records directly into fragmented MP4 (`fMP4`) segments.
  - `recordSegmentDuration: 60s` (60-second fixed segments).
  - `recordPartDuration: 1s` (enables power-loss safety without file corruption).
  - Audio recording is toggled per camera: if camera capability confirms audio and user enabled audio (`nvr recording set-audio --serial <SERIAL> --enabled`), audio track is recorded; otherwise disabled.
  - No remuxing is required; files are natively playable fMP4.
- **D-35: Two-source segment indexing (REC-09).**
  - *Real-time hook:* MediaMTX `runOnRecordSegmentComplete` executes a CLI hook (`nvr recording index-segment ...`) that immediately writes segment start time, duration, size, and path into the SQLite `segments` table.
  - *Reconciliation scanner:* Background loop on startup and periodically (e.g. every 10 minutes) reconciles disk contents with SQLite: indexes unindexed files, clears database records for deleted files, and flags truncated files.

### 3. Retention Policies & Janitor
- **D-36: Retention enforcement & camera removal (REC-05, REC-06, CAM-09).**
  - Per-camera retention is configurable: max retention days (e.g. 14 days) and max storage gigabytes.
  - The NVR Janitor is the **sole** component that deletes footage (MediaMTX `recordDeleteAfter` is set to `0s`). Oldest unprotected segments are pruned first.
  - Camera removal (`nvr cameras remove --serial <SERIAL>`) requires an explicit choice: `--keep-recordings` (preserves files and keeps segments table or archives them) or `--delete-recordings` (janitor purges segment files and DB records).

### 4. Recording Modes & Schedules
- **D-37: Recording modes & schedules (REC-02, REC-03).**
  - Supported modes:
    - `Continuous`: 24/7 recording.
    - `Scheduled`: Records only during active windows defined by weekly schedule.
    - `Event`: Records continuous rolling circular buffer ready for event locking (Phase 4).
    - `Off`: Camera stream is not recorded.
  - Weekly schedule represents a 7×24 grid (168 hourly slots or 336 30-min slots) stored in the camera's recording configuration.

### 5. Watchdog & Independent Process Supervision
- **D-38: Process decoupling & declarative reconciler (FND-01, FND-02).**
  MediaMTX runs as an independent daemon. The NVR Core's Declarative Reconciler reads camera configurations from SQLite and synchronizes paths via MediaMTX's loopback control API (`127.0.0.1:9997`).
  If NVR Core crashes or restarts, MediaMTX continues recording in-flight streams. If MediaMTX restarts, NVR Core reconciles and re-provisions all paths immediately.
- **D-39: Gap watchdog & dual health status (HLTH-01, HLTH-03, HLTH-06, REC-10).**
  - Dual independent badges for each camera:
    1. Connection status: `online` vs `offline`.
    2. Recording status: `recording` vs `not_recording`.
  - Gap watchdog monitors `last_segment_completed_at`. If elapsed time exceeds `2 × segment_duration + 30s` (~150 seconds for 60s segments), status transitions to `not_recording` with a gap alert.
  - Dropped streams reconnect automatically with exponential backoff (1s, 2s, 4s, ..., up to 60s).

### 6. Admin CLI Commands
- **D-40: CLI recording and storage interface (FND-04, REC-02, REC-06, HLTH-04).**
  - `nvr recording status`: displays per-camera recording state, mode, current segment age, and health badges.
  - `nvr recording set-mode --serial <SERIAL> --mode <MODE>`
  - `nvr recording set-retention --serial <SERIAL> [--days N] [--max-gb GB]`
  - `nvr recording set-schedule --serial <SERIAL> [--schedule-spec ...]`
  - `nvr storage status`: displays disk space, mountpoint, free space reserve, and retention estimates.
  - `nvr storage set-path <PATH> [--allow-system-disk]`
  - `nvr storage scan`: triggers manual disk/index reconciliation.
  - `nvr cameras remove --serial <SERIAL> (--keep-recordings | --delete-recordings)`

</decisions>
