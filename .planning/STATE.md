---
gsd_state_version: "1.0"
current_phase: 08
current_phase_name: Cross-Platform Packaging & Soak
status: completed
stopped_at: All 8 Phases complete (76 of 76 plans verified, 15/15 phase gate passed 100% green)
last_updated: "2026-11-04T11:10:00.000Z"
last_activity: 2026-11-04
last_activity_desc: Phase 08 complete (Plan 08-05: Phase 8 tracer, 15/15 phase gate passed 100% green)
state_head: HEAD
progress:
  total_phases: 8
  completed_phases: 8
  total_plans: 76
  completed_plans: 76
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-26)

**Core value:** Never miss footage: every added camera records reliably 24/7 (plus events), and that footage is always findable on a timeline from both the web UI and the mobile app.
**Current status:** All 8 project phases fully completed, verified, and passing 15/15 gate checks.

## Current Position

Phase: 08 (Cross-Platform Packaging & Soak) — COMPLETED
Plans: 5 of 5 complete (100% Phase 08 complete)
Status: All milestone phases complete
Last activity: 2026-11-04 — Plan 08-05 complete (Phase 8 tracer, 15/15 phase gate passed 100% green)

Progress: [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓] 100% (All 8 Phases Complete)

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
- [D-55]: Mobile LAN Integration architecture: mDNS zero-configuration discovery advertising API version, secure device pairing via QR-code or credentials with revocable per-device bearer tokens, sub-stream live relay default, daily calendar/span recordings playback, and server-side RBAC.
- [D-56]: Cross-Platform Packaging & Soak: Service generators for Systemd, LaunchDaemon, and WinSW; PowerManager host sleep inhibition; atomic SQLite backup/restore with SHA-256 manifests; 16-camera concurrency and soak simulation.

### Roadmap Evolution

- Phase 9 added: UI Redesign (Tailwind v4 + shadcn/ui design system, sidebar shell with router, restyled pages, web stack bump, fix Settings/Devices nav build break)

## Session Continuity

Last session: 2026-11-04
Stopped at: Phase 08 complete; all 8 phases finished and verified.
Resume file: .planning/ROADMAP.md
