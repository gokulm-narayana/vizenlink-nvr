# Plan 04-02: ONVIF PullPoint Event Subscription Engine & Pluggable Source Summary

**Execution Date:** 2026-11-04  
**Status:** Completed  
**Requirements:** EVT-01, EVT-06, EVT-07, HLTH-09  

---

## 1. Summary of Delivered Capabilities

1. **Pluggable EventSource Protocol (`src/vizenlink_nvr/events/source.py`):**
   - Defined `EventSource` abstract protocol (`subscribe`, `poll`, `renew`, `unsubscribe`).
   - Defined `RawCameraEvent` dataclass capturing canonical EventType, timestamps, and payload data.

2. **ONVIF PullPoint Client & XML Parser (`src/vizenlink_nvr/events/onvif_pullpoint.py`):**
   - Implemented `OnvifPullPointSource` managing WSSE authenticated `CreatePullPointSubscription`, `PullMessages`, and `Renew` requests.
   - Built resilient XML parser extracting `Topic`, `UtcTime`, and `SimpleItem` key-values.
   - Built clock drift compensation (`EVT-07`, `HLTH-09`): if camera time diverges by $> 5.0\text{s}$ from NVR UTC time, flags `clock_sync_state = "uncertain"` and re-stamps event with NVR UTC time.

3. **EventSubscriptionSupervisor (`src/vizenlink_nvr/events/supervisor.py`):**
   - Manages background subscription tasks per camera with auto-renewal every 30s.
   - Built exponential reconnect backoff (1s, 2s, 4s... max 60s) on socket drop or SOAP fault (`EVT-06`).
   - Persists live subscription state (`active`, `subscribing`, `reconnecting`, `failed`, `last_event_at`) in `event_subscriptions` database table.

4. **Automated Verification:**
   - `tests/unit/test_pullpoint_parser.py`: 3 passed.
   - `tests/integration/test_event_subscription_supervisor.py`: 1 passed.
   - `ruff` and `mypy`: 100% clean.
