# Plan 05-05 Summary: Gallery REST API, Media Downloads, Deletion, and RBAC

## Status: COMPLETE

### Overview
Implemented the Gallery REST API router (`/api/v1/gallery`), allowing querying snapshots and clips with pagination and filters, secure media downloads (`image/jpeg` and `video/mp4`), deletion with disk unlinking, viewer RBAC scoping (`AUTH-05`), and audit logging.

### Key Changes
1. **Gallery Router (`src/vizenlink_nvr/api/v1/gallery.py`):**
   - `GET /api/v1/gallery`: Lists media items with pagination (`limit`, `offset`), filtering by `camera_serial`, `item_type`, `start_time`, and `end_time`. Restricts non-owner/operator viewers to assigned cameras (`AUTH-05`).
   - `GET /api/v1/gallery/{item_id}`: Fetches single gallery item metadata with viewer camera access verification.
   - `GET /api/v1/gallery/{item_id}/download`: Serves requested snapshot (`image/jpeg`) or clip (`video/mp4`) via FastAPI `FileResponse` with directory traversal protection.
   - `DELETE /api/v1/gallery/{item_id}`: Requires `operator` or `owner` role, removes DB record, unlinks file from disk, and records audit event `gallery.delete_item`.
2. **App Router Inclusion (`src/vizenlink_nvr/api/app.py`):**
   - Registered `gallery_router` under `/api/v1/gallery`.
3. **OpenAPI Specification Contract:**
   - Updated `contracts/openapi_v1_baseline.json` and verified backward-compatibility.
4. **Integration Tests (`tests/integration/test_gallery_api.py`):**
   - Verified gallery queries and filtering (`item_type`, `camera_serial`).
   - Verified viewer RBAC boundary (viewer sees only permitted camera items; forbidden `403` when accessing unauthorized camera).
   - Verified downloading snapshots and clips with correct MIME types.
   - Verified deletion: file unlinked from disk, DB record removed, audit event logged, and viewer deletion rejected with `403`.

### Verification
- `uv run pytest tests/integration/test_gallery_api.py -v`: 3 passed in 0.79s.
- `uv run python tools/check_api_breaking_changes.py`: Success: OpenAPI schema is backward-compatible with baseline.
- `uv run ruff check src/vizenlink_nvr/api/v1/gallery.py src/vizenlink_nvr/api/app.py tests/integration/test_gallery_api.py`: All checks passed.

