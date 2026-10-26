# Phase 1: Foundations & Camera Onboarding - Context

**Gathered:** 2026-10-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers a headless, locked-down foundation and camera onboarding:
- the UTC time model;
- an NVR-generated default-deny MediaMTX config;
- a Python camera layer that mirrors `camera_api` and is contract-tested in CI on Linux, macOS and Windows;
- discovery, verification and registration of VizenLink/NuraEye cameras by serial.

Everything is driven from a local admin CLI. Nothing listens on the LAN.

Requirements: FND-03, FND-04, FND-05, CAM-01–08, CAM-10.

Out of this phase:
- Recording, the MediaMTX reconciler and supervision (FND-01, FND-02) belong to Phase 2.
- Removing a camera with keep/delete of its recordings (CAM-09) belongs to Phase 2.
- Any web UI or LAN-exposed API belongs to Phase 3.

</domain>

<decisions>
## Implementation Decisions

The user asked Claude to choose, with the VizenLink mobile app and `camera_api` as the reference. Every decision below mirrors their behaviour unless it is marked **deliberate difference**.

### Onboarding flow (mirror the mobile app's `camera_onboarding.dart` / `camera_scan.dart`)
- **D-01: Scan.** Use WS-Discovery multicast first and fall back to a unicast /24 sweep only if multicast finds nothing. Probe each candidate with the unauthenticated `areYouNuraeyeDevice`, with retries on first contact. Candidates that fail are dropped as "not a VizenLink camera".
  - The display name comes from the camera's GetScopes name, falling back to its model.
  - **The scan sends blank credentials only. It never sends the factory login or any stored password.**
- **D-02: Manual add by IP/host.** Run `areYouNuraeyeDeviceWithRetry` first. If it fails, the result is "unsupported device" (CAM-03), not "unreachable". Unreachable means no answer at all.
- **D-03: Default-password probe.** Make exactly **one** automatic attempt with `admin` / factory password (`password`), using a fresh session with no cached token. The results are:
  - `factoryPassword`: the owner must set a new password (CAM-04);
  - `configured` (401): ask for the password;
  - `blocked`: show the camera's `retryAfter`;
  - `unreachable`.
  - Never make a second automatic attempt, because each one costs an entry on the camera's lockout counter.
- **D-04: Setting the new password.** The NVR sets the new Administrator password **on the camera** (`setUserPassword` for `admin`), with the same rules as the mobile app:
  - 8 to 32 characters;
  - never the factory password, in any letter case.
  - The CLI then tells the owner: "Use this new password in the VizenLink mobile app too."
- **D-05: Credential verification.** Verification must use an **authenticated** call (`GetCapabilities` via NuraEye REST). Never use ONVIF `GetDeviceInformation`, which answers without checking credentials. That bug made every camera look factory-fresh in the mobile app (fixed 2026-10-16).
  - Failure reasons map to CAM-03's three outcomes:
    - 401 → wrong credentials;
    - no answer or timeout → unreachable;
    - identity check failed → unsupported.
  - A blocked camera gets its own message.
- **D-06: Data read after verification.** Read serial (`getSerialNumber`, which is also the WAN thing name), MAC, device information, device identity (name and location) and capabilities. All are best-effort except the serial: **a camera without a readable serial cannot be added**, because identity depends on it.
- **D-07: Atomic add (CAM-06).** The camera row (with its encrypted credentials) is written in one DB transaction, only after verification and capability probe succeed. A failure at any step leaves no row, and a retry starts clean.
  - The default-password change happens on the camera **before** the DB write. If the change succeeds but the add then fails, the camera simply keeps its new password and the retry asks for it.

### Camera account the NVR uses
- **D-08: Account.** The NVR signs in with the camera's **Administrator (`admin`) account**. `camera_api` documents this ("exactly one Administrator (the owner; a third-party NVR uses it too)"), and later phases need Administrator for recording mode, storage and factory reset (SET-06).
  - The NVR does **not** create its own camera account in v1, because the camera has only 5 account slots shared with family members.
  - **Reversibility:** costly. Switching to a dedicated NVR account later touches the stored credentials of every camera and needs an owner-visible migration step.
