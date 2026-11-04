# Plan 04-01: Schema Migration 0005, Event Models, and Pre/Post-Roll Settings Summary

**Execution Date:** 2026-11-04  
**Status:** Completed  
**Requirements:** EVT-01, REC-04, HLTH-09  

---

## 1. Summary of Delivered Capabilities

1. **Alembic Schema Migration 0005 (`src/vizenlink_nvr/db/migrations/versions/0005_events_and_protection.py`):**
   - Created `events` table with columns `id`, `camera_serial`, `event_type`, `source`, `start_time`, `end_time`, `snapshot_path`, `is_locked`, `clock_sync_state`, `raw_topic`, `details_json`, `created_at`.
   - Created `event_subscriptions` table with columns `camera_serial`, `state`, `subscription_url`, `last_event_at`, `last_renewed_at`, `error_reason`, `clock_drift_seconds`, `updated_at`.
   - Added `pre_roll_seconds` and `post_roll_seconds` (both defaulting to 10 seconds) to `recording_settings`.
   - Verified zero schema drift against temporary database via `alembic check`.

2. **SQLAlchemy ORM Models (`src/vizenlink_nvr/db/models.py`):**
   - Defined `Event` and `EventSubscription` models with proper constraints and relationships.
   - Updated `Camera` model with `events` and `subscription` cascade relationships.
   - Updated `RecordingSettings` with pre-roll and post-roll configurations.

3. **Event Domain Types and Services (`src/vizenlink_nvr/services/events.py`):**
   - Implemented `EventType` enum (`MOTION`, `LINE_CROSSING`, `TAMPER`, `PERSON`, `VEHICLE`, `DIGITAL_INPUT`, `GENERIC`).
   - Implemented `ClockSyncState` enum (`SYNCED`, `UNCERTAIN`, `DRIFT_DETECTED`).
   - Implemented `canonicalize_event_topic(topic: str)` mapping ONVIF and vendor topic patterns to canonical types.
   - Implemented event repository functions: `insert_event`, `get_event`, `set_event_locked`, and `list_events`.

4. **Automated Verification:**
   - `tests/unit/test_event_models.py`: 2 passed.
   - `alembic check`: 0 schema drift.
   - `ruff` and `mypy`: 100% clean.
