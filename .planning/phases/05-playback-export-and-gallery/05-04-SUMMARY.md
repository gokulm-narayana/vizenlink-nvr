# Plan 05-04 Summary: MP4 Clip Export Engine and Snapshot Capture Service

## Status: COMPLETE

### Overview
Implemented the lossless MP4 clip export engine (`ClipExporter`) using stream copying and container fragment assembly without re-encoding, and added playback & live snapshot capture API endpoints (`POST /api/v1/playback/export` and `POST /api/v1/playback/snapshot`), adhering to atomic temp-then-rename file integrity, permission hardening (`0o640`), camera RBAC scoping (`AUTH-05`), and audit logging.

### Key Changes
1. **Lossless fMP4 Clip Exporter (`src/vizenlink_nvr/media/clip_exporter.py`):**
   - Parses top-level ISOBMFF box headers (`ftyp`, `moov`, `moof`, `mdat`, `sidx`).
   - Reconstructs a single continuous MP4 file by writing the first segment's `ftyp` and `moov` followed by all segment fragments (`moof` + `mdat`) across the time window.
   - Enforces atomic temp-then-rename (`.tmp_{uuid}` replaced onto final target) and sets POSIX `0o640` file permissions.
2. **Playback Export Endpoint (`POST /api/v1/playback/export` in `src/vizenlink_nvr/api/v1/playback.py`):**
   - Validates user camera permissions and range (`end_time > start_time`).
   - Identifies overlapping recording segments from SQLite database.
   - Invokes `ClipExporter.export_fmp4_clip` into gallery relative storage (`gallery/clips/{serial}/{YYYY}/{MM}/{DD}/...`).
   - Records metadata in `gallery_items` table and creates audit event `gallery.export_clip`.
3. **Playback & Live Snapshot Endpoint (`POST /api/v1/playback/snapshot` in `src/vizenlink_nvr/api/v1/playback.py`):**
   - Validates user camera permissions and base64 JPEG payload (`\xFF\xD8\xFF` magic header).
   - Writes JPEG using atomic temp-then-rename with `0o640` permissions into `gallery/snapshots/{serial}/{YYYY}/{MM}/{DD}/...`.
   - Records metadata in `gallery_items` table and creates audit event `gallery.save_snapshot`.
4. **Integration Tests (`tests/integration/test_clip_export.py`):**
   - `test_clip_exporter_lossless_concatenation`: verifies ISOBMFF box assembly, temp file cleanup, and file permissions.
   - `test_clip_exporter_invalid_inputs`: tests error handling on empty or missing segment files.
   - `test_api_export_clip_workflow`: tests permission enforcement (`403` on unauthorized camera), range validation (`400`), successful export, DB item creation, and audit logging.
   - `test_api_save_snapshot_workflow`: tests snapshot permissions, non-JPEG rejection, successful save, file permissions, and audit logging.
5. **OpenAPI Contract:**
   - Updated `contracts/openapi_v1_baseline.json` and verified backward-compatibility.

### Verification
- `uv run pytest tests/integration/test_clip_export.py -v`: 4 passed in 0.48s.
- `uv run python tools/check_api_breaking_changes.py`: Success: OpenAPI schema is backward-compatible with baseline.
- `uv run pytest -q`: 406 passed, 1 skipped.

