---
gsd_state_version: "1.0"
current_phase: 05
current_phase_name: Playback, Export & Gallery
status: ready
stopped_at: Phase 04 complete (7 of 7 plans verified and 11/11 phase gate passed); ready for Phase 05
last_updated: "2026-11-04T07:58:00.000Z"
last_activity: 2026-11-04
last_activity_desc: Phase 04 complete (Plan 04-07: Phase 4 end-to-end tracer, 11/11 phase gate passed)
state_head: HEAD
progress:
  total_phases: 8
  completed_phases: 4
  total_plans: 54
  completed_plans: 54
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-26)

**Core value:** Never miss footage: every added camera records reliably 24/7 (plus events), and that footage is always findable on a timeline from both the web UI and the mobile app.
**Current focus:** Phase 05 — Playback, Export & Gallery

## Current Position

Phase: 04 (Events & Event Recording) — COMPLETED
Plans: 7 of 7 complete (100% Phase 04 complete)
Status: Ready for Phase 05 planning
Last activity: 2026-11-04 — Plan 04-07 complete (Phase 4 tracer, 11/11 phase gate passed 100% green)

Progress: [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓] 100% (Phase 04 complete)

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

## Session Continuity

Last session: 2026-11-04
Stopped at: Phase 04 complete; ready for Phase 05 planning
Resume file: .planning/ROADMAP.md
