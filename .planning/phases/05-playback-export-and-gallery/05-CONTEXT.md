# Phase 5: Playback, Export & Gallery - Context

**Phase Goal:** Any recorded moment can be found and used in under a minute: users scrub a timeline, jump from events, export clips, save snapshots and search recordings.
**Status:** In Planning
**Requirements:** PLAY-01, PLAY-02, PLAY-03, PLAY-04, PLAY-05, PLAY-06, PLAY-07, PLAY-08, GAL-01, GAL-02, GAL-03, LIVE-07, REC-12

---

## 1. Domain Architecture & Principles

### 1.1 Timeline Scrubbing & Index Mapping
- **24-Hour Timeline Data Model:** The backend exposes an efficient timeline index (`/api/v1/playback/timeline`) returning:
  1. Recorded segment intervals (`start_time`, `end_time`, `duration`, `stream_type`, `is_protected`).
  2. Camera outage intervals (`start_time`, `end_time`, `reason`) from `CameraOutage` table (`PLAY-08`). Outages are distinctly colored on the timeline from retention deletions.
  3. Camera events (`id`, `event_type`, `start_time`, `is_locked`, `snapshot_path`).
- **Date Picker Calendar:** `/api/v1/playback/days` scans available segment dates for the selected camera and month (`PLAY-02`).
- **Event-to-Recording Jump:** Clicking an event immediately navigates the timeline to `event.start_time - pre_roll_seconds` (`PLAY-05`).

### 1.2 Video Playback Streaming
- **Cross-Platform fMP4 Delivery:**
  - Modern browsers (Chrome, Edge, Firefox, Safari desktop/iOS) natively support progressive fMP4 playback with standard `<video>` controls and `playbackRate` (0.5x, 1x, 2x, 4x, 8x) (`PLAY-03`).
  - MediaMTX playback server (:9996) serves `/get?path=cam/{serial}/main&start={ISO}` with `Accept-Ranges: none`.
  - To support instantaneous, reliable seeking across any segment or gap, the NVR provides a direct segment streaming endpoint (`/api/v1/playback/segment/{id}`) with full HTTP `Range: bytes=...` support (`206 Partial Content`), ensuring seamless Safari and iOS compatibility (`PLAY-04`).
- **Gap Skipping:** When the playback cursor reaches the end of a recorded span or an outage gap, the player smoothly skips to the start of the next available segment (`PLAY-04`).

### 1.3 Clip Export & Snapshots
- **Lossless Stream Copy Export:**
  - Marking `in` and `out` points on the timeline triggers an export request (`POST /api/v1/playback/export`) (`PLAY-06`).
  - The export engine selects matching segments, extracts or copies the requested byte span using fMP4 box concatenation / stream copy without re-encoding, and writes an MP4 clip to `gallery/clips/{serial}/{id}.mp4` using safe temp-then-rename semantics.
- **Snapshot Capture:**
  - Playback and Live snapshots can be saved directly into `gallery/snapshots/{serial}/{id}.jpg` (`PLAY-07`, `LIVE-07`).
  - Each item is indexed in `gallery_items`.

### 1.4 Gallery & Evidence Locking
- **Unified Media Gallery (`/gallery`):**
  - Displays Snapshots and Clips with metadata (camera, timestamp, user, duration, size) (`GAL-01`, `GAL-02`).
  - Clips can be previewed, downloaded, and deleted with explicit user confirmation (`GAL-02`).
- **Segment / Recording Locking (`REC-12`):**
  - Users can lock specific segments or entire event recordings to prevent retention pruning.

---

## 2. Invariants & Security Boundaries

1. **RBAC Scoping (`AUTH-05`):**
   - Viewers can only view timeline spans, play video, export clips, and view gallery items for cameras they are explicitly permitted to view.
   - Unauthorized camera requests return `403 Forbidden`.
2. **Audit Logging (`AUTH-07`):**
   - All clip exports, clip deletions, and segment locks are permanently recorded in `audit_logs`.
3. **Safe File Operations:**
   - Gallery file paths are strictly sandboxed under the NVR storage root (`gallery/clips/...` and `gallery/snapshots/...`). Directory traversal is strictly prevented.
