# Handoff — 2026-10-26 — phase1-context

**GSD position:** Phase 1 of 8. Context gathered; ready to plan.

## What this session did
- Ran `/gsd-discuss-phase 1`. The user asked Claude to decide using the mobile app and `camera_api` as the reference.
- Wrote `.planning/phases/01-foundations-camera-onboarding/01-CONTEXT.md` (22 decisions) and `01-DISCUSSION-LOG.md`.

## Decisions made (and why)
- **Onboarding mirrors the mobile app.** The flow is `camera_onboarding.dart` / `camera_scan.dart`: one factory-password probe (each attempt counts toward the camera lockout), authenticated verification via `GetCapabilities` (never `GetDeviceInformation`, which ignores credentials), and blank credentials during scans.
- **Camera account.** The NVR uses the camera's `admin` account. `camera_api` documents that NVRs do this, and later phases need admin. A 401 sets `auth_failed` with no automatic retry, to avoid lockout.
- **Default password.** The NVR sets the new password on the camera (8–32 characters, never `password`) and tells the owner to use it in the mobile app too.
- **Identity.** Serial is the primary key. Re-IP is healed silently, by serial, with blank credentials. Name and location are stored on the camera (shared with mobile); "group" is an NVR-only tag.
- **Credentials at rest.** AES-256-GCM, with the data key in the OS keystore or a 0600 key file. This differs from the mobile app because the NVR must restart recording unattended.
- **CLI.** Permanent `nvr` CLI. Passwords are prompted only, never passed as arguments.
- **Contracts.** `camera_api` contracts are vendored into `contracts/camera_api/` with a sha256 lock, so CI doesn't need the private repo.
- **Hardware.** The user has **one real camera** that can be factory-reset. A real-camera smoke suite runs opt-in and is skipped in CI.

## Current state
- Working: planning docs only, no code yet.

## Next step
- `/clear`, then `/gsd-plan-phase 1`.

## Open questions / waiting on
- Firmware owner: is there a LAN alert feed? (Phase 4 depends on the answer and falls back to PullPoint.)
- Old VMS security exposure on shared networks (the user was warned).
