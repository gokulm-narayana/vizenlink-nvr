# Phase 4: Events & Event Recording - Validation Strategy

**Date:** 2026-11-04  
**Status:** In Progress  

## Validation Strategy Overview

Phase 4 validates that camera alerts become reliable, protected, searchable records with trigger snapshots:
1. Schema migration `0005` creates `events` and updates `recording_settings` with pre-/post-roll defaults.
2. ONVIF PullPoint subscription engine ingests events, handles camera reboots, and normalizes clock drift.
3. Snapshots are generated and saved at trigger time.
4. Segments in the event window (`[trigger - pre_roll, trigger + post_roll]`) are marked protected and immune to janitor pruning.
5. REST API provides filtered and permission-scoped event listings and locking.
6. React UI renders the event feed with live unread badge updates.
7. End-to-end pipeline tracer proves the complete alert -> protect -> query lifecycle.

---

## Requirements Validation Matrix

| Requirement | Description | Test Type | Automated Test Target | Status |
|:---|:---|:---|:---|:---:|
| **EVT-01** | Ingest camera events into persistent event index (ONVIF PullPoint / pluggable) | Unit & Integration | `tests/unit/test_pullpoint_parser.py`<br>`tests/integration/test_event_ingestion.py` | Pending |
| **EVT-02** | Event list with thumbnail, type, camera and time | Integration / UI | `tests/integration/test_api_events.py` | Pending |
| **EVT-03** | Filter events by camera, type and date range | Integration | `tests/integration/test_api_events.py` | Pending |
| **EVT-04** | Event snapshot captured and stored at trigger time | Unit & Integration | `tests/unit/test_event_snapshots.py` | Pending |
| **EVT-05** | In-app live event notifications with unread badge | Frontend / Integration | `tests/unit/test_event_notifications.py` | Pending |
| **EVT-06** | Subscription monitoring (alive, last event, auto-resubscribe, risk warning) | Integration | `tests/integration/test_event_subscription_supervisor.py` | Pending |
| **EVT-07** | Clock drift compensation: uncertain clock restamped with NVR time | Unit | `tests/unit/test_clock_drift_compensation.py` | Pending |
| **REC-04** | Event mode keeps pre-roll and post-roll footage (default ~10s each) | Integration | `tests/integration/test_event_segment_protection.py` | Pending |
| **HLTH-09** | User can see whether each camera's clock is synced or uncertain | Integration | `tests/integration/test_camera_clock_health.py` | Pending |

---

## Security & Reliability Invariants

1. **Viewer Scoping:**
   - A viewer user can only query events for cameras they have permissions to view. Events for non-permitted cameras return empty or 403.
2. **Protection Guarantee:**
   - Any segment tagged with `is_protected = True` is never deleted by `enforce_retention` or `enforce_disk_low_water_mark`.
3. **Resubscribe Backoff:**
   - Subscription failures back off exponentially (1s, 2s, 4s, ... max 60s) and never crash the process.