- **D-09: Password changed elsewhere.** If the admin password is changed from the mobile app, the NVR's next call gets 401. The NVR must then:
  - stop and mark the camera `auth_failed`;
  - make **no automatic retries with the stored password**, which would trip the lockout;
  - wait for the owner to re-enter the password through the CLI (later, the web UI).
- **D-10: Role failures.** `CameraForbidden` (403, or `InsufficientUserLevel`) is a role problem, not a credentials problem. The camera layer surfaces it as its own result kind, and the NVR never treats it as "log in again".

### Identity and re-IP (mirror `camera_address_recovery.dart`)
- **D-11: Primary key.** The camera's serial (thing name) is the primary key. IP, port, MAC and TLS fingerprint are mutable attributes.
  - Every LAN request carries `X-VizenLink-Camera-Id: <serial>`, with exact header case.
  - **Reversibility:** one-way. The serial is the key that recordings (Phase 2), events and the mobile API hang off, so changing it would mean a data migration.
- **D-12: Re-IP is healed silently.** On a 421 (a different camera answered) or the camera going unreachable:
  1. ask the stored address for its serial, unauthenticated;
  2. if another device answers or there is no answer, re-discover by serial (multicast first, then unicast sweep) using **blank credentials**;
  3. update the stored host.
  - If the serial isn't found, or two devices claim it, change nothing and back off.
  - The stored password is **never** sent to an unverified device.
- **D-13: Name and location are the camera's own** (`getDeviceIdentity` / GetScopes), so the NVR and the mobile app always show the same names.
  - Renaming from the NVR writes to the camera. The NVR keeps a cached copy for offline display.
  - In addition, the NVR has its own optional **group** tag per camera (CAM-08 "group"), used for business multiview. It is never written to the camera.

### Credential storage at rest
- **D-14: Deliberate difference from the mobile app.** `camera_api`'s `CameraSecureStorage` wraps the data key with the user's account password. A headless NVR must restart recording after a power cut with nobody present, so it cannot require a passphrase at boot. Instead:
  - camera passwords are AES-256-GCM encrypted in SQLite;
  - the data key is random and stored in the OS keystore where available (macOS Keychain, Windows DPAPI/Credential Manager, Linux Secret Service);
  - otherwise it is stored in a key file with owner-only permissions (0600 or equivalent ACL) in the NVR data directory, outside the recordings volume.
  - Passwords are never logged, never printed by the CLI and never returned by any API.
  - **Reversibility:** costly. Changing the key-wrapping scheme later requires re-encrypting every stored credential.

### Admin CLI
- **D-15: The CLI is a permanent tool, not a throwaway.** It is the headless path for Pi and Jetson boxes and for recovery, for example resetting the owner password in Phase 3.
  - Suggested shape: `nvr cameras scan|add|list|show|rename|reprobe`, `nvr status`, `nvr mediamtx check`.
- **D-16: CLI behaviour.**
  - Default output is human-readable tables; `--json` gives machine output for tests and scripts.
  - Passwords are **only ever prompted interactively** (hidden input), never accepted as flags or arguments, so they never land in shell history or `ps`. A non-interactive stdin mode is allowed for tests.
  - Every other input is a flag.

### Contract mirroring and testing
- **D-17: Vendored contracts.** Copy the contract inputs into this repo under `contracts/camera_api/`, pinned with a `camera_api.lock.json` that records sha256 hashes of each upstream file. Inputs are the relevant docs, the Camera REST OpenAPI and golden fixtures from `camera_api/test`.
  - CI runs against the vendored copy, so it needs no access to the private `onchiptech/nuraeye-rt` repo.
  - A local drift-check script compares the vendored files against the sibling checkout and reports changes.
  - **Upstream `camera_api` files are never modified.**
