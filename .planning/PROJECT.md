# VizenLink NVR

## What This Is

A rebuild of the existing VizenLink/NuraEye VMS (`nuraeye-rt/vms`) as a network video recorder that records, plays back and manages VizenLink/NuraEye cameras on the local network. It keeps the proven Python + MediaMTX recording approach, replaces the AngularJS web UI with a modern one, and aligns all camera behaviour with the shared `camera_api` contracts so the NVR and the VizenLink mobile app behave identically with the same camera. It serves both home users (2–8 cameras, simple UX) and communities/small businesses (8–32 cameras, guard/manager operators) from one product with tiered views and roles.

## Core Value

**Never miss footage** — every added camera records reliably 24/7 (plus events), and that footage is always findable on a timeline from both the web UI and the mobile app.

## Business Context

- **Customer**: VizenLink camera owners — households and communities/small businesses running a local recorder box
- **Revenue model**: Companion to VizenLink/NuraEye camera hardware (OnChipTech); tiering/licensing deferred
- **Success metric**: Zero recording gaps on healthy cameras; footage for any event found in under a minute
- **Strategy notes**: Product vision in `/Users/gokul/mobilecctvapp/VizenLink_Home_Community_CCTV_Feature_Seed_v0.1.md` (vms-* scenarios in `/Users/gokul/mobilecctvapp/scenarios/`)

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Discover VizenLink/NuraEye cameras on the LAN (WS-Discovery) and add them with credentials
- [ ] Live view of a single camera and a multiview grid (via MediaMTX relay)
- [ ] 24/7 continuous recording per camera, with retention policy and disk-full handling
- [ ] Event recording triggered by NuraEye camera AI alerts (LAN alerts API), with ONVIF events as fallback
- [ ] Timeline playback by camera and time, with clip export
- [ ] Alerts/events list linked to the matching recording
- [ ] Camera settings (imaging, encoder, OSD, privacy, etc.) following `camera_api` semantics and capability flags
- [ ] Users and login: local NVR accounts plus optional link to the VizenLink Cognito account
- [ ] Roles: Owner/Admin, Operator, Viewer
- [ ] Simple/Advanced view toggle (Simple default for home users)
- [ ] Health and storage status: camera online state, disk usage, recorder health
- [ ] Snapshot gallery and recordings search (ported from old VMS)
- [ ] Documented NVR REST API that the mobile app consumes on LAN: browse recordings, live via NVR, NVR health, manage NVR (add/remove cameras, recording mode)
- [ ] Platform-independent Python core (runs on Raspberry Pi, Jetson, Linux PC, Windows/macOS)

### Out of Scope

- Remote (off-LAN) access to the NVR — v1 is LAN only; mobile keeps its existing camera/AWS paths off-LAN
- Third-party / generic ONVIF cameras — VizenLink/NuraEye only for v1
- AI features in the NVR (the old VMS's AI analytics layers, Nura AI chatbot) — AI stays separate from the platform-independent core
- Kafka WebSocket feed from old VMS — not core NVR functionality
- Enforced camera-count limits / licensing tiers — designed for later; v1 targets ~16 cameras without enforcement
- Video wall, bulk provisioning, infrastructure dashboards (GPU/CPU/thread stats)

## Context

- **Existing VMS** (`/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms`): Flask backend (`python/server.py`, ~1.8k lines, `/api/vms/*` POST JSON endpoints, `{success,data|error}` envelope), AngularJS 1.x UI (`js/`, `views/`), MediaMTX for RTSP relay and recording (mpegts, 5-minute segments, segment-complete webhook, `continuous/` and `clips/` folders), Python ONVIF/NuraEye clients, WS-Discovery scanner. Per-camera recording modes already exist: continuous/event/scheduled/off.
- **Shared API** (`/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages`): `camera_api` (pure Dart; LAN ONVIF + NuraEye REST `/nuraeye/*`, RTSP/WebRTC live view, recordings; WAN AWS IoT/KVS), `auth_api` (Cognito), `alerts_api` (AWS IoT MQTT alerts). `camera_api/API_REFERENCE.md`, `SETTINGS_API_GUIDE.md` and `STREAMING_GUIDE.md` are the behavioural contract the Python backend must match.
- **Mobile app** (`/Users/gokul/mobilecctvapp`): Flutter, consumes the three packages; screens for live view, multiview, events, alerts, camera settings. Will add NVR support over LAN.
- Python cannot import the Dart packages directly — "using the existing API" means the Python camera layer mirrors `camera_api`'s contracts (endpoints, capability flags, settings semantics, typed result/error model).

## Constraints

- **Tech stack (backend)**: Python + MediaMTX — keeps proven recording path and runs on all target hardware
- **Tech stack (frontend)**: React + TypeScript (Vite) — best ecosystem for video grids, timeline scrubbing, WebRTC/HLS players
- **Platform**: Platform-independent Python for all non-AI features; hardware not yet decided (Pi, Jetson, Linux PC, Windows/macOS all possible)
- **Network**: LAN only for v1
- **Compatibility**: Camera behaviour must match `camera_api` contracts; changes to `camera_api` itself require explicit owner confirmation
- **Cameras**: VizenLink/NuraEye only
- **Scale**: ~16 cameras target on mid-range hardware

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rebuild existing VMS (not Flutter desktop / Dart server) | Keep proven Python + MediaMTX recording | — Pending |
| Fresh repo in Vizenlink_Vms, port useful logic from old VMS | Clean architecture while reusing MediaMTX client, discovery, ONVIF where they match camera_api | — Pending |
| `camera_api` contracts are source of truth for camera behaviour | NVR and mobile app must behave identically; removes drift | — Pending |
| React + TypeScript (Vite) web UI | AngularJS is EOL; strongest video/timeline ecosystem | — Pending |
| Event recording: NuraEye alerts + ONVIF events fallback | Use camera's own AI; ONVIF as safety net | — Pending |
| Auth: local accounts + optional Cognito link | Works fully offline; one VizenLink identity when online | — Pending |
| Tiers = roles + Simple/Advanced toggle, no enforced limits in v1 | One product for home and business without licensing complexity | — Pending |
| Mobile integration over LAN in v1 (recordings, live, health, manage) | Gives mobile long recording history; remote access deferred | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-26 after initialization*
