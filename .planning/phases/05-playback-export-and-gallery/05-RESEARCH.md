# Phase 5: Playback, Export & Gallery - Research & Technical Decisions

## 1. Playback Architecture & Seeking

### 1.1 Progressive fMP4 vs MediaMTX `/get` vs Range Requests
- **MediaMTX Playback Endpoint (`:9996/get`):**
  - MediaMTX provides a built-in playback server that concatenates recorded fMP4 segments on-the-fly when queried via `/get?path={path}&start={RFC3339}&duration={seconds}`.
  - However, MediaMTX returns `Accept-Ranges: none`, which prevents browsers from performing HTTP 206 Byte-Range seeks within an open HTTP connection.
  - While seeking can be modeled by sending a new GET request starting at the target seek timestamp, Safari and iOS browsers are notorious for requiring HTTP 206 byte-range responses for HTML5 `<video>` scrubbing.
- **Hybrid Streaming Approach:**
  - The NVR provides `/api/v1/playback/segment/{id}` which serves individual segment files with full `Accept-Ranges: bytes` and `206 Partial Content` support.
  - The timeline knows the exact duration and boundary of every 5-minute segment.
  - When playing continuously, the player uses MediaSource Extensions (MSE) or seamlessly advances to the next segment URL when the current segment ends.
  - Seeking to any second in any segment resolves immediately via HTTP byte-range request.

---

## 2. MP4 Clip Export Without Re-encoding

- **Stream Copying / Transmuxing:**
  - Re-encoding video with FFmpeg is CPU-heavy and slow on embedded / edge hardware.
  - Because all recorded segments are already valid fMP4 (H.264/H.265 tracks with `ftyp`, `moov`, `moof`, `mdat` boxes), exporting a clip across contiguous segments can be achieved through pure stream copy / container concatenation.
  - For single segments or multiple segments, the exporter concatenates the `moof` + `mdat` fragments, updating sequence numbers and sample composition time offsets where necessary, or writes a compliant single-track MP4.
  - A fallback to system `ffmpeg` (when installed on the host) provides fast `-c copy` stream copying:
    ```bash
    ffmpeg -y -ss {offset} -t {duration} -i {input_seg} -c copy {output_clip}
    ```
  - If `ffmpeg` is not installed, the pure Python fMP4 box concatenator assembles the valid fMP4 clip directly.

---

## 3. Database Schema Design: Migration 0006

- **`gallery_items` Table:**
  ```sql
  CREATE TABLE gallery_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      item_type TEXT NOT NULL,  -- 'snapshot', 'manual_clip', 'export_clip'
      camera_serial TEXT NOT NULL REFERENCES camera(serial) ON DELETE CASCADE,
      user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      title TEXT NOT NULL,
      file_path TEXT NOT NULL,
      file_size_bytes BIGINT NOT NULL,
      duration_seconds REAL,
      captured_at TIMESTAMP NOT NULL,
      created_at TIMESTAMP NOT NULL,
      CONSTRAINT ck_gallery_item_type CHECK (item_type IN ('snapshot', 'manual_clip', 'export_clip'))
  );
  CREATE INDEX ix_gallery_items_camera_captured ON gallery_items (camera_serial, captured_at);
  CREATE INDEX ix_gallery_items_type ON gallery_items (item_type);
  ```

---

## 4. UI Components & Interaction Model

1. **Playback Timeline:**
   - 24-hour horizontal timeline canvas/SVG.
   - Zoom levels: `24h` (full day), `12h`, `4h`, `1h`, `15m`.
   - Visual layers:
     - Background grid with hour/minute ticks.
     - Green/teal blocks for continuous recording spans.
     - Red blocks for camera outage intervals (`PLAY-08`).
     - Yellow/orange badges for event markers (`motion`, `line_crossing`, etc.).
     - In/Out selection overlay when export mode is enabled.
     - Playhead cursor (draggable or clickable).
2. **Date Picker:**
   - Calendar dropdown fetching `/api/v1/playback/days?camera_serial=...&year=...&month=...`.
   - Days with available recordings are highlighted with a badge/dot.
3. **Gallery:**
   - Grid layout with thumbnails, file size, duration, timestamp, and actions (Download, Delete, Preview).

