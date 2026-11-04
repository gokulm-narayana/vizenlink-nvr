# Phase 4: Events & Event Recording - Research

**Date:** 2026-11-04  
**Status:** Completed  

## Executive Summary

Phase 4 bridges real-time camera alerts (motion, tampering, AI detection, digital inputs) into the persistent NVR recording and notification pipeline. The design centers on five critical technical pillars:
1. **Pluggable Event Ingestion (ONVIF PullPoint default):** Standards-compliant PullPoint subscription loop with automatic renewal, reconnect backoff, and SOAP message parsing.
2. **Clock Drift Invariant & Time Restamping:** Discrepancies between camera hardware clocks and NVR NTP are normalized so timeline indexing is strictly monotonic.
3. **Trigger-Time Snapshots:** Snapshots fetched from camera snapshot URIs or extracted from live streams and linked directly to event records.
4. **Segment Protection (`REC-04`):** Continuous segments overlapping pre-roll and post-roll boundaries are marked protected, preventing Janitor reclamation.
5. **REST API & React Event Feed:** Scoped event queries, locking controls, and live unread notification badges.

---

## 1. ONVIF PullPoint Architecture

ONVIF defines Event Handling in the Core Specification:
- **Subscription Creation:**
  `POST /onvif/event_service` with `tev:CreatePullPointSubscription`:
  ```xml
  <s:Body>
    <tev:CreatePullPointSubscription>
      <tev:InitialTerminationTime>PT60S</tev:InitialTerminationTime>
    </tev:CreatePullPointSubscription>
  </s:Body>
  ```
  Returns `SubscriptionReference/Address` (the unique pullpoint endpoint).
- **Message Pulling:**
  `POST {pullpoint_url}` with `tev:PullMessages`:
  ```xml
  <s:Body>
    <tev:PullMessages>
      <tev:Timeout>PT5S</tev:Timeout>
      <tev:MessageLimit>10</tev:MessageLimit>
    </tev:PullMessages>
  </s:Body>
  ```
  Returns notification messages containing `Topic`, `UtcTime`, and `Message/Data/SimpleItem`.
- **Subscription Renewal:**
  Periodic `wsnt:Renew` request every 30-45 seconds keeps the subscription alive without incurring recreate overhead.

### Topic Classification Matrix

| Raw Topic Substring | Canonical `event_type` | Severity |
|:---|:---|:---:|
| `RuleEngine/CellMotionDetector/Motion` | `motion` | Normal |
| `RuleEngine/MotionRegionDetector/Motion` | `motion` | Normal |
| `RuleEngine/LineDetector/LineCrossed` | `line_crossing` | Alert |
| `RuleEngine/TamperDetector/Tamper` | `tamper` | High |
| `VideoAnalytics/Person` / `Human` | `person` | Alert |
| `VideoAnalytics/Vehicle` | `vehicle` | Alert |
| `Device/Trigger/DigitalInput` | `digital_input` | Normal |

---

## 2. Event-Mode Segment Protection Algorithm

In `Event` mode, the camera records continuous 60s fMP4 segments. If no event occurs, segments remain unprotected (`is_protected = False`) and are reclaimed by the retention janitor according to disk space / age policies.

When an event triggers at $T_{start}$ and ends at $T_{end}$:
1. Bounding span is calculated:
   $$W_{start} = T_{start} - \text{pre\_roll\_seconds}$$
   $$W_{end} = T_{end} + \text{post\_roll\_seconds}$$
2. All segments where:
   $$\text{segment.start\_time} < W_{end} \quad \text{AND} \quad \text{segment.end\_time} > W_{start}$$
   are updated to:
   $$\text{is\_protected} = \text{True}, \quad \text{protection\_reason} = \text{"event:"} + \text{str}(event.id)$$
3. The Retention Janitor query (`enforce_retention`, `enforce_disk_low_water_mark`) specifically filters `Segment.is_protected == False`, completely guaranteeing that footage containing the event is preserved.

---

## 3. Clock Drift & Restamping Invariant (`HLTH-09`, `EVT-07`)

Cameras in field deployments often suffer from:
- Misconfigured NTP servers or lack of internet connectivity.
- RTC battery failure resetting clock to 1970 or 2000.
- Timezone offsets improperly configured on the camera.

**Detection & Correction Strategy:**
1. During subscription establishment and periodic health check, NVR compares `camera_time` (from ONVIF `GetSystemDateAndTime` or message header) with `nvr_utc_now`.
2. Offset is computed: $\Delta = |T_{camera} - T_{nvr}|$.
3. If $\Delta > 5.0\text{ seconds}$, `clock_sync_state` is set to `"uncertain"`.
4. Event `start_time` is recorded as `nvr_utc_now`, ensuring that events always match the timeline of the recorded segments.

---

## 4. REST API & UI Integration

- `/api/v1/events`:
  - Query parameters: `camera_serial`, `event_type`, `start_time`, `end_time`, `is_locked`, `limit`, `offset`.
  - Scoped by user permissions (Viewers can only retrieve events for cameras they are permitted to view).
- `/api/v1/events/{id}/lock` & `/api/v1/events/{id}/unlock`:
  - Protects event and associated footage indefinitely (`REC-12`).
- Web UI:
  - Header badge updates in real time with unread event counter.
  - Events tab lists event cards with snapshot thumbnails, timestamps, and camera badges.

