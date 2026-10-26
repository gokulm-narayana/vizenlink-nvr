# Handoff — 2026-10-26 — project-init

**Account/session:** initial setup session
**GSD position:** Phase 1 of 8, 0 plans, Ready to plan (discuss/plan not started)

## What this session did
- Ran `/gsd-new-project`: questioning, then 4 parallel research agents plus a synthesis, then requirements, then the roadmap.
- Created `.planning/`: PROJECT.md, config.json, research/ (STACK, FEATURES, ARCHITECTURE, PITFALLS, SUMMARY), REQUIREMENTS.md (85 v1), ROADMAP.md (8 phases), STATE.md.
- Generated `.claude/CLAUDE.md`, with project rules and related-codebase paths added at the bottom.
- Set up this handoff folder.

## Decisions made (and why)
- **Rebuild the existing VMS** in this fresh repo, porting logic where it's useful. It stays Python + MediaMTX because the recording path is proven and runs on Pi, Jetson and PC.
- **`camera_api` (Dart) is the behaviour contract.** The Python camera layer mirrors it, and contract tests prevent drift.
- **Web UI:** React + TypeScript (Vite) replaces AngularJS, which is end-of-life.
- **Users:** home and business in one product, with roles (Owner/Admin, Operator, Viewer), a Simple/Advanced toggle, and no enforced camera limits in v1.
- **Mobile app** uses the NVR over LAN in v1 (recordings, live relay, health, management). Remote access is out of scope.
- **Auth:** local accounts. The Cognito identity is stored in the data model, and the linking UI comes in v1.x.
- **Event source:** ONVIF PullPoint (no documented NuraEye LAN feed was found). Event recording is continuous recording plus protected ranges, because MediaMTX has no pre-roll.
- **Recording:** fMP4 on MediaMTX v1.21.3, with `recordDeleteAfter: 0s`. The NVR is the only component that deletes footage.
- **Workflow:** YOLO mode, standard granularity, parallel execution, research/plan-check/verifier on, adaptive models, Horizontal Layers structure.

## Current state
- Working: planning docs only. There is no code yet.
- Broken / half-done: nothing.

## Next step
- `/clear`, then `/gsd-discuss-phase 1` (or `/gsd-plan-phase 1` to skip the discussion).
- After Phase 1 produces code, run `/init` once to add build and test commands to CLAUDE.md.

## Open questions / waiting on
- **Firmware owner:** does the camera push alerts to a local recorder on the LAN? Phase 4 needs the answer and falls back to PullPoint.
- **Old VMS security:** it exposes credentials, recordings and the Flask debugger on the LAN. The user was told to stop it or bind it to localhost on any shared network.
- Hardware target is not decided yet (Pi, Jetson, PC, Windows or macOS). The Phase 8 soak will measure it.
