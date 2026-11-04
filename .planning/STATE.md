---
gsd_state_version: "1.0"
current_phase: 07
current_phase_name: Mobile LAN Integration
status: ready
stopped_at: Phase 06 complete (4 of 4 plans verified and 13/13 phase gate passed); ready for Phase 07
last_updated: "2026-11-04T10:16:00.000Z"
last_activity: 2026-11-04
last_activity_desc: Phase 06 complete (Plan 06-04: Phase 6 tracer, 13/13 phase gate passed)
state_head: HEAD
progress:
  total_phases: 8
  completed_phases: 6
  total_plans: 66
  completed_plans: 66
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-26)

**Core value:** Never miss footage: every added camera records reliably 24/7 (plus events), and that footage is always findable on a timeline from both the web UI and the mobile app.
**Current focus:** Phase 07 — Mobile LAN Integration

## Current Position

Phase: 06 (Camera Settings) — COMPLETED
Plans: 4 of 4 complete (100% Phase 06 complete)
Status: Ready for Phase 07 planning
Last activity: 2026-11-04 — Plan 06-04 complete (Phase 6 tracer, 13/13 phase gate passed 100% green)

Progress: [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓] 100% (Phase 06 complete)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table and Phase Contexts:

- [D-41]: Web Setup Wizard on uninitialized NVR redirects to `/setup`. Creates Owner account (Argon2id, min 8 chars), site timezone, and storage directory. HTTP-only, SameSite=Lax session cookies with 5-failure 15-minute brute-force lockout.
- [D-42]: MediaMTX configured with `authMethod: http` pointing to NVR loopback auth endpoint `/api/v1/auth/mediamtx`. Short-lived (15 min) signed media tokens validated on read attempts.
- [D-43]: OpenAPI 3.1 REST API under `/api/v1` for auth, users, cameras, recording, storage, and health. Data model includes nullable `cognito_sub` for future cloud linking (AUTH-08). CI breaking-change detector guards compatibility.
- [D-44]: Persistent SQLite `audit_logs` tracking logins, failures, camera ops, config changes, and user management.
- [D-45]: React + Vite Single Page App served by FastAPI. WebRTC (WHEP) player with HLS fallback. 1×1 to 4×4 multiview grid using sub-streams by default, auto-switching to main stream on zoom. Layout persisted in `localStorage`. Simple vs Advanced view toggle (AUTH-06).
- [D-46]: Pluggable `EventSource` protocol with `OnvifPullPointSource` managing SOAP PullPoint subscriptions, XML parsing, and exponential reconnect backoff (1s to 60s).
- [D-47]: `EventSnapshotManager` enforces disk path layout (`events/{serial}/{YYYY}/{MM}/{DD}/{id}.jpg`) with 0o640 permissions, JPEG validation, and fallback tiny JPEG.
- [D-48]: `SegmentProtectionService` tags overlapping segments with `is_protected = True`, granting absolute immunity against retention janitor and low-water pruning (REC-04).
- [D-49]: Event clock drift evaluation restamps timestamps with NVR UTC time when camera drift exceeds 5 seconds (EVT-07, HLTH-09).
- [D-50]: Gallery data model with `gallery_items` table (migration 0006) capturing snapshots, manual clips, and exported clips with foreign keys and cascade rules.
- [D-51]: RangeFileResponse HTTP 206 Partial Content byte-range streaming for fMP4 video playback, with MediaMTX auth webhook supporting `action in ("read", "playback")`.
- [D-52]: Lossless MP4 clip exporter combining ISOBMFF fragment boxes without CPU-intensive re-encoding, utilizing atomic temp-then-rename and POSIX 0o640 permissions.
- [D-53]: React 24h interactive playback timeline with zoom (24h/12h/4h/1h), visual outage and event indications, gap skipping without freeze, and unified media gallery with preview modals and safety-confirmed deletion.
- [D-54]: Camera settings service with capability-gated options, dynamic bounds validation, re-encryption of camera passwords into Vault, append-only audit trail for reboot and factory reset, and strict Owner/Admin RBAC enforcement.

## Session Continuity

Last session: 2026-11-04
Stopped at: Phase 06 complete; ready for Phase 07 planning
Resume file: .planning/ROADMAP.md