- **D-18: Port or rewrite.** Port old-VMS Python code (`ws_discovery_scanner.py`, `onvif_*.py`, `nuraeye_*.py`) only where it already matches `camera_api` behaviour. Rewrite everything else against the Dart contracts.
  - Known gaps to fix rather than port: the missing camera-ID header, missing SOAP-fault-before-HTTP-status handling, IP-keyed identity, and `netifaces` (replaced by `ifaddr`).
- **D-19: Fake-camera simulator.** Build a simulator with fault injection (401, 421, 428/password-change-required, blocked, 403, timeout, SOAP fault) for CI and unit tests.

### Hardware testing
- **D-20: Real-camera smoke suite.** The user has **one real VizenLink/NuraEye camera** on the LAN that can be factory-reset. Phase 1 gets a real-camera smoke suite, marked and skipped in CI, covering:
  - scan;
  - manual add;
  - the factory-password flow (needs a factory reset first);
  - the wrong-password message;
  - the 421 / re-IP heal;
  - the research flags: case-preserving headers, WSSE clock-skew tolerance, and RTSPS with 3 concurrent clients per stream.
  - The reset test runs only on explicit opt-in and warns that it changes the camera.

### Time and MediaMTX baseline
- **D-21: Time.** All stored times are UTC (microsecond precision). Display uses one site-wide IANA time zone, held in settings and defaulting to the host time zone until the Phase 3 first-run wizard sets it.
  - DST tests cover both transitions.
  - Camera-reported times are never trusted as authoritative.
- **D-22: MediaMTX config.** The NVR generates the config from code and pins the binary at v1.21.3 with a SHA-256 checksum. Settings:
  - no anonymous users;
  - control API bound to `127.0.0.1` only;
  - RTMP, SRT and MoQ disabled;
  - `recordDeleteAfter: 0s` as the global default, ahead of Phase 2.
  - Phase 1 only has to prove that the config is generated and that anonymous publish, read and playback are rejected. The auth-method choice (jwt vs http) is a Phase 3 spike.

### Claude's Discretion
- Repo layout: a monorepo with backend and later `web/`, and package and module names.
- CLI framework (for example Typer), table rendering, and how the CLI reaches the service layer. It must be the same service/code path the Phase 3 API will reuse, with no logic only the CLI has.
- Exact contract-test harness structure (`behaviors.yaml` vs pytest parametrization), simulator design and fixture format.
- How the "group" tag is stored, as long as it is NVR-only.
- Discovery timeouts and retry counts. Default to the `camera_api` values (3 s identity probe, retry variant 3 × 8 s, unicast cap 15 s).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.** Paths outside this repo are absolute. They are read-only references and must not be modified.

### Project planning
- `.planning/PROJECT.md`: vision, constraints, key decisions.
- `.planning/REQUIREMENTS.md`: FND-03/04/05 and CAM-01–08, CAM-10 wording.
- `.planning/ROADMAP.md` § Phase 1: goal and success criteria.
- `.planning/research/SUMMARY.md`, `STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md`: stack versions, camera-layer design, drift prevention, MediaMTX hardening, old-VMS defects to avoid.
- `.claude/CLAUDE.md`: project rules, including never modifying `camera_api`.

