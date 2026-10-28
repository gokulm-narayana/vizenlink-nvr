# Plan 01-24 Summary: Serial-Keyed Camera Schema, Registry Service, and Stream Selection

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Confirm D-11 (one-way): the camera serial is the registry's primary key**
   - User explicitly confirmed locked decision D-11 ("serial-pk"): the camera serial is the primary key for the `camera` table, and foreign-keyed by child tables with `ON DELETE CASCADE`.

2. **Task 2: Create serial-keyed registry and stream resolver**
   - Defined SQLAlchemy ORM models in `src/vizenlink_nvr/db/models.py`:
     - `Camera` (serial PK, host, https_port, mac, name, location, group_tag, manufacturer, model, firmware_version, hardware_id, tls_fingerprint_sha256, camera_id_check, state, added_at, host_updated_at, identity_synced_at, last_error; check constraint on `state`).
     - `CameraCredential` (serial PK FK to `camera.serial` ON DELETE CASCADE, username, ciphertext, nonce, key_id, enc_version, updated_at).
     - `CameraCapabilitiesRow` (serial PK FK to `camera.serial` ON DELETE CASCADE, raw_json, probed_at, firmware_version_at_probe).
     - `CameraStream` (composite PK: `(serial, role)` FK to `camera.serial` ON DELETE CASCADE, profile_token, profile_name, venc_token, codec, width, height, transport, scheme, port, path, source, sub_is_main, probed_at; check constraints on `role` and `source`).
   - Created Alembic migration `src/vizenlink_nvr/db/migrations/versions/0002_camera_registry.py` (down_revision `0001_initial`) with `alembic check` clean.
   - Implemented `src/vizenlink_nvr/services/streams.py`:
     - `natural_token_key` for human token sorting (e.g., `Profile_2` before `Profile_10`).
     - `select_streams` (drops `Profile_3` / `MOBILE_ONLY_PROFILE_TOKEN` and non-positive resolutions, sorts by descending `(width * height)` then natural key, sets `sub_is_main` if only 1 profile exists).
     - `resolve_streams` calling NuraEye `get_live_stream_uri` and falling back to ONVIF Media2 `get_stream_uri` with source `"onvif_fallback"` when transport is `"webrtc"` (D-23, LST-04).
   - Implemented `src/vizenlink_nvr/services/registry.py`:
     - `StreamView`, `CameraView` (strictly credential-free data structures).
     - `insert_camera`, `get_camera`, `list_cameras`, `update_host`, `set_state`, `replace_credential`, `replace_capabilities_and_streams`, `load_connection`, `camera_counts`, `stream_url`.
   - Unit tests in `tests/unit/test_stream_selection.py` (natural sorting, profile filtering, fallback on webrtc, error handling).
   - Integration tests in `tests/integration/test_registry.py` (CRUD operations, safe views, atomic rollbacks, state changes, cascading deletes, stream URL formatting without credentials).

### Verification Evidence:
- `uv run pytest tests/integration/test_registry.py tests/unit/test_stream_selection.py -x -q`: 13 passed in 0.78s.
- `uv run mypy src`: Success: no issues found in 61 source files.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 110 files already formatted.
- Alembic schema validation: `alembic check` clean.
- Reference repositories remained untouched; no secrets leak in plain text or views.
