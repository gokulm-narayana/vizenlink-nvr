# Phase 1: Foundations & Camera Onboarding - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md. This log preserves the alternatives considered.

**Date:** 2026-10-26
**Phase:** 01-foundations-camera-onboarding
**Areas discussed:** Admin CLI experience, Default password & creds, Camera test setup, Identity & re-IP rules. All were decided by Claude at the user's request ("go with recommended also refer the mobile app and api").

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Admin CLI experience | One-off vs permanent CLI, prompts vs flags, scan output | ✓ (Claude decides) |
| Default password & creds | Set the password on the camera vs refuse; at-rest protection | ✓ (Claude decides) |
| Camera test setup | Real cameras, fixtures for CI, port vs rewrite | ✓ (Claude decides) |
| Identity & re-IP rules | Default names, location/group model, silent vs flagged re-IP | ✓ (Claude decides) |

**User's choice:** "go with recommeded also refer the mobile app and api"
**Notes:** Claude read `mobilecctvapp/lib/app_state/camera_onboarding.dart`, `camera_scan.dart`, `camera_address_recovery.dart`, `utils/camera_account_rules.dart`, and the "Camera accounts and roles", identity and discovery sections of `camera_api/API_REFERENCE.md`. Decisions mirror those flows.

## Camera test setup

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, 1 camera | One camera available, can be factory-reset | ✓ |
| Yes, 2+ cameras | Several cameras | |
| Yes, but no resets | Cameras available, no reset or password change | |
| Not right now | Fixtures and simulator only | |

**User's choice:** Yes, 1 camera

## Claude's Discretion

- Repo layout and module names; CLI framework and how it reaches the service layer (it must reuse the Phase 3 API's code path).
- Contract-test harness shape, simulator design and fixture format.
- Storage of the NVR-only group tag; discovery timeouts (defaults from `camera_api`).

**Key choices made by Claude, with the mobile app and API as reference:**
- The NVR uses the camera's Administrator account (`camera_api` documents NVR use), with no automatic retry on 401.
- One factory-password probe attempt; the NVR sets the new password on the camera with the mobile app's password rules.
- Authenticated verification via `GetCapabilities`, never `GetDeviceInformation`.
- Serial is the primary key, with silent re-IP healing using blank credentials.
- Name and location are the camera's own; group is an NVR-only tag.
- Credentials are encrypted with an OS-keystore or key-file data key. This differs from the mobile app because the NVR must start unattended.
- The CLI is permanent; passwords are prompted only, never passed as arguments.
- `camera_api` contracts are vendored with a sha256 lock file; CI does not depend on the private repo.

## Deferred Ideas

- Dedicated least-privilege NVR camera account.
- Claimed-by-another-NVR detection and batch add (v1.x).
- Cloud claim during NVR onboarding (the NVR is LAN-only in v1).