### camera_api contracts (source of truth for camera behaviour)
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/API_REFERENCE.md`. Key sections:
  - `CameraConnection` and the camera-ID check (421, `X-VizenLink-Camera-Id`);
  - `OnvifDeviceClient` (`getSerialNumber`, `getDeviceIdentity`, `getDeviceInformation`);
  - `NuraeyeClient` (`areYouNuraeyeDevice[WithRetry]`, sessions, the 6-session limit, password-change-required);
  - `WsDiscoveryClient` (`scanMulticast`, `scanUnicast`);
  - "Camera accounts and roles" (5 accounts, Administrator, `CameraForbidden`, `setUserPassword`);
  - `CameraSecureStorage`/`CameraCredentials` (keyed by serial).
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md`: capability flags and which client gates which setting.
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/STREAMING_GUIDE.md`: stream profiles and the RTSP vs WebRTC sub-transports (CAM-07 stream selection).
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/lib/src/`: reference implementation, in particular `camera_result.dart`, `camera_connection.dart`, `lan/camera_id_mismatch.dart`, `lan/wsse_digest.dart`, `lan/nuraeye/nuraeye_client.dart`, `lan/nuraeye/capabilities_client.dart`, `lan/onvif/onvif_device_client.dart`, `lan/onvif/soap_fault.dart` and `lan/discovery/ws_discovery_client.dart`.
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/test/`: golden fixtures and behaviour tests to vendor, including `camera_id_header_test.dart`, `case_preserving_http_client_test.dart`, `capabilities_client_test.dart` and `fixtures/`.

### Mobile app reference flows (behaviour to mirror)
- `/Users/gokul/mobilecctvapp/lib/app_state/camera_onboarding.dart`: factory-password probe, authenticated verification, post-verify reads.
- `/Users/gokul/mobilecctvapp/lib/app_state/camera_scan.dart`: multicast then unicast, the genuineness probe, blank-credential naming.
- `/Users/gokul/mobilecctvapp/lib/app_state/camera_address_recovery.dart`: silent re-IP healing by serial with blank credentials and backoff.
- `/Users/gokul/mobilecctvapp/lib/utils/camera_account_rules.dart`: password rules (8–32 characters, not `password`), 5 accounts, `admin` reserved.

### Old VMS (port candidates; reference only)
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms/python/ws_discovery_scanner.py`
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms/python/onvif_*.py`, `nuraeye_*.py`, `onvif_utils.py`
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms/python/mediamtx_client.py`
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms/mediamtx/mediamtx.yml`: shows what **not** to ship (the `any` user, `recordDeleteAfter: 1d`).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The repo has no code yet; this is greenfield.
- `camera_api` (Dart) is the behavioural spec, and its tests and fixtures can be vendored as golden data.
- From the old VMS, `ws_discovery_scanner.py` (WS-Discovery probe and parse) and the ONVIF SOAP builders in `onvif_*.py` can be ported once checked against the Dart behaviour.

### Established Patterns (from camera_api, to mirror in Python)
- Typed results, never exceptions: Success, Failure (with kind and reason), Timeout, plus distinct `Blocked(retryAfter)`, `Forbidden` and `PasswordChangeRequired` outcomes.
- Every LAN request carries the camera-ID header with exact case, and a 421 publishes a mismatch event.
- Check for SOAP faults before checking the HTTP status.
- REST sessions are cached per host and account. Concurrent logins are serialized because the firmware holds only 6 sessions.
- Verification always forces a fresh login and never reuses a cached session.

### Integration Points
- The Phase 2 recording core consumes the camera registry (keyed by serial) and the selected main/sub stream URIs from CAM-07.
- The Phase 3 API reuses the same service layer the CLI calls.
- The Phase 7 mobile integration relies on names and locations matching the camera's own identity (D-13).

</code_context>

<specifics>
## Specific Ideas

- After a default-password change, the CLI tells the owner to use the new password in the VizenLink mobile app too.
- Error wording should match the mobile app's plain language:
  - "Incorrect username or password."
  - "Could not reach the camera — check the connection and try again."
  - `cameraBlockedMessage(retryAfter)`
- The scan list shows each camera's model, name and IP, matching the mobile scan list.

</specifics>

<deferred>
## Deferred Ideas

- A dedicated NVR camera account (least-privilege) instead of `admin`. Revisit if camera account slots or privilege separation become a problem (see D-08).
- Detecting a camera already claimed by another NVR (CAM-X1, v1.x).
- Batch add of many discovered cameras (CAM-X2, v1.x).
- Claiming the camera for the owner's cloud account during NVR onboarding. The mobile app does this; the NVR is LAN-only in v1.

</deferred>

---

*Phase: 01-foundations-camera-onboarding*
*Context gathered: 2026-10-26*
