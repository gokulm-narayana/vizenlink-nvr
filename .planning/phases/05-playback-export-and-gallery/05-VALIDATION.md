# Phase 5: Playback, Export & Gallery - Validation Strategy

**Date:** 2026-11-04  
**Status:** In Planning  

## Validation Strategy Overview

Phase 5 validates that any recorded moment can be found, scrubbed on a timeline, exported, and browsed in a media gallery:
1. Schema migration `0006` creates `gallery_items` and adds necessary indices.
2. Timeline index queries return contiguous recording spans, outage gaps, and event markers with date-picker coverage.
3. Video playback streaming provides seamless progressive playback and byte-range seeking across segment boundaries.
4. Clip export produces valid, standalone MP4 clips from selected in/out time spans with temp-then-rename safety.
5. Gallery REST API enables browsing, downloading, and deleting media items with full RBAC camera scoping and audit logging.
6. React UI renders the interactive 24-hour timeline, transport controls, date picker, export dialog, and media gallery.
7. Phase 5 end-to-end pipeline tracer validates the entire playback, export, and gallery lifecycle against an updated 12-step phase gate.

---

## Requirements Validation Matrix

| Requirement | Description | Test Type | Automated Test Target | Status |
|:---|:---|:---|:---|:---:|
| **PLAY-01** | Per-camera 24h timeline with recorded spans, gaps, event markers; seek and zoom | Integration / UI | `tests/integration/test_playback_timeline.py` | Pending |
| **PLAY-02** | Date picker shows which days have footage | Integration | `tests/integration/test_playback_timeline.py` | Pending |
| **PLAY-03** | Transport controls: play/pause, ±10s skip, speed, mute, fullscreen | Unit / UI | `tests/unit/test_player_controls.py` | Pending |
| **PLAY-04** | Playback continues across segment boundaries without seam and skips gaps | Integration | `tests/integration/test_playback_streaming.py` | Pending |
| **PLAY-05** | Jump from event straight to recording (padded by pre-roll) | Integration | `tests/integration/test_playback_timeline.py` | Pending |
| **PLAY-06** | Mark in/out on timeline and export an MP4 clip | Integration | `tests/integration/test_clip_export.py` | Pending |
| **PLAY-07** | Save snapshot from playback frame | Integration | `tests/integration/test_gallery_api.py` | Pending |
| **PLAY-08** | Timeline distinguishes recording outage gap from retention pruning | Integration | `tests/integration/test_playback_timeline.py` | Pending |
| **GAL-01** | Browse snapshot gallery filtered by camera, time and user | Integration | `tests/integration/test_gallery_api.py` | Pending |
| **GAL-02** | Browse, preview, download and delete (with confirmation) clips | Integration | `tests/integration/test_gallery_api.py` | Pending |
| **GAL-03** | Search recordings by camera, date/time and event type, jump to timeline | Integration | `tests/integration/test_playback_timeline.py` | Pending |
| **LIVE-07** | Record manual clip from live view into gallery | Integration | `tests/integration/test_gallery_api.py` | Pending |
| **REC-12** | Lock recordings/segments so retention never deletes them | Integration | `tests/integration/test_playback_timeline.py` | Pending |

---

## Security & Reliability Invariants

1. **Viewer Isolation (`AUTH-05`):**
   - Viewers can only query timeline spans, stream video segments, export clips, and view gallery files for cameras they have permissions to view.
2. **Safe Exporting:**
   - Clip exports use atomic temp-then-rename to prevent corrupted or half-written video files.
3. **Retention Protection (`REC-12`):**
   - Locked segments are marked `is_protected = True` and are guaranteed to survive retention and low-water pruning.
