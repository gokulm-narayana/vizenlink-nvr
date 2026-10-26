# Phase 1: Foundations & Camera Onboarding - Research

**Researched:** 2026-10-26
**Domain:** Python camera-protocol mirror of the Dart `camera_api` (REST + ONVIF SOAP + WS-Discovery), default-deny MediaMTX baseline, UTC time model, encrypted credential store, SQLite/Alembic, headless admin CLI, three-OS CI
**Confidence:** HIGH for wire behaviour (read from Dart source, firmware source and current published docs, plus experiments run in this session). MEDIUM for Windows-specific behaviour (not runnable on this macOS host; flagged `[ASSUMED]` and turned into CI checks). LOW only where a real camera must answer (flagged in the smoke-test plan).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The user asked Claude to choose, with the VizenLink mobile app and `camera_api` as the reference. Every decision below mirrors their behaviour unless it is marked **deliberate difference**.

#### Onboarding flow (mirror the mobile app's `camera_onboarding.dart` / `camera_scan.dart`)
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

#### Camera account the NVR uses
- **D-08: Account.** The NVR signs in with the camera's **Administrator (`admin`) account**. `camera_api` documents this ("exactly one Administrator (the owner; a third-party NVR uses it too)"), and later phases need Administrator for recording mode, storage and factory reset (SET-06).
  - The NVR does **not** create its own camera account in v1, because the camera has only 5 account slots shared with family members.
  - **Reversibility:** costly. Switching to a dedicated NVR account later touches the stored credentials of every camera and needs an owner-visible migration step.
- **D-09: Password changed elsewhere.** If the admin password is changed from the mobile app, the NVR's next call gets 401. The NVR must then:
  - stop and mark the camera `auth_failed`;
  - make **no automatic retries with the stored password**, which would trip the lockout;
  - wait for the owner to re-enter the password through the CLI (later, the web UI).
- **D-10: Role failures.** `CameraForbidden` (403, or `InsufficientUserLevel`) is a role problem, not a credentials problem. The camera layer surfaces it as its own result kind, and the NVR never treats it as "log in again".

#### Identity and re-IP (mirror `camera_address_recovery.dart`)
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

#### Credential storage at rest
- **D-14: Deliberate difference from the mobile app.** `camera_api`'s `CameraSecureStorage` wraps the data key with the user's account password. A headless NVR must restart recording after a power cut with nobody present, so it cannot require a passphrase at boot. Instead:
  - camera passwords are AES-256-GCM encrypted in SQLite;
  - the data key is random and stored in the OS keystore where available (macOS Keychain, Windows DPAPI/Credential Manager, Linux Secret Service);
  - otherwise it is stored in a key file with owner-only permissions (0600 or equivalent ACL) in the NVR data directory, outside the recordings volume.
  - Passwords are never logged, never printed by the CLI and never returned by any API.
  - **Reversibility:** costly. Changing the key-wrapping scheme later requires re-encrypting every stored credential.

#### Admin CLI
- **D-15: The CLI is a permanent tool, not a throwaway.** It is the headless path for Pi and Jetson boxes and for recovery, for example resetting the owner password in Phase 3.
  - Suggested shape: `nvr cameras scan|add|list|show|rename|reprobe`, `nvr status`, `nvr mediamtx check`.
- **D-16: CLI behaviour.**
  - Default output is human-readable tables; `--json` gives machine output for tests and scripts.
  - Passwords are **only ever prompted interactively** (hidden input), never accepted as flags or arguments, so they never land in shell history or `ps`. A non-interactive stdin mode is allowed for tests.
  - Every other input is a flag.

#### Contract mirroring and testing
- **D-17: Vendored contracts.** Copy the contract inputs into this repo under `contracts/camera_api/`, pinned with a `camera_api.lock.json` that records sha256 hashes of each upstream file. Inputs are the relevant docs, the Camera REST OpenAPI and golden fixtures from `camera_api/test`.
  - CI runs against the vendored copy, so it needs no access to the private `onchiptech/nuraeye-rt` repo.
  - A local drift-check script compares the vendored files against the sibling checkout and reports changes.
  - **Upstream `camera_api` files are never modified.**
- **D-18: Port or rewrite.** Port old-VMS Python code (`ws_discovery_scanner.py`, `onvif_*.py`, `nuraeye_*.py`) only where it already matches `camera_api` behaviour. Rewrite everything else against the Dart contracts.
  - Known gaps to fix rather than port: the missing camera-ID header, missing SOAP-fault-before-HTTP-status handling, IP-keyed identity, and `netifaces` (replaced by `ifaddr`).
- **D-19: Fake-camera simulator.** Build a simulator with fault injection (401, 421, 428/password-change-required, blocked, 403, timeout, SOAP fault) for CI and unit tests.

#### Hardware testing
- **D-20: Real-camera smoke suite.** The user has **one real VizenLink/NuraEye camera** on the LAN that can be factory-reset. Phase 1 gets a real-camera smoke suite, marked and skipped in CI, covering:
  - scan;
  - manual add;
  - the factory-password flow (needs a factory reset first);
  - the wrong-password message;
  - the 421 / re-IP heal;
  - the research flags: case-preserving headers, WSSE clock-skew tolerance, and RTSPS with 3 concurrent clients per stream.
  - The reset test runs only on explicit opt-in and warns that it changes the camera.

#### Time and MediaMTX baseline
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

### Deferred Ideas (OUT OF SCOPE)
- A dedicated NVR camera account (least-privilege) instead of `admin`. Revisit if camera account slots or privilege separation become a problem (see D-08).
- Detecting a camera already claimed by another NVR (CAM-X1, v1.x).
- Batch add of many discovered cameras (CAM-X2, v1.x).
- Claiming the camera for the owner's cloud account during NVR onboarding. The mobile app does this; the NVR is LAN-only in v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FND-03 | All timestamps stored as UTC, NVR clock authoritative; display in site IANA zone, correct across DST | `UtcDateTime` SQLAlchemy type storing integer epoch microseconds (prototype run, rejects naive datetimes, round-trips microseconds); `zoneinfo` + `tzdata`; DST day lengths 23 h / 25 h reproduced (see Time model) |
| FND-04 | MediaMTX default-deny (no anonymous publish/read/playback, API loopback only, unused protocols off) | Generated config validated with `mediamtx --validate-conf`, run on v1.21.3, anonymous publish/read/playback all answered 401, API 401 without credentials, disabled listeners refuse connections, negative control proves the probes can fail (see MediaMTX baseline) |
| FND-05 | Python camera layer mirrors `camera_api` contracts, checked by contract tests and golden fixtures in CI | Full Dart-to-Python mirror inventory, behaviour catalogue of about 65 rules, vendoring list with hashes, lock/drift/mirror-header design, simulator design |
| CAM-01 | Scan the LAN (WS-Discovery), show model, name, IP | Probe format, multicast then unicast, per-candidate identity probe and name resolution with blank credentials; Python-specific multi-NIC and Windows notes |
| CAM-02 | Manual add by IP/host | `areYouNuraeyeDeviceWithRetry` first; outcome taxonomy; host validation |
| CAM-03 | Clear reason on add failure (unreachable / wrong credentials / unsupported) | Result-kind to outcome mapping table; error wording from the mobile app; blocked handling |
| CAM-04 | Forced default-password change before add | Single factory probe, any login success means factory password, `setUserPassword` envelope, password rules |
| CAM-05 | Probe and cache capabilities at add, re-probe on demand | `GET /nuraeye/capabilities` parsing rules, store raw JSON plus typed subset, `reprobe` command |
| CAM-06 | Atomic add, retry-safe | One DB transaction after all camera I/O; prototype showed zero rows after a mid-add exception |
| CAM-07 | Auto-select main (recording) and sub (grid) streams | `GetProfiles` (Media2) plus `POST /nuraeye/live-stream-uri`; selection algorithm; codec and port/path facts; ONVIF `GetStreamUri` fallback needs user decision |
| CAM-08 | Name a camera and give it a location label/group | `SetScopes` envelope and encoding, 32-character limit, NVR-only group column |
| CAM-10 | Identify by serial; re-find after DHCP change without misfiling | Recovery algorithm from `camera_address_recovery.dart`, 421/unreachable events, duplicate prevention on add |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Extracted from `/Users/gokul/Desktop/Vizenlink_Vms/.claude/CLAUDE.md`. The planner must verify compliance; they carry the same authority as the locked decisions above.

- **`camera_api` is the source of truth for camera behaviour.** Never modify anything under `nuraeye-rt/mobile_app/packages/**` or `mobilecctvapp/packages/**` without the user's explicit confirmation. If the NVR needs camera behaviour the contracts do not cover, stop and ask. (Consequence for this phase: the ONVIF `GetStreamUri` fallback in CAM-07 is not in `camera_api`; see Open Question 1.)
- Never touch the old VMS or mobile app repos from this project unless the user asks. They are reference only. Research read them; no file outside `/Users/gokul/Desktop/Vizenlink_Vms` was modified.
- Core value is "never miss footage". The NVR retention janitor is the only component that deletes recordings; MediaMTX runs with `recordDeleteAfter: 0s`. SQLite is the source of truth.
- Nothing is exposed to the LAN without auth (API and media). Phases 1-2 are loopback/CLI only.
- Time: store UTC; NVR clock authoritative; display in the site IANA time zone.
- Scope v1: LAN only, VizenLink/NuraEye cameras only, no AI in the core.
- Stack: Python 3.13 (uv) + FastAPI + SQLite/Alembic + MediaMTX v1.21.3 (fMP4). Old-VMS defects not to carry over: IP-keyed cameras, `segments.json` index, `atexit` path deletion, `recordDeleteAfter: 1d`, anonymous MediaMTX, `debug=True`, static serving of the project dir.
- GSD workflow: file-changing work goes through a GSD command; session handoff rules (`.planning/handoff/LATEST.md`) apply to executors.

## Summary

Phase 1 is greenfield. The repo contains only planning documents, so everything below (package, DB, CLI, CI, simulator, contracts) is new. The hard part is not the framework choices, which the project-level research already made; it is reproducing the exact wire behaviour of the Dart `camera_api` and proving the reproduction in CI without access to a private repository. This research read every Dart file that matters, the firmware source behind several claims, the current published camera API documents, and ran the risky Python and MediaMTX mechanics on this machine. Several project-level assumptions turn out to be wrong or stale, and those are listed first because they change plans.

The Dart tests contain no JSON golden fixtures. `camera_api/test/fixtures/` holds only two `.mkv` files; every other expectation is an inline string inside a Dart test. "Vendor the golden fixtures" therefore means: copy the Dart test files verbatim as reference, hand-curate JSON fixtures and a `behaviors.yaml` from them (each fixture carries a source path and line range), and let the lock file detect when an upstream test changes. An optional Dart conformance runner (Dart 3.13.3 is installed here, `camera_api` can be depended on by path read-only) can later capture real request traces to cross-check the Python client.

**Primary recommendation:** build one standalone `vizenlink_nvr.camera` package whose only HTTP entry point is a single `http.py` (case-preserving httpx 0.28.1, a dedicated TLS context with `SECLEVEL=0`, pre-request certificate pinning by `SSLContext.sslobject_class`, 421/unreachable event bus). Drive it from a service layer that both the Typer CLI and the Phase 3 API call. Prove it with three layers: (1) a table-driven contract suite fed by hand-curated golden fixtures and an in-process TLS fake camera that records raw header bytes; (2) a real MediaMTX v1.21.3 binary started per OS in CI to prove default-deny, with a negative-control config so the probes are known to be able to fail; (3) an opt-in hardware smoke suite for the one real camera that settles the open camera facts.

### Findings that change the project-level assumptions

| # | Finding | Evidence | Consequence |
|---|---------|----------|-------------|
| F1 | The firmware **REST session table holds 10 sessions**, not 6. | `#define NURAEYE_SESSION_MAX_CLIENTS      10` `[VERIFIED: nuraeye-rt/nuraeye/nuraeye_session.h:25]`. The Dart comment still says `NURAEYE_SESSION_MAX_CLIENTS = 6` `[VERIFIED: camera_api/lib/src/lan/nuraeye/nuraeye_client.dart:68-71]`. The published doc says "fixed-size array of **10 slots**" `[CITED: nuraeye-rt/docs/external-api/camera-rest-api.md:56-58]`. | Do not hard-code a number. Keep one cached session per (host, account) and serialize logins; the number only matters for the simulator's LRU test (make it configurable, default 10). |
| F2 | **RTSPS live view allows 2 concurrent clients per stream, not 3.** The roadmap flag "3 clients per stream" is wrong for current firmware. | `#define RTSPS_LIVEVIEW_MAX_CLIENTS 2` inside `#ifndef` `[VERIFIED: nuraeye-rt/ameba-rtos-pro2/project/nuraeye/src/module_rtsps.h:151-153]`; firmware test "3rd client rejected" `[CITED: nuraeye-rt/design/FR-camera-firmware.md FR-CF-153]`. | The NVR must hold exactly one upstream RTSPS connection per camera stream. The smoke test measures the real cap instead of assuming 3. |
| F3 | The camera's TLS certificate is a **shared public sample** (port 443: PolarSSL sample, `CN=localhost`, expired 2023-09-22; RTSPS ports: another sample, expires 2029). Every camera presents the same certificate and key. | `[CITED: nuraeye-rt/kb/wiki/known-security-risks.md, row SR-11, measured on a live camera 2026-10-22]` | Per-camera TOFU pinning currently yields the **same fingerprint for every camera** and does not authenticate a camera. Pin anyway (it detects future per-camera certificates, SR-11's planned fix) but (a) never use chain/expiry verification, (b) document that identity rests on the 421 serial check plus digest auth, (c) never describe the pin as MITM protection in user-facing text. |
| F4 | The camera **does not compare the WSSE `created` timestamp with its own clock** in digest verification, so NVR clock skew does not break LAN logins. | `user_table_verifyDigest` computes the digest and a constant-time compare, with no time input `[CITED: nuraeye-rt/onvif/core/user_table.c:355-373, read in full; falsification attempt is smoke test HW-07]`. The WAN path has a separate replay guard (last 64 nonces) that does not apply to LAN `[CITED: design/Camera-WAN-MQTT-API.md:124]`. | Resolves the "WSSE clock-skew tolerance" flag on paper. Keep the nonce fresh on every request. HW-07 sends `created` values +/- 1 h and +/- 24 h to confirm. |
| F5 | On current firmware `POST /nuraeye/live-stream-uri` **always returns transport `rtsp`** with `Profile_1` -> port 554 `/high`, `Profile_2` -> 555 `/medium`, `Profile_3` -> 556 `/mobile`. ONVIF exposes exactly two profiles (`Profile_1`, `Profile_2`). The camera's default codec is **H.265 on all three streams**. | `[CITED: nuraeye-rt/docs/external-api/camera-rest-api.md:1391-1426, camera-onvif-api.md:467, :803, :1574]` (published 2026-10-21 for firmware build 20261019+). | `Profile_3` is excluded from NVR stream selection. Store the codec per stream. The project-level assumption "H.264 only" in ARCHITECTURE.md is out of date and matters for Phase 3 browser playback (H.265 is not playable in many browsers). Older design docs still describe three ONVIF profiles and `/low`; the smoke test (HW-11) settles it. |
| F6 | `camera_api` has **no `GetStreamUri` client**. If a dev firmware build has WebRTC enabled, `live-stream-uri` returns `webrtc` and a signaling URL, not an RTSP URL. | `grep` for `GetStreamUri` in `camera_api/lib` returns only a comment `[VERIFIED: live_stream_uri_client.dart:12]`; transport branch `[VERIFIED: live_stream_uri_client.dart:20-26]`. | The RTSP-with-`WEBRTC_STREAMING` flag needs a fallback outside `camera_api` (ONVIF `GetStreamUri`, documented in the camera ONVIF doc). That is a "contract not covered" case, so it is Open Question 1. |
| F7 | The mobile app's TLS handshake workaround is needed in Python too: the camera runs mbedTLS 2.28.x on the Ameba Pro 2 and OpenSSL 3.2+ default security levels break the handshake. The reference Python tooling uses `ciphers="DEFAULT:@SECLEVEL=0"`. | `[CITED: nuraeye-rt/testing_utilities/onvif_client.py:24-36 and docs/external-api/quick-start.md "lower the minimum TLS security level if your TLS library needs it"]`. `set_ciphers("DEFAULT:@SECLEVEL=0")` is accepted by Python 3.13 on macOS OpenSSL 3.5.9 `[VERIFIED: experiment, scratch venv]`. | The camera-only `SSLContext` must set it. Apply it to this one context, never process-wide. |
| F8 | REST 429 bodies carry `retry_after_seconds` as a top-level field, but `error_msg` is just "Too many failed sign-in attempts". Dart extracts retry time only with the regex `retry in (\d+) s` from the message. | Body example `[CITED: camera-rest-api.md:123-131]`; Dart parse `[VERIFIED: camera_result.dart:65-69]` `static Duration? parseRetryAfter(String text) { ... RegExp(r'retry in (\d+) s')`; `NuraeyeRestClient._unwrap` reads only `error_msg` from an error body `[CITED: nuraeye_rest_client.dart `_unwrap`]`. | Python parses **both** (`retry_after_seconds` first, regex second). Golden fixtures cover both shapes. Administrator blocks are short (15 s doubling to at most 30 s) `[CITED: camera-rest-api.md:132]`. |
| F9 | `WsDiscoveryClient` code defaults differ from its documentation. Code: multicast wait 5 s; unicast cap **30 s**, straggler wait **10 s**, send interval **50 ms**. `API_REFERENCE.md` says 15 s / 5 s. CONTEXT's "unicast cap 15 s" comes from the stale doc. | `Duration overallCap = const Duration(seconds: 30),` `Duration stragglerWait = const Duration(seconds: 10),` `Duration sendInterval = const Duration(milliseconds: 50),` `[VERIFIED: ws_discovery_client.dart:93-97]`; doc `[CITED: API_REFERENCE.md "scanUnicast ... overallCap = 15s ... stragglerWait = 5s"]`. | Use the code values (they are the proven ones: 253 probes x 50 ms ~ 12.7 s of sending). |
| F10 | `Keystore` and `service account` can disagree. A key stored in the logged-in admin's Keychain / Credential Manager / Secret Service is invisible to a system service running as another account. | Reasoning from OS keystore scoping `[ASSUMED]` (verify in Phase 8 packaging); the CLI is run by an admin while the Phase 2 service will not be. | Ship a key-source setting (`auto`/`keyring`/`file`), record the key id and an encrypted canary in the DB, and make `nvr status` report "credentials decryptable: yes/no". Phase 8 should default services to the key file. |
| F11 | `sqlalchemy` needs the **`[asyncio]` extra** (greenlet), and Alembic autogenerate renders a custom `TypeDecorator` as `db.UtcDateTime()` without an import, producing a migration that crashes. | Both reproduced in the scratch venv (`ImportError: ... requires that the Python 'greenlet' library`; `NameError: name 'db' is not defined`). Fix with `render_item` verified (`alembic check: no drift`). | Install `sqlalchemy[asyncio]~=2.1`; put a `render_item` hook in `env.py` rendering `UtcDateTime` as `sa.BigInteger()`. |
| F12 | MediaMTX HLS answers an anonymous request with **302** (cookie check) before the **401**. A test that asserts the first status code, or "not 200", gives a false pass or false fail. Also with the permissive old-style config WHEP returns 404 and playback returns 400 (not 200), so "status != 200" cannot prove default-deny. | Both observed on v1.21.3 `[VERIFIED: experiment]`. | Auth probes must follow redirects and assert **exactly 401** per protocol, and the suite needs a negative-control run with the permissive config. |
| F13 | The factory-password probe must treat **any successful login with `admin`/`password` as "factory password"**, even if `password_change_required` is false. | Mobile app returns `factoryPassword` for any `CameraSuccess` from `isPasswordChangeRequired()` and never inspects the boolean `[CITED: /Users/gokul/mobilecctvapp/lib/app_state/camera_onboarding.dart `probeFactoryLogin` switch]`; dev builds without the gate keep `admin/password` `[CITED: design/FR-camera-firmware.md FR-CF-158 text "opt-in for a dev build"]`. | Mirror exactly. Do not branch on the boolean. |

### Research flags: status after this research

| Roadmap research flag | Status | What is settled | What only the real camera can settle |
|-----------------------|--------|-----------------|--------------------------------------|
| Case-preserving HTTP client | Settled in Python | httpx 0.28.1 and httpx2 2.16.0 both send user-supplied header names byte-for-byte on HTTP/1.1 `[VERIFIED: experiment, raw-socket TLS server]`. HTTP/2 must stay off (default off). | HW-06: camera ignores a lower-cased `x-vizenlink-camera-id` (shows why preservation matters) and answers 421 to the exact-case header. |
| WSSE clock-skew tolerance | Settled on paper (F4) | Camera does not use `created` for time checks. | HW-07 skewed-`created` logins. |
| Non-admin streaming account | Documented, unverified | `User` role may "watch live video (`live-stream-uri` ...)" `[CITED: camera-rest-api.md:115]`; RTSP is authorised against the account role `[CITED: API_REFERENCE.md "Camera accounts and roles"]`. D-08 keeps `admin` anyway. | HW-08 creates a `User` account, DESCRIBE over RTSPS, deletes it (opt-in write). |
| RTSPS concurrency | Settled in source (F2): 2 per stream | Third connection is closed before TLS `[CITED: testing_utilities/rtsps_third_client_reject_test.py docstring]`. | HW-09 measures the real cap and the failure shape. |
| RTSP with `WEBRTC_STREAMING` enabled | Documented: current firmware always `rtsp` (F5) | Fallback design exists (Open Question 1). | HW-10 records `transport` for all three tokens. |

## Architectural Responsibility Map

Phase 1 has no browser tier. The tiers are the layers of the headless backend plus the OS and the media process.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Camera wire protocol (REST, SOAP, discovery, results) | Camera protocol layer (`camera/`) | - | Standalone mirror of `camera_api`; no DB, web or CLI imports so the same tests run against the simulator and a real camera. |
| Onboarding orchestration (probe, password change, verify, read, select streams, persist) | Service layer (`services/`) | Camera protocol layer | One code path reused by the CLI now and the Phase 3 API later (D-15). |
| Re-IP healing | Service layer | Camera protocol layer (events, discovery) | Policy (backoff, ambiguity, blank credentials) belongs with the registry, not in the protocol client. |
| Camera registry, capabilities cache, stream rows, settings | Persistence (SQLite + Alembic) | Service layer | DB is the source of truth (FND-02 in Phase 2 builds on this). |
| Credential encryption and key custody | Secrets module (`secrets/`) | OS keystore / filesystem | Key never leaves the secrets module; DB holds only ciphertext. |
| UTC time model and site-zone rendering | Core (`timeutil.py`, DB type) | CLI (render) | Conversion happens at the edges only; storage and logic are UTC. |
| MediaMTX config generation, pinned binary, self-check | Media plane module (`media/`) | MediaMTX process | Config is code; the process is only started for validation and probes in Phase 1. |
| Admin CLI (tables, `--json`, prompts, exit codes) | Presentation (`cli/`) | Service layer | No logic of its own; renders service outcomes. |
| Contract drift detection and fixtures | Test/tooling (`contracts/`, `tools/`) | CI | Mechanical, not conventional. |

## Standard Stack

All versions verified against PyPI on 2026-10-26 (`curl https://pypi.org/pypi/<pkg>/json`). The project-level STACK.md already fixed the main choices; this table adds what Phase 1 needs and what it does not.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CPython (via uv) | 3.13 (floor 3.11) | Runtime | STACK.md decision. `.python-version` = `3.13`. uv installs it on any OS. |
| uv | 0.13.5 (latest); local host has 0.10.9 | Env, lockfile, runner | STACK.md. CI pins via `astral-sh/setup-uv`. |
| httpx | 0.28.1 | All camera HTTP (REST + SOAP) | Preserves header case on HTTP/1.1, accepts a custom `ssl.SSLContext`, async. Wrapped behind `camera/http.py` so swapping to `httpx2` 2.16.0 (drop-in, header case verified) is a one-file change. |
| cryptography | 50.0.2 | AES-256-GCM for credentials; self-signed certs for the simulator | Standard, wheels for all three OS. |
| keyring | 25.7.0 | OS keystore access (Keychain, Credential Manager, Secret Service) | De-facto standard. `NoKeyringError` subclass of `KeyringError` on fail backend `[VERIFIED: experiment]`. |
| ifaddr | 0.2.0 | Enumerate NICs and prefix lengths | Pure Python; replaces `netifaces` (D-18). |
| defusedxml | 0.7.1 | Parse untrusted XML (UDP ProbeMatches, SOAP) | XXE/entity-expansion safe. Used with `{*}Tag` wildcard lookups to mirror Dart's `namespace: '*'`. |
| SQLAlchemy[asyncio] | 2.1.6 | ORM/Core, async session | STACK.md. The `[asyncio]` extra is mandatory (F11). |
| aiosqlite | 0.22.1 | Async SQLite driver | STACK.md. Prototype with WAL + FK pragmas works on 3.13. |
| Alembic | 1.20.1 | Migrations (batch mode) | STACK.md. Programmatic `upgrade head`; `alembic check` in CI. |
| Typer | 0.27.3 | Admin CLI | Built on click; `CliRunner(input=...)` drives hidden prompts in tests `[VERIFIED: experiment]`. |
| rich | 15.0.0 | Tables for human output | Typer's table renderer; `--json` bypasses it. |
| pydantic | 2.14.1 | Wire models, service outcomes | STACK.md. |
| pydantic-settings | 2.16.1 | `NVR_*` environment configuration | STACK.md. |
| platformdirs | 4.13.5 | Per-OS data/config/log directories | STACK.md. |
| PyYAML | 6.0.3 | Generate `mediamtx.yml`; read `behaviors.yaml` and OpenAPI | MediaMTX accepts JSON too `[VERIFIED: --validate-conf accepted a JSON file]`, but YAML keeps a readable generated header. |
| tzdata | 2026.5 | IANA database on Windows (`zoneinfo` has none there) | Required for FND-03 on Windows CI. |
| tzlocal | 5.4.5 | Host IANA zone name for the default site zone (D-21) | Cross-platform; fall back to `UTC` if it fails. |

### Supporting (dev and test)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 | Test runner | All tests |
| pytest-asyncio | 1.4.1 | Async tests (`asyncio_mode = "auto"`) | Camera layer and services |
| pytest-timeout | 2.4.0 | Kill hung network tests | Every test (default 30 s; 120 s for `mediamtx`) |
| ruff | 0.17.2 | Lint and format | CI + pre-commit |
| mypy | 2.4.0 | Types (strict on `camera`, `services`, `secrets`) | CI on Linux |
| hatchling | 1.32.4 | Build backend | Packaging; migrations included as package data |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx 0.28.1 | httpx2 2.16.0 | Pydantic-maintained successor; header case verified identical. Pinning (`sslobject_class`) was **not** re-verified on it (the test run was blocked), so re-run the pin test before switching. Keep the wrapper. |
| defusedxml + `{*}Tag` | xmltodict ~=1.0 (STACK.md choice) | Phase 1 needs ~8 SOAP operations and namespace-agnostic element lookups; ElementTree wildcards mirror the Dart code one-to-one and avoid xmltodict's attribute-prefix quirks. xmltodict can still be used for the larger Phase 6 surface. |
| Typer | click / argparse | Typer gives typed options and `CliRunner`; argparse has no hidden-prompt helper. |
| Hand-written 4 wire models | `datamodel-code-generator` 0.86.0 from OpenAPI | Phase 1 reads four endpoints (identity, login, capabilities, live-stream-uri). Hand models plus a test that every field name exists in the vendored OpenAPI is cheaper. Generate in Phase 6 when the surface is large. |
| `keyring` only | key file only | D-14 asks for both. See F10 for the service-account catch. |
| AES-GCM (`cryptography`) | Fernet | Fernet is AES-128-CBC+HMAC; D-14 says AES-256-GCM. |

### Installation

```bash
uv init --package --name vizenlink-nvr --python 3.13   # src layout, hatchling
uv add "httpx==0.28.1" "cryptography~=50.0" "keyring~=25.7" "ifaddr~=0.2" "defusedxml~=0.7" \
       "sqlalchemy[asyncio]~=2.1" "aiosqlite~=0.22" "alembic~=1.20" "typer~=0.27" "rich~=15.0" \
       "pydantic~=2.14" "pydantic-settings~=2.16" "platformdirs~=4.13" "pyyaml~=6.0" \
       "tzdata" "tzlocal~=5.4"
uv add --dev "pytest~=9.1" "pytest-asyncio~=1.4" "pytest-timeout~=2.4" "ruff~=0.17" "mypy~=2.4"
```

**Version verification:** every row above was read from the PyPI JSON API on 2026-10-26 (version and `requires_python`; all accept 3.11+ except where noted). Dates of first release range from 2006 to 2022 for the established packages (see audit).

## Package Legitimacy Audit

`gsd-tools query package-legitimacy check --ecosystem pypi ...` returned **SUS for every package**. The cause is the tool, not the packages: the seam has no PyPI download counts (`weeklyDownloads: null` -> reason `unknown-downloads`), and `too-new` / `no-repository` fire because `publishedAt` is the date of the **latest release** and some PyPI metadata omits a repository URL. Each package was cross-checked with the PyPI JSON API (first-release date, current version) and is either named in the project STACK.md (selected from official sources) or a standard, long-lived tool.

| Package | Registry | Age (first release) | Downloads | Source Repo | Verdict (seam) | Disposition |
|---------|----------|---------------------|-----------|-------------|----------------|-------------|
| httpx | PyPI | 2019-07 | n/a (unknown-downloads) | github.com/encode/httpx | SUS (tool limit) | Approved, in STACK.md |
| cryptography | PyPI | 2014-01 | n/a | none in metadata (pyca/cryptography) | SUS (too-new = latest release 2026-09-30) | Approved |
| keyring | PyPI | 2009-08 | n/a | github.com/jaraco/keyring | SUS (tool limit) | Approved |
| ifaddr | PyPI | 2014-07 | n/a | github.com/pydron/ifaddr | SUS (tool limit) | Approved, in STACK.md |
| defusedxml | PyPI | 2013-02 | n/a | github.com/tiran/defusedxml | SUS (tool limit) | Approved |
| typer | PyPI | 2019-12 | n/a | github.com/fastapi/typer | SUS (too-new = latest release 2026-10-06) | Approved |
| rich | PyPI | 2019-11 | n/a | github.com/Textualize/rich | SUS (tool limit) | Approved |
| sqlalchemy | PyPI | 2006-02 | n/a | sqlalchemy.org | SUS (too-new = latest release) | Approved, in STACK.md |
| aiosqlite | PyPI | 2017-05 | n/a | none in metadata (omnilib/aiosqlite) | SUS (no-repository) | Approved, in STACK.md |
| alembic | PyPI | 2011-11 | n/a | github.com/sqlalchemy/alembic | SUS (too-new) | Approved, in STACK.md |
| pydantic / pydantic-settings | PyPI | 2017-05 / 2019-08 | n/a | github.com/pydantic/* | SUS (too-new) | Approved, in STACK.md |
| platformdirs | PyPI | 2021-05 | n/a | github.com/tox-dev/platformdirs | SUS (too-new) | Approved, in STACK.md |
| pyyaml | PyPI | 2011-07 | n/a | pyyaml.org | SUS (tool limit) | Approved |
| tzdata / tzlocal | PyPI | 2016-08 / 2012-09 | n/a | github.com/python/tzdata ; none in metadata | SUS (too-new) | Approved |
| pytest, pytest-asyncio, pytest-timeout | PyPI | 2010 / 2015 / 2012 | n/a | github.com/pytest-dev/* | SUS (too-new / tool limit) | Approved |
| ruff, mypy, hatchling | PyPI | 2022 / 2009 / 2022 | n/a | astral / mypy-lang / pypa | SUS (too-new) | Approved |
| httpx2 (alternative only) | PyPI | 2026-05 | n/a | github.com/pydantic/httpx2 | not run through the seam | Not installed in Phase 1 |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all of the above by the seam, for the tool-limit reasons stated. Planner instruction: do **one** `checkpoint:human-verify` task ("review the dependency list and `uv.lock` before the first `uv sync`"), not one per package. Commit `uv.lock` and install with `uv sync --locked` thereafter. Packages named only here as alternatives (`httpx2`, `datamodel-code-generator`, `xmltodict`) are not installed in Phase 1.

## Architecture Patterns

### System Architecture Diagram

```
                       nvr cameras add --host H [--port P]
                                   |   (CLI: hidden password prompt, renders outcome, exit code)
                                   v
 +-----------------------------------------------------------------------------------------+
 | OnboardingService.add()        (services/; the only place with flow logic)              |
 |                                                                                         |
 |  1 identity  NuraeyeClient.are_you_nuraeye_device_with_retry()   3 x 8 s, 1 s apart      |
 |        no answer at all ........................................... UNREACHABLE         |
 |        answered but not genuine / HTTP error / bad body ............ UNSUPPORTED         |
 |  2 factory probe  ONE login admin/"password", fresh session (no cache)                  |
 |        login succeeds ....... FACTORY  -> prompt new password -> ONVIF SetUser(admin)    |
 |                                           -> clear sessions -> continue with new password|
 |        401 ................. CONFIGURED -> prompt password                              |
 |        429 ................. BLOCKED(retry_after)        timeout/refused -> UNREACHABLE  |
 |  3 verify   clear session, authenticated GET /nuraeye/capabilities   (never GetDeviceInfo)|
 |        401 -> WRONG_CREDENTIALS   428 -> NEEDS_NEW_PASSWORD   429 -> BLOCKED             |
 |  4 read     serial (REQUIRED) , MAC, device info, name+location, capabilities, TLS pin   |
 |  5 streams  Media2 GetProfiles -> select main/sub -> POST /nuraeye/live-stream-uri each  |
 |  6 persist  ONE transaction: camera + credential(AES-GCM) + capabilities + streams       |
 +--------------------------+--------------------------------------------------------------+
                            | calls                                       | writes
                            v                                             v
   +-------------------------------------------+            +-----------------------------+
   | camera/  (mirror of camera_api, no DB/web)|            | db/ (SQLite WAL, Alembic)   |
   |  http.py  <- ONLY HTTP entry point        |            | secrets/ (AES-GCM, keyring  |
   |   case-preserving, SECLEVEL=0, TLS pin,   |            |   or 0600 key file)         |
   |   421 + unreachable events                |            +-----------------------------+
   |  nuraeye/  onvif/  discovery/  result.py  |
   +--------------------+----------------------+
                        | HTTPS (self-signed, mbedTLS 2.28)  | UDP 239.255.255.250:3702
                        v                                    v
              VizenLink / NuraEye camera  (REST /nuraeye/*, SOAP /onvif/*, RTSPS 554/555)

   Separate path (FND-04):  media/config.py -> mediamtx.yml -> pinned mediamtx v1.21.3
                            -> nvr mediamtx check [--probe]  (generate, --validate-conf, optional live probes)
```

### Recommended Project Structure

```
vizenlink-nvr/                      # repo root = /Users/gokul/Desktop/Vizenlink_Vms
├── pyproject.toml  uv.lock  .python-version     # uv, hatchling; pytest/ruff/mypy config; markers
├── src/vizenlink_nvr/
│   ├── camera/                     # == camera_api mirror. Imports nothing from db/services/cli.
│   │   ├── result.py               # Success | Failure(kind, reason, http_status, retry_after) | Timeout
│   │   ├── connection.py           # CameraConnection(host, port, username, password: SecretStr, serial, mac)
│   │   ├── http.py                 # THE choke point: httpx client factory, TLS ctx, pin, events, raw capture
│   │   ├── events.py               # CameraIdMismatchEvent + in-process notifier (mirror of CameraIdMismatchNotifier)
│   │   ├── wsse.py                 # digest + created/nonce generation (golden vectors)
│   │   ├── nuraeye/                # client.py (session cache, call), capabilities.py, live_stream_uri.py, models.py
│   │   ├── onvif/                  # soap.py (envelope, fault-first), device.py, media2.py
│   │   └── discovery/              # ws_discovery.py (probe, parse, multicast, unicast sweep)
│   ├── services/                   # onboarding.py, recovery.py, registry.py, streams.py, settings.py (CLI + Phase 3 API share these)
│   ├── secrets/                    # vault.py (AES-GCM), keysource.py (keyring | file), permissions.py
│   ├── db/                         # engine.py (pragmas), models.py, types.py (UtcDateTime), migrations/ (package data)
│   ├── media/                      # config.py (default-deny), binary.py (pinned fetch+verify), check.py (probes), pins.json
│   ├── cli/                        # app.py (Typer), render.py (tables/--json), prompts.py, exitcodes.py
│   ├── timeutil.py  paths.py  logging.py  errors.py
├── contracts/
│   ├── camera_api/                 # verbatim vendored copies (read-only reference) + provenance
│   ├── camera_api.lock.json        # sha256 of every upstream file this repo mirrors + upstream commit
│   ├── behaviors.yaml              # rule IDs -> source file:lines -> test node ids
│   └── fixtures/                   # hand-curated golden JSON/XML (each with `source:`)
├── sim/fake_camera/                # asyncio TLS camera + UDP WS-Discovery responder + fault plans
├── tools/                          # drift_check.py, vendor_contracts.py, fetch_mediamtx.py
├── tests/{unit,contract,integration,mediamtx,hardware}/
└── .github/workflows/ci.yml
```

### Pattern 1: Typed results, never exceptions (mirror of `CameraResult`)

**What:** `Success[T] | Failure | Timeout`. `Failure.kind` is a closed enum covering Dart's subtypes plus the two Python needs.
**Dart source:** `camera_result.dart` (sealed `CameraResult`, `CameraForbidden`, `CameraBlocked(retryAfter)`, `CameraPasswordChangeRequired`, `CameraCredentialsMissing`, `CameraTimeout`).

| Wire condition | Dart returns | Python `Failure.kind` | `reason` text (fixture parity) |
|----------------|--------------|-----------------------|--------------------------------|
| REST 403 | `CameraForbidden(error_msg)` | `FORBIDDEN` | `error_msg` |
| REST 428 | `CameraPasswordChangeRequired(error_msg)` | `PASSWORD_CHANGE_REQUIRED` | `error_msg` |
| REST 429 | `CameraBlocked(error_msg, parseRetryAfter)` | `BLOCKED` + `retry_after` | `error_msg` |
| REST 401 (on an authenticated call or on login) | `CameraFailure('HTTP 401: <error_msg>')` | `UNAUTHORIZED` | `HTTP 401: <error_msg>` |
| REST 421 | `CameraFailure('HTTP 421: <error_msg>')` plus mismatch event | `ID_MISMATCH` | `HTTP 421: Camera ID mismatch` |
| REST other non-2xx | `CameraFailure('HTTP <code>: <error_msg>')` | `GENERIC` | same |
| REST body not JSON (any status) | `RestFailure('Malformed response body', statusCode)` -> `HTTP <code>: Malformed response body` | `BAD_RESPONSE` | same |
| Identity challenge failure | `CameraFailure(error_msg)` **without** a status prefix | `GENERIC` (or `UNREACHABLE`) | `error_msg` |
| Connection refused / no route / DNS / TLS error | `CameraFailure(exception text)` | `UNREACHABLE` | exception text |
| Timeout | `CameraTimeout` | `Timeout` | - |
| SOAP fault | see behaviour S-01 | `FORBIDDEN` / `BLOCKED` / `PASSWORD_CHANGE_REQUIRED` / `GENERIC` | fault reason text, plus ` [ter:<subcode>]` for other faults |

Sources: `[VERIFIED: nuraeye_client.dart (the `_authed` result switch, lines ~392-414) and (`_login`, lines ~522-544)]`, `identity` branch `rest.RestFailure(:final reason) => CameraFailure<bool>(reason)` `[VERIFIED: nuraeye_client.dart:583]`. Dart folds transport exceptions into a plain `CameraFailure(e.toString())` and reserves `CameraTimeout` for `TimeoutException` only `[CITED: nuraeye_rest_client.dart `get`/`post` catch blocks]`. The Python `UNREACHABLE` kind is an **improvement that keeps Dart's reason text**: D-02 needs "no answer at all" to be distinguishable from "answered with an error".

### Pattern 2: One HTTP choke point (`camera/http.py`)

Everything that talks to a camera over HTTPS goes through one factory (the Python twin of `createCameraHttpClient`). It must:

1. **Preserve header case.** httpx 0.28.1 on HTTP/1.1 sends names exactly as given: wire bytes captured were `X-VizenLink-Camera-Id: VZL-1` and `Authorization: Bearer t` `[VERIFIED: experiment, raw TLS socket server]`. Never enable HTTP/2 (h2 lower-cases names). Add `X-VizenLink-Camera-Id` only when the serial is known and non-empty `[VERIFIED: camera_id_mismatch.dart:6]` `const String cameraIdHeaderName = 'X-VizenLink-Camera-Id';`; do not add it if the caller already supplied it (any case) `[CITED: insecure_camera_http_client.dart, `_send`]`.
2. **Use a dedicated `ssl.SSLContext`:** `PROTOCOL_TLS_CLIENT`, `check_hostname=False`, `verify_mode=CERT_NONE`, `set_ciphers("DEFAULT:@SECLEVEL=0")` (F7), `sslobject_class`/`sslsocket_class` subclasses that compare the SHA-256 of the peer certificate **right after the handshake and before any request bytes are sent** (Code Example 1). On mismatch raise `ssl.SSLCertVerificationError`; the wrapper converts it to `Failure(kind=TLS_CHANGED)` (see the end of this pattern). Experiment: match -> HTTP 200; mismatch -> `ConnectError`, and the server received **no HTTP request** `[VERIFIED: experiment]`. Expired certificates are accepted because chain/expiry checks are off (F3).
3. **Emit events.** On any 421 response with a camera id set: publish `CameraIdMismatchEvent(host, port, expected_id)`. On connection refused/no route: publish `unreachable=True` immediately; also when no response headers arrive within 8 s `[VERIFIED: insecure_camera_http_client.dart:73-74]` `static const Duration _silentAfter = Duration(seconds: 8);` (the caller's own timeout still decides the result). No id, no event `[CITED: camera_id_header_test.dart "a 421 without a cameraId (nothing was addressed) is not reported"]`.
4. **Keep raw request capture optional** (test hook) so contract tests can assert header names byte-for-byte.
5. **Be the single place** to swap `httpx` -> `httpx2`.

Add a `FailureKind.TLS_CHANGED` for pin mismatches (not in Dart; D-11 treats the fingerprint as a mutable attribute, and Pitfall 15 in PITFALLS.md requires an explicit "trust new certificate" action). Because F3 says the fingerprint is shared today, the likely real-world trigger is a future firmware moving to per-camera certificates.

### Pattern 3: Session cache with single-flight login (mirror of `NuraeyeClient`)

Held in an object owned by the camera-layer factory (Dart uses process-wide statics; Python must not, so tests stay isolated and a fixture can "clear caches").

- Key: `f"{host}|{username}"` `[VERIFIED: nuraeye_client.dart:111]` `String get _sessionKey => '${connection.host}|${connection.username}';`
- Default lifetime `[VERIFIED: nuraeye_client.dart:59]` `static const int _defaultExpiresInSec = 1800;`; proactive refresh margin `[VERIFIED: nuraeye_client.dart:64]` `static const Duration _expiryLeeway = Duration(seconds: 15);`. Every successful authenticated call pushes `valid_until` to `now + expires_in_sec` (idle timeout), only if the cached token is still the one used.
- One in-flight login per key; concurrent callers await the same task (`dict[str, asyncio.Task]`). Failed login is not cached.
- A 401 on an authenticated call: drop the session, log in once more, retry the operation once; if that also returns 401 the result is `UNAUTHORIZED` (feeds D-09 `auth_failed`, no further automatic attempts).
- `clear_session_for(host)` removes every account's entry for that host (Dart removes keys starting with `host|`). Call it before the factory probe, before verification, after `SetUser`, after a host change, and on camera removal.
- Login request body: `{"auth_credentials": {"username", "password_digest", "nonce", "created"}}` plus optional `client_label` `[VERIFIED: rest_identity_discovery_client.dart:25-36]`; path `'/nuraeye/session/login'`. Response fields: `token`, `expires_in_sec`, `username`, `role`, `password_change_required`.
- Send a `client_label` such as `VizenLink NVR` (display/audit only `[CITED: camera-rest-api.md:38]`) so the owner can recognise the NVR's session. Cap at 32 characters `[VERIFIED: nuraeye_session.h:32]` `#define NURAEYE_SESSION_LABEL_MAX_LEN    32`.

### Pattern 4: Add flow as a service with a closed outcome type

`OnboardingService` returns discriminated outcomes; the CLI renders them, Phase 3 maps them to API errors. Steps in the diagram. Rules:

- **Scan sends blank credentials only** (D-01). The ProbeMatch `Scopes` also carry `onvif://www.onvif.org/MAC/<mac>`, `name/` and `location/` (`ONVIF_FIXED_SCOPE_MAC = "onvif://www.onvif.org/MAC/"`), usable as display hints, but identity probe plus `GetScopes` stay authoritative. (Constant quoted from the old VMS file; `[CITED: vms/python/onvif_utils.py]`.)
- **Manual add never auto-retries credentials.** At most one factory probe; a 401 on the real password verification ends the add (D-03, D-09). Re-prompt only on explicit user action.
- **Already registered:** after the serial is read, if the serial exists with a different host, treat it as re-IP (update host, clear sessions, reprobe streams) instead of inserting a duplicate; if the same host, return `ALREADY_REGISTERED` without writing.
- **Password change:** `SetUser` envelope with only `Username` and `Password` (no `UserLevel`) `[VERIFIED: multi_user_accounts_test.dart:390-400]`, XML-escape `& < > "`. New-password rules: 8-32 characters, not `password` in any case `[CITED: mobilecctvapp/lib/utils/camera_account_rules.dart validateNewCameraPassword]`; camera also refuses it (`password_not_allowed`). After success, clear sessions and verify with the **new** password via a fresh login (this is also the proof that the change took effect).
- **Lost reply after `SetUser`:** if `SetUser` times out, the camera may have changed. The next run's factory probe returns `CONFIGURED` and the owner enters the password they chose. Document this in the CLI help; do not attempt both passwords automatically (each wrong attempt is a lockout count).

Outcome taxonomy and CLI mapping (wording from the mobile app `[CITED: mobilecctvapp/lib/app_state/camera_onboarding.dart verifyAndReadCamera; camera_account_rules.dart cameraBlockedMessage]`):

| Outcome | Trigger | CLI message | Exit |
|---------|---------|-------------|------|
| `UNREACHABLE` | identity probe Timeout/`UNREACHABLE` after 3 attempts; or verify Timeout/`UNREACHABLE` | "Could not reach the camera — check the connection and try again." | 10 |
| `WRONG_CREDENTIALS` | verify returns `UNAUTHORIZED` | "Incorrect username or password." | 11 |
| `UNSUPPORTED_DEVICE` | identity probe answered but not genuine / HTTP error / malformed | "This device is not a VizenLink camera, or its firmware is not supported." | 12 |
| `NEEDS_NEW_PASSWORD` | factory probe login succeeded, or verify returned 428 | prompts for a new password; after success: "Use this new password in the VizenLink mobile app too." | 13 |
| `BLOCKED` | 429 anywhere | "This camera is locked after too many failed sign-ins. Try again in about N minutes." (about a minute if <= 60 s; without a number: "... in a few minutes.") | 14 |
| `NO_SERIAL` | `getSerialNumber` empty or failed | "This camera did not report a serial number and cannot be added." | 15 |
| `STREAMS_UNAVAILABLE` | profiles or stream URIs unreadable | "Could not read the camera's video streams. Try again." | 16 |
| `ALREADY_REGISTERED` | serial exists | "Camera <serial> is already registered" (+ "address updated" if the host changed) | 0 / 17 |
| `OK` | row committed | table of what was stored | 0 |

Exit codes are a proposal; what matters is that they are stable and tested. `FORBIDDEN` on the admin account is treated as a generic failure with its own message (it should not happen).

### Pattern 5: Atomic add (CAM-06)

All camera I/O (steps 1-5) completes **before** the transaction opens. Step 6 is a single `async with session.begin()`. Prototype: an exception after `flush()` inside the block left **0 rows**; a naive `datetime` was rejected by the type; microseconds round-tripped; WAL and `foreign_keys` were on `[VERIFIED: experiment, SQLAlchemy 2.1.6 + aiosqlite 0.22.1, scratch DB]`. Test every failure point with the simulator (fault at identity, probe, verify, each read, profiles, URIs, and a forced exception inside the DB block) and assert `SELECT count(*)` is 0 for `camera`, `camera_credential`, `camera_capabilities`, `camera_stream`, then re-run the add successfully. Secrets are encrypted before the transaction opens, so an exception cannot leave plaintext anywhere.

### Pattern 6: Re-IP healing (CAM-10), mirror of `camera_address_recovery.dart`

Triggers: a `CameraIdMismatchEvent` from the HTTP layer, an explicit `nvr cameras reprobe`, or the add flow meeting a known serial. Phase 1 has no daemon, so the healer is a service class with injected `discover`, `read_serial`, `now`, `is_on_lan`; Phase 2 subscribes it to the event bus.

1. Ignore the event if no stored camera has that serial **and** that host (already moved or removed). Skip if a heal for that serial is in flight. Skip if `now < not_before[serial]`.
2. For `unreachable` events: skip placeholder hosts; skip if the stored address verified as this camera within the last 60 s; ask the stored address for its serial (unauthenticated `GetDeviceInformation`, 4 s). If it answers with the right serial, remember `verified_until = now + 60 s`, clear failures, stop.
3. Search: multicast first (`thorough=False`), then unicast sweep (`thorough=True`). For each candidate skip the old host; read its serial with **blank credentials**; collect hosts whose serial equals the target. Exactly one match -> update the stored host. More than one -> change nothing (log "N devices claim this serial"). None -> schedule backoff.
4. Backoff: `base 30 s * 2^(n-1)`, capped at 10 min `[CITED: mobilecctvapp camera_address_recovery.dart baseBackoff 30 s, maxBackoff 10 min, _scheduleRetry]`. Failures reset on success.
5. On success: update `host`, `host_updated_at`, `last_seen`; clear the session cache for the old host; the next authenticated call carries the serial header, so a wrong guess is caught by 421 instead of being trusted.

The stored password is never sent during steps 1-3. From the mobile app's class comment: candidates are probed with "**blank** credentials, not the camera's saved password ... a saved password must never be sent to some other device" `[CITED: mobilecctvapp camera_address_recovery.dart class doc]`.

### Pattern 7: Stream selection (CAM-07)

Inputs: Media2 `GetProfiles` (endpoint resolved from `GetServices`, namespace `http://www.onvif.org/ver20/media/wsdl`, fail with "Media2 service not offered by this camera" if absent, as Dart does `[CITED: onvif_video_encoder_client.dart `resolveMedia2Endpoint`]`) and `POST /nuraeye/live-stream-uri`.

```
profiles = media2.get_profiles()          # [{token, name, venc_token, width, height, encoding}], skip entries without VideoEncoder/Width/Height
if not profiles: STREAMS_UNAVAILABLE
ordered  = sorted(profiles, key=lambda p: (-(p.width * p.height), token_natural_key(p.token)))
main     = ordered[0]
sub      = ordered[1] if len(ordered) > 1 else ordered[0]      # sub_is_main = True when only one profile
for each of {main, sub}: POST /nuraeye/live-stream-uri {"profile_token": token}
        transport == "rtsp"  -> store port, path, transport, url scheme
        transport == "webrtc"-> fallback: ONVIF GetStreamUri (Open Question 1) else STREAMS_UNAVAILABLE
```

- Never hard-code the number of streams `[CITED: STREAMING_GUIDE.md:77-83 "Never hardcode three streams: read the list and its length"]`. Re-read profiles on every `reprobe` and before any reconnect.
- `Profile_3` is not in the ONVIF list and is the mobile app's stream; it is never selected. On current firmware this yields `Profile_1` (2560x1440 or 1920x1080, `/high`, port 554) as main and `Profile_2` (1280x720, `/medium`, port 555) as sub `[CITED: camera-onvif-api.md:608; camera-rest-api.md:1423-1424]`.
- Store `codec` from the profile's `VideoEncoder` `encoding` attribute (fall back to child `<tt:Encoding>`) `[CITED: camera-onvif-api.md:865-876 shows `encoding="H264"` on tr2:VideoEncoder]`. Default is H.265 on current firmware (F5).
- Store **port and path, not the full URL**; build `rtsps://<host>:<port><path>` from the current host so a re-IP does not leave stale URLs. Never store credentials in the URL (Phase 2 percent-encodes credentials when it builds the MediaMTX source).
- Treat the URL's host as untrusted: use the connection host, not the host inside the response.

### Pattern 8: Credential vault (D-14)

- `cryptography` `AESGCM` with a 32-byte random data key, 12-byte random nonce per encryption, ciphertext bound to the row with AAD `b"vizenlink-nvr/cred/v1|" + serial + b"|" + username`. Verified: round trip works; decrypting under a different AAD raises `InvalidTag` `[VERIFIED: experiment]`.
- Table `camera_credential(serial PK/FK, username, ciphertext BLOB, nonce BLOB, key_id TEXT, enc_version INT, updated_at)`. `key_id` lets a future key rotation re-encrypt row by row.
- Key source order from `NVR_SECRETS_BACKEND` (`auto`|`keyring`|`file`). `auto`: use `keyring` only if the active backend is not the `fail`/`null` backend; any `KeyringError` falls back to the file. Run keyring calls in a worker thread with a 5 s timeout (a locked Linux Secret Service can block waiting for a prompt `[ASSUMED]`).
- File source: `<data_dir>/secrets/data.key`, directory 0700, file 0600, created with `os.open(..., O_CREAT|O_EXCL, 0o600)`; refuse to start when group/other bits are set (POSIX). Windows: remove inheritance and grant only the current user via `icacls <path> /inheritance:r /grant:r "<user>:F"` using `subprocess.run([...], shell=False)` `[ASSUMED: needs the Windows CI test described in Validation]`.
- Store an encrypted canary in `app_setting` (`secrets_canary`). `nvr status` and every command that reads credentials check the canary first: wrong key -> report `credentials unreadable (key source mismatch)` instead of failing every camera (F10).
- Passwords are `pydantic.SecretStr` in memory, redacted in `repr`, and a logging filter scrubs `Authorization`, `Bearer`, `password`, `password_digest`. CLI never echoes them; prompts go to stderr (Pitfall 9).

### Pattern 9: Time model (FND-03)

- Storage: integer **epoch microseconds** in an SQLAlchemy `UtcDateTime` `TypeDecorator`; bind rejects naive datetimes; result is an aware UTC `datetime`. Use integer arithmetic `(dt - EPOCH) // timedelta(microseconds=1)` (not float timestamps). Prototype passed round-trip and naive-rejection `[VERIFIED: experiment]`.
- `utc_now()` returns `datetime.now(UTC)`; ban `datetime.utcnow()` (deprecated; the old VMS used it) with a ruff rule (`DTZ003`/`DTZ005`).
- Site zone: `app_setting.site_timezone` (IANA string validated by `ZoneInfo`), default `tzlocal.get_localzone_name()` with fallback `UTC`. `tzdata` is a hard dependency (Windows has no system IANA db).
- Rendering helper returns local wall time plus abbreviation and offset. Day windows are computed in the site zone and converted to UTC: `America/New_York` 2026-03-08 = 23.0 h, 2026-11-01 = 25.0 h, 2026-06-01 = 24.0 h; fall-back shows two distinct UTC instants as the same wall clock `01:30` with offsets -04:00 (fold 0) and -05:00 (fold 1); spring-forward jumps `01:59:59-05:00` -> `03:00:00-04:00` `[VERIFIED: experiment, zoneinfo]`. Add `Australia/Lord_Howe` (30-minute DST shift) to the parametrized zones.
- Camera clocks are never stored as authoritative. If the layer parses `GetSystemDateAndTime` it returns it as data for display only (Phase 4 uses it for clock sync state).

### Pattern 10: MediaMTX default-deny baseline (FND-04)

Pinned release assets and checksums (from the release's `checksums.sha256`, downloaded 2026-10-26; the `darwin_arm64` tarball's computed hash matched `bc1a0762...`) `[VERIFIED: github.com/bluenviron/mediamtx/releases/tag/v1.21.3]`:

| Asset | SHA-256 |
|-------|---------|
| mediamtx_v1.21.3_darwin_amd64.tar.gz | 8a8416ee2ff5d17d9366498b6d88b76ab6d3afcda50b6d7321ccddb349bdbaf2 |
| mediamtx_v1.21.3_darwin_arm64.tar.gz | bc1a0762fd18ffb413bcd81dcb9a072ac159fbd1f27e79ac6f14598aaac5ed3f |
| mediamtx_v1.21.3_linux_amd64.tar.gz | 0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635 |
| mediamtx_v1.21.3_linux_arm64.tar.gz | 27f038237cb5f77a724f6afc58eca2798f2bc4edf9989895631a80eeb41a4fe2 |
| mediamtx_v1.21.3_linux_armv6.tar.gz | cbacd828dd7c8bb67954eee2b0b5590b1f1f6994faa6fcd86a3cf0ba50213095 |
| mediamtx_v1.21.3_linux_armv7.tar.gz | 134b53bfdb26583d02e1c27fc256d587cf3482e80c9e3b49083595e19a096284 |
| mediamtx_v1.21.3_windows_amd64.zip | b2f5246b07cb72961df03b8d5e8cad43dc657bcf3f49a87bb031bdf22721af74 |

Store this table in `media/pins.json`; the downloader verifies before extracting and extracts with `tarfile.extractall(filter="data")` / checked `zipfile` (no path traversal). There is no Windows arm64 asset; Windows arm64 hosts would need the amd64 build under emulation `[ASSUMED]`.

The shipped v1.21.3 `mediamtx.yml` is **open by default**: `authInternalUsers` has user `any` with empty `pass` and `ips: []` holding `publish`, `read`, `playback`, plus an `any`-from-loopback `api/metrics/pprof` user; `rtmp`, `srt`, `moq` default to `true`; `playbackAllowOrigins`, `hlsAllowOrigins`, `webrtcAllowOrigins` default `["*"]` `[VERIFIED: v1.21.3 release archive, `mediamtx.yml` extracted and read in full this session]`. The generated config must therefore **replace** `authInternalUsers` entirely.

Generated config (Phase 1 shape; Phase 3 changes bind addresses and `authMethod`), validated and run:

```yaml
authMethod: internal
authInternalUsers:                      # no `any` user at all
  - user: nvr-control
    pass: sha256:<base64 of sha256(random control password)>
    ips: [127.0.0.1/32, "::1/128"]
    permissions: [{action: api}]
api: true
apiAddress: 127.0.0.1:9997
metrics: false
pprof: false
playback: true
playbackAddress: 127.0.0.1:9996
rtsp: true
rtspAddress: 127.0.0.1:8554
rtspTransports: [tcp]
hls: true
hlsAddress: 127.0.0.1:8888
webrtc: true
webrtcAddress: 127.0.0.1:8889
webrtcLocalUDPAddress: 127.0.0.1:8189
rtmp: false
srt: false
moq: false
pathDefaults:
  record: false
  recordFormat: fmp4
  recordDeleteAfter: 0s
paths:
  all_others:
# Hardening on top of what was measured: set apiAllowOrigins, playbackAllowOrigins, hlsAllowOrigins and
# webrtcAllowOrigins explicitly to [] (the shipped defaults are [] for the API and ["*"] for the others).
```

Measured on MediaMTX v1.21.3 (darwin arm64) with that shape (without the explicit CORS lines) `[VERIFIED: experiment]`:

| Probe | Result |
|-------|--------|
| `--validate-conf` on the config | exit 0, "configuration file is valid"; a typo key (`recrdDeleteAfter`) exits 1 with `unknown field`; a wrong type exits 1 -> strict, use it as the drift guard on every upgrade |
| Startup log | one `started with listener` line per listener, all on `127.0.0.1` (API 9997, playback 9996, RTSP 8554, HLS 8888, WebRTC 8889 + UDP 8189); none for RTMP/SRT/MoQ |
| Anonymous RTSP `ANNOUNCE` (publish) | `RTSP/1.0 401 Unauthorized` |
| Anonymous RTSP `DESCRIBE` (read) | `401` |
| Anonymous HLS `index.m3u8` | `302` (cookie check) then **`401`** after following the redirect |
| Anonymous WHEP (read) / WHIP (publish) | `401` / `401` |
| Anonymous playback `/list`, `/get` | `401` / `401` |
| API without credentials / wrong password / correct credentials | `401` / `401` / `200` |
| API-only user publishing over RTSP or reading HLS | `401` (permissions are per action) |
| TCP 1935, 1936, 8890, 8892, 8893, 8322, 9998, 9999 | connection refused |
| **Negative control** (same file but the shipped `any` users) | RTSP `ANNOUNCE` -> `200 OK`; DESCRIBE -> 404; WHEP -> 404; playback `/list` -> 400; API anonymous -> `200` |

The negative control is mandatory in the suite: it shows that "status != 200" would mis-judge several protocols and that each probe really fails when the config is open. Run the real binary on each OS in CI (`tests/mediamtx/`), via a small `MediaMtxProcess` context manager (start with the config path, wait for the `[API] started` log line, terminate in `finally`; never leave a process behind). `nvr mediamtx check [--probe]` reuses the same code so the owner can run the proof on their own box.

### Pattern 11: Contract mirroring, lock and drift (FND-05, D-17)

See "Vendoring inventory" and "Behaviour catalogue" below. Mechanics:

- `contracts/camera_api.lock.json`: `{schema, upstream: {repo, commit, dirty, reviewed_on}, files: [{path, sha256, vendored_as, mirrored_by: [...], behaviors: [...]}]}`. Upstream commit at research time: nuraeye-rt `a413efbe0ed804dc9b0f0e4b00701ba065af537b` (2026-10-22), working tree dirty for `rtsp_replay_session.dart` only (not in the list); mobilecctvapp `abe32d7d2f8b909fd3ad44193bf8ebefe1b13a20`.
- Every mirrored Python module starts with `# mirrors: <upstream path>@<sha256[:12]>`; a meta-test checks the header hashes equal the lock and that the vendored copy hashes equal the lock (tamper/partial-update guard, runs in CI without the sibling repo).
- `tools/drift_check.py --upstream <nuraeye-rt> --mobile <mobilecctvapp>` compares upstream files with the lock and prints a diff for changed files; exits 1 on drift. A changed upstream file means re-review, update Python and fixtures, bump the lock.
- Optional later step (needs Dart, installed here as 3.13.3): `tools/dart_conformance/` depending on `camera_api` **by path, read-only**, run a fixed scenario against the simulator and capture request traces as fixtures. No upstream file is touched.

### Pattern 12: Fake-camera simulator (D-19)

An asyncio TLS server on `127.0.0.1:<random port>` (self-signed certificate generated per session with `cryptography`) plus a UDP responder for WS-Discovery. It parses HTTP/1.1 by hand (about 80 lines) so it can record **raw header names and values exactly as received**; that is what lets tests assert case preservation. Do not use a framework that normalizes headers.

Behaviour to implement (each toggled by a `FaultPlan` per route, consumed in order):

| Area | Behaviour |
|------|-----------|
| Identity | `POST /nuraeye/identity`: verify request digest of `are-you-onchip-nuraeye`, reply digest of `yes-i-am-onchip-nuraeye` with the same nonce/created; `genuine=False` mode returns a wrong digest |
| Accounts | admin/`password` initially; `default_password_in_use`; first-password gate (428 everywhere except the allowed list); `SetUser` rejects `password`; up to 5 accounts; roles |
| Login | digest check; token; `expires_in_sec` (configurable, 0 allowed); LRU session table with configurable size (default 10); lockout counter (5 consecutive failures -> 429 with `retry_after_seconds`; admin blocks 15 s) |
| Camera ID | header compared exactly (whitespace trimmed) before routing and auth; mismatch -> 421 with `{"error_code":421,"error_msg":"Camera ID mismatch"}` (REST) or SOAP Receiver fault (ONVIF); empty/absent header never refuses; serial never appears in the reply |
| REST | `/nuraeye/capabilities`, `/nuraeye/live-stream-uri` (rtsp or webrtc mode), `/nuraeye/health` |
| ONVIF | `GetDeviceInformation`, `GetScopes`/`SetScopes`, `GetNetworkInterfaces`, `GetServices`, `SetUser`, Media2 `GetProfiles`, optional `GetStreamUri`; SOAP fault bodies at HTTP 200 and non-200 |
| Faults | 401, 403, 421, 428, 429 (with and without `retry_after_seconds`), 503 firmware upgrade, timeout (sleep longer than the client timeout), connection drop, malformed body, SOAP fault at 200 / 400 / 428 / 429 |
| Recording | every request appended to `sim.requests` with raw header list, body, TLS peer, and whether credentials/Authorization were present (used to prove "scan never sends credentials" and "exactly one factory attempt") |
| WS-Discovery | UDP socket on `127.0.0.1:<port>` answering Probes with a firmware-shaped `ProbeMatches` (Types `tdn:NetworkVideoTransmitter`, XAddrs, Scopes incl. MAC/name/location); also answers every Probe regardless of Types because the real camera does `[CITED: camera-onvif-api.md:1576]` |

Discovery tests target `127.0.0.1` with injectable multicast group, port and host list; they do not depend on multicast working on CI runners.

### Vendoring inventory (what to copy into `contracts/camera_api/`)

All paths are relative to `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt` unless stated. Line counts and 12-character sha256 prefixes were taken from the working tree at commit `a413efbe` on 2026-10-26 (the lock stores full hashes). Copy byte-for-byte; never edit a vendored file.

**A. Documents (reference + OpenAPI parity test)**

| Upstream path | Lines | sha256[:12] | Use |
|---------------|-------|-------------|-----|
| `mobile_app/packages/camera_api/API_REFERENCE.md` | 2265 | dd54015ee202 | Result type, camera-ID check, accounts/roles, discovery, RTSPS sections |
| `mobile_app/packages/camera_api/SETTINGS_API_GUIDE.md` | 1121 | 0d79acaa0b47 | Capability flag semantics (Phase 6 will rely on it; vendor now so the lock is complete) |
| `mobile_app/packages/camera_api/STREAMING_GUIDE.md` | 479 | 0a5ef0aa0575 | Stream profiles, RTSP vs WebRTC, "never hardcode three streams" |
| `design/Camera-REST-API.openapi.yaml` | 1781 | 5eefa2a7f936 | The file the Dart REST generator reads (`tools/generate_dart_rest_client.py`); drives field-name parity test |
| `docs/external-api/camera-rest-api.openapi.yaml` | 2357 | 0e71b0658cdf | Published edition (v1.0, 2026-10-21, firmware 20261019+); the two OpenAPI files differ in prose, so also test that their path/operation sets agree |
| `docs/external-api/camera-onvif-api.md` | 1579 | 9dba44a27aaf | SOAP samples (GetNetworkInterfaces, GetServices, Media2 GetProfiles), known limitations |
| `docs/external-api/camera-rest-api.md` | 1699 | 6f7ee1cde7e6 | Error bodies (421, 428, 429, 403), live-stream-uri ports/paths |
| `docs/external-api/{README.md,CHANGELOG.md,quick-start.md}` | 46 / 5 / 85 | 0802a7fe5dcc / b3f539f865d7 / 6084df947670 | Common facts, TLS adapter example |

**B. Dart source mirrored by Python modules (reference copies)**

| Upstream (under `mobile_app/packages/camera_api/lib/src/`) | Lines | sha256[:12] | Python module |
|-----|-----|-----|-----|
| `camera_result.dart` | 118 | eaa81aa28a68 | `camera/result.py` |
| `camera_connection.dart` | 207 | 4e3f9ec35f61 | `camera/connection.py` (endpoint paths `/onvif/device_service` etc.) |
| `camera_role.dart` | 98 | 403a2de6c777 | `camera/roles.py` (`Administrator`/`Operator`/`User`, `atLeast`) |
| `recording_mode_types.dart` | 99 | 871a4cd15860 | `camera/nuraeye/capabilities.py` (wire values `continuous`, `scheduled`, `event_triggered`) |
| `device_reset_types.dart` | 27 | 093227387abe | `camera/onvif/device.py` (`Soft`/`Hard`; Soft only in tests) |
| `lan/camera_id_mismatch.dart` | 47 | 1e0f913e3a37 | `camera/events.py`, `camera/http.py` |
| `lan/wsse_digest.dart` | 59 | 103b118108cc | `camera/wsse.py` |
| `lan/insecure_camera_http_client.dart` | 113 | ba12f28f9848 | `camera/http.py` |
| `lan/nuraeye/nuraeye_client.dart` | 617 | 2e06d2ad3a40 | `camera/nuraeye/client.py` (session cache, `_authed`, identity, retry) |
| `lan/nuraeye/nuraeye_rest_client.dart` | 118 | c6af6ee3efb7 | `camera/nuraeye/rest.py` (envelope unwrap, URI/query split) |
| `lan/nuraeye/rest_identity_discovery_client.dart` | 71 | 49ec7db1d149 | `camera/nuraeye/models.py` (identity, login bodies) |
| `lan/nuraeye/rest_result.dart` | 51 | 5f873ea471c1 | `camera/nuraeye/rest.py` |
| `lan/nuraeye/capabilities_client.dart` | 227 | 109c790ed5ae | `camera/nuraeye/capabilities.py` |
| `lan/nuraeye/live_stream_uri_client.dart` | 154 | 4fc87450a10b | `camera/nuraeye/live_stream_uri.py` |
| `lan/onvif/onvif_device_client.dart` | 611 | bd2e63476c9c | `camera/onvif/device.py` (subset: serial, device info, network, services, scopes, SetUser, system date) |
| `lan/onvif/onvif_video_encoder_client.dart` | 618 | af62024e35e1 | `camera/onvif/media2.py` (`GetServices` resolution + `GetProfiles` only; encoder settings are Phase 6) |
| `lan/onvif/soap_fault.dart` | 59 | ffb2a21c3a54 | `camera/onvif/soap.py` |
| `lan/discovery/ws_discovery_client.dart` | 210 | cf09c72d1da6 | `camera/discovery/ws_discovery.py` |

**C. Dart tests (reference copies; these are the "golden" sources)**

| Upstream (under `mobile_app/packages/camera_api/test/`) | Lines | sha256[:12] | Becomes |
|-----|-----|-----|-----|
| `camera_id_header_test.dart` | 115 | 88d965374c07 | HTTP-01/03/04 (raw-socket wire assertions) |
| `case_preserving_http_client_test.dart` | 53 | 6ffa5701c377 | HTTP-02 |
| `camera_unreachable_event_test.dart` | 62 | 599de6494d8a | HTTP-05 |
| `nuraeye_digest_test.dart` | 34 | ad66302fa821 | WSSE-01 known-answer vector `F3ldVt6HHuN3/vvi4vYtwEH8+w8=` |
| `nuraeye_are_you_nuraeye_device_test.dart` | 157 | 35d288f9a9f3 | IDN-01..03 |
| `nuraeye_client_session_expiry_test.dart` | 111 | 6ffd8cd2f390 | SES-01..04 |
| `nuraeye_client_concurrency_test.dart` | 44 | c9ee54256923 | SES-05 |
| `nuraeye_client_failure_reason_test.dart` | 68 | fe0a11909b48 | RES-05 |
| `capabilities_client_test.dart` | 127 | bd3a1537bb10 | CAP-01..03 |
| `live_stream_uri_client_test.dart` | 108 | ae443fa52a38 | LST-01..03 |
| `onvif_device_client_test.dart` | 322 | 22b2a080b692 | DEV-01..07, SOAP-01 (HTTP-200 fault) |
| `onvif_video_encoder_client_test.dart` | 186 | 11bc9184b22b | PRF-01/02 (GetProfiles samples) |
| `ws_discovery_wire_format_test.dart` | 45 | 22fbb2a08e8f | DSC-02 (firmware-shaped ProbeMatches XML) |
| `multi_user_accounts_test.dart` | 402 | 658923c1c163 | SOAP-03..05 (role/blocked/password-change faults), DEV-06 |
| `camera_connection_test.dart` | 73 | e44e71d2da4d | connection immutability, `copyWithHost` (CAM-10) |
| `rest_mock_helpers.dart` | 54 | d8a33f926baa | The mock login envelope: `{'error_code': 0, 'error_msg': 'Success', 'output': {'token', 'expires_in_sec'}}` |

Not vendored (no Phase 1 behaviour): `camera_secure_storage_test.dart` (D-14 is a deliberate difference), all WAN/KVS/MQTT/cloud files, `recordings_client`, `onvif_recording/search/replay`, settings clients, RTSP session classes (Phase 5/6 add them to the lock as they arrive), and the `.mkv` fixtures.

**D. Hash-tracked only (different repo, `/Users/gokul/mobilecctvapp`, commit `abe32d7d`)**

| Path | Lines | sha256[:12] | Why |
|------|-------|-------------|-----|
| `lib/app_state/camera_onboarding.dart` | 254 | 479ce0bf01a8 | factory probe, genuineness check, verify-and-read order, wording |
| `lib/app_state/camera_scan.dart` | 99 | 03b02401d5f4 | multicast then unicast, 3 s identity probe, name fallback, blank credentials |
| `lib/app_state/camera_address_recovery.dart` | 313 | e222376b0b38 | healer algorithm and backoff |
| `lib/utils/camera_account_rules.dart` | 96 | fb46706cd3f5 | password rules, `cameraBlockedMessage` |

Recommendation: copy these four too (they are app code from the same organization, reference only), under `contracts/mobile_app/`, because several behaviours (D-01..D-07, D-12) are defined by them and not by `camera_api`. If the user prefers not to copy app code, keep the hashes and put the extracted rules in `behaviors.yaml` only.

### Behaviour catalogue (each row = one rule in `behaviors.yaml` and at least one pytest node)

Seed fixtures come from the vendored Dart tests (section C) and the published docs. "Source" is where the rule is defined; a pytest node must reference the rule id with `@pytest.mark.behavior("ID")`, and a meta-test fails when a rule has no test or a marker cites an unknown id.

| ID | Rule | Source |
|----|------|--------|
| RES-01 | Results are `Success`, `Failure`, `Timeout`; `Forbidden`, `Blocked(retry_after)`, `PasswordChangeRequired`, `CredentialsMissing` are failure subtypes | `camera_result.dart` |
| RES-02 | Re-typing a failure for another result type keeps the subtype and `retry_after` | `camera_result.dart:115-118` |
| RES-03 | `retry_after` = `retry_after_seconds` field if present, else regex `retry in (\d+) s` on the message, else unknown (Python superset, F8) | `camera_result.dart:65-69`, `camera-rest-api.md:123-131` |
| RES-04 | REST status mapping: 403 Forbidden, 428 PasswordChangeRequired, 429 Blocked, other `HTTP <code>: <error_msg>`; same mapping for login | `nuraeye_client.dart:392-414, 522-544` |
| RES-05 | A rejected call's reason contains the numeric status (`401`) and the camera's text | `nuraeye_client_failure_reason_test.dart` |
| RES-06 | Timeout is never folded into Failure; transport errors become `Failure(UNREACHABLE)` with the exception text | `nuraeye_rest_client.dart` (catch blocks) |
| RES-07 | REST body that is not a JSON object -> `HTTP <code>: Malformed response body`; 2xx with non-object `output` -> `{}`; error bodies may lack `output` (the 421 body has none) | `nuraeye_rest_client.dart` (_unwrap), `camera-rest-api.md:158-164` |
| HTTP-01 | `X-VizenLink-Camera-Id: <serial>` sent verbatim on every request when the serial is known; absent or empty serial sends nothing | `camera_id_header_test.dart` tests 1-2 |
| HTTP-02 | Other header names (`Authorization`) keep their case on the wire | `case_preserving_http_client_test.dart` |
| HTTP-03 | A 421 with a camera id publishes exactly one mismatch event (host, port, expected id) and the caller still receives the failure | `camera_id_header_test.dart` test 3 |
| HTTP-04 | A 421 without a camera id publishes nothing | `camera_id_header_test.dart` test 4 |
| HTTP-05 | Connection refused publishes one `unreachable` event (with id) and still raises to the caller; no id -> no event; normal answer -> no event | `camera_unreachable_event_test.dart` |
| HTTP-06 | No response headers for 8 s publishes `unreachable` once; the caller's own timeout is unchanged | `insecure_camera_http_client.dart:62, 73-74` |
| HTTP-07 | Camera checks the id **before** authentication: wrong id + wrong password -> 421, wrong password alone -> 401; empty header counts as absent; serial never in the reply | `testing_utilities/camera_id_check_test.py` CID-01..04 (simulator mirrors it; HW-06 confirms) |
| HTTP-08 | REST uses `Content-Type: application/json` (+ `Authorization: Bearer`); SOAP uses `application/soap+xml; charset=utf-8` | `nuraeye_rest_client.dart` (_headers), `onvif_device_client.dart:557` |
| HTTP-09 | TLS: self-signed accepted, `SECLEVEL=0`, pin compared before any request bytes, mismatch -> `TLS_CHANGED` | F3, F7 (Python-specific, no Dart twin) |
| WSSE-01 | digest = `base64(SHA1(nonce_raw + created + password))`; known-answer vector for nonce `AAAAAAAAAAAAAAAAAAAAAA==`, created `2026-01-01T00:00:00.000Z`, password `test-password` is `F3ldVt6HHuN3/vvi4vYtwEH8+w8=` | `nuraeye_digest_test.dart` (reproduced in Python `[VERIFIED: experiment]`) |
| WSSE-02 | `created` = UTC `%Y-%m-%dT%H:%M:%S.000Z` (milliseconds fixed at `.000`); nonce = 16 random bytes, base64; fresh per request | `wsse_digest.dart:20-27, 51-58` |
| WSSE-03 | SOAP security header shape (UsernameToken, PasswordDigest type URI, Nonce Base64Binary, wsu:Created); Python escapes the username (Dart does not) | `onvif_device_client.dart:534-551` |
| IDN-01 | Identity request digest is of `are-you-onchip-nuraeye`; expected reply digest is of `yes-i-am-onchip-nuraeye` with the **same** nonce/created; `POST /nuraeye/identity`, unauthenticated | `nuraeye_client.dart:556-586` |
| IDN-02 | Wrong reply -> `Success(False)`; HTTP error -> `Failure` (reason = `error_msg`, no status prefix); missing reply -> `Failure("missing reply digest in response")`; timeout -> `Timeout` | `nuraeye_are_you_nuraeye_device_test.dart`, `nuraeye_client.dart:570-585` |
| IDN-03 | Retry variant: 3 attempts, 8 s each, 1 s apart, stops at the first genuine reply, returns the last result otherwise (manual add). Scan: single 3 s attempt per candidate | `nuraeye_client.dart:600-614`, mobile `camera_scan.dart` |
| SES-01 | A fresh session is reused across calls (one login for N calls) | `nuraeye_client_session_expiry_test.dart` |
| SES-02 | A session past `expires_in_sec - 15 s` is refreshed **before** the next call, without needing a 401 (`expires_in_sec: 0` test) | same |
| SES-03 | Each successful call extends the session (ten calls, one login) | same |
| SES-04 | A 401 on an authenticated call triggers exactly one re-login and one retry | same |
| SES-05 | Concurrent calls for one (host, account) share a single login | `nuraeye_client_concurrency_test.dart` |
| SES-06 | Sessions are keyed per (host, account); `clear_session_for(host)` removes all accounts of that host | `nuraeye_client.dart:102-111` |
| SES-07 | Login failures map as RES-04; login without a token -> `Failure("session/login succeeded but returned no token")`; login response fields parsed (`role`, `password_change_required`) | `nuraeye_client.dart:526-544` |
| SOAP-01 | A `<Fault>` is detected **before** the HTTP status: HTTP 200 + Fault -> Failure with the reason text | `onvif_device_client_test.dart` ("SOAP Fault returned with HTTP 200") |
| SOAP-02 | Fault sub-code = the **last** `Subcode/Value` `ter:<Name>`; non-role faults return `reason [ter:<Name>]` | `soap_fault.dart:12-16`, `onvif_device_client.dart:580-581` |
| SOAP-03 | `InsufficientUserLevel` (any HTTP status, e.g. 400) -> Forbidden, not UNAUTHORIZED | `multi_user_accounts_test.dart` role tests |
| SOAP-04 | `TooManyAttempts` fault -> Blocked; bare HTTP 429 -> Blocked; neither is Forbidden | `multi_user_accounts_test.dart` blocked tests |
| SOAP-05 | `PasswordChangeRequired` fault (HTTP 428) -> PasswordChangeRequired; bare 428 too | `multi_user_accounts_test.dart` password-change tests |
| SOAP-06 | Non-SOAP non-200 -> `HTTP <code>: <body>` (proxy HTML) | `onvif_device_client.dart:584-588` |
| SOAP-07 | Fault with HTTP 421 (camera-id) surfaces reason `Camera ID mismatch` and sets kind `ID_MISMATCH` (Python improvement) | `camera-rest-api.md:165` |
| DEV-01 | `getSerialNumber` = first `SerialNumber` text, trimmed, `""` if absent | `onvif_device_client_test.dart` |
| DEV-02 | `getDeviceInformation` = Manufacturer, Model, FirmwareVersion, SerialNumber, HardwareId | same |
| DEV-03 | `getNetworkInterfaceInfo` = first `Name`, `HwAddress`, `Address`; Python normalizes MAC to `AA:BB:CC:DD:EE:FF` | same; sample `camera-onvif-api.md:261-273` |
| DEV-04 | `getDeviceIdentity`: scope items starting `onvif://www.onvif.org/name/` and `.../location/`, percent-decoded; either may be empty | `onvif_device_client.dart:13-14, 250-271` |
| DEV-05 | `setDeviceName/Location` send **one** `Scopes` entry, percent-encoded (`Back%20Yard`); name/location max 32 characters enforced before sending | `onvif_device_client.dart:19-20, 290-299`; test |
| DEV-06 | `setUserPassword` = `SetUser` with `Username` + `Password` only, XML-escaped | `onvif_device_client_test.dart`, `multi_user_accounts_test.dart:390-400` |
| DEV-07 | `getServices` sends `IncludeCapability=false`, returns (Namespace, XAddr) pairs | `onvif_device_client.dart:221-245` |
| PRF-01 | `GetProfiles` (Media2) -> token, Name, VideoEncoder token, Width, Height (+ encoding); profiles without a VideoEncoder or size are skipped; none usable -> failure | `onvif_video_encoder_client.dart` (getProfiles) |
| PRF-02 | Media2 endpoint resolved via `GetServices` namespace `http://www.onvif.org/ver20/media/wsdl`; absent -> "Media2 service not offered by this camera" | `onvif_video_encoder_client.dart` (resolveMedia2Endpoint) |
| PRF-03 | NVR stream selection rule (largest = main, next = sub, single profile = both, Profile_3 never) | this research (Pattern 7) |
| CAP-01 | `wan_command_capable` and `wan_live_view_capable` must be booleans else `Failure("GetCapabilities response missing ...")` | `capabilities_client.dart:158-164` |
| CAP-02 | Missing optional fields default: bools false, ranges 0, `max_users` 1, `max_recording_schedule_windows` **14**, lists empty | `capabilities_client.dart:184-218` |
| CAP-03 | `supported_recording_modes` keeps only `continuous`, `scheduled`, `event_triggered`; unknown strings dropped | `capabilities_client.dart:209-214`, `recording_mode_types.dart:5-18` |
| CAP-04 | Event types / deterrence options tolerate wrong shapes (non-list -> empty) | `capabilities_client.dart:165-177` |
| CAP-05 | Python keeps the raw `output` JSON and a typed superset (adds `camera_id_check`, `night_vision_*_capable`, which Dart's class omits) | OpenAPI capabilities schema; Dart omission is a gap, not a rule |
| CAP-06 | Every field name Python reads exists in the vendored OpenAPI `/nuraeye/capabilities` schema | `Camera-REST-API.openapi.yaml` |
| LST-01 | `POST /nuraeye/live-stream-uri {"profile_token": T}` -> `transport` (`webrtc` or `rtsp`), `port` (int), `url`; all three required | `live_stream_uri_client.dart` tests, `nuraeye_client.dart:222-226` |
| LST-02 | Unknown transport or unparseable URL -> Failure | `live_stream_uri_client.dart` |
| LST-03 | 400 (unknown token), 501, 404 -> Failure (no legacy fallback) | `live_stream_uri_client_test.dart` |
| DSC-01 | Probe: SOAP 1.2 envelope, `Types` = `dn:NetworkVideoTransmitter` with `dn` = `http://www.onvif.org/ver10/network/wsdl`, fresh `uuid:` MessageID, Action `.../discovery/Probe` | `ws_discovery_client.dart:132-150` |
| DSC-02 | ProbeMatches: namespace-agnostic `XAddrs`, first whitespace-separated token starting `http://`/`https://`; default port 80/443; dedupe by host; malformed -> ignored | `ws_discovery_client.dart:152-172`, `ws_discovery_wire_format_test.dart` |
| DSC-03 | Multicast to `239.255.255.250:3702`, wait 5 s | `ws_discovery_client.dart:35-36, 41-42` |
| DSC-04 | Unicast sweep: every host of each local IPv4 /24 except own addresses, one shared socket, 50 ms pacing, 30 s cap, 10 s straggler wait | `ws_discovery_client.dart:93-130, 174-199` |
| DSC-05 | Scan flow: multicast, unicast only when empty; each candidate gets a 3 s identity probe; name = `GetScopes` name, else Model, else `Camera at <host>`; blank credentials only | mobile `camera_scan.dart` |
| HEAL-01..05 | Healer rules 1-5 of Pattern 6 (ids avoid the `REC-` prefix, which belongs to recording requirements) | mobile `camera_address_recovery.dart` |
| ONB-01 | Factory probe: clear session, single login `admin`/`password`; success -> factory; 401 -> configured; 429 -> blocked(retry_after); else unreachable | mobile `camera_onboarding.dart:62-69` |
| ONB-02 | Verify = fresh login + authenticated `GetCapabilities`; 428 -> needs new password; 429 -> blocked; 401 -> wrong credentials; else unreachable | mobile `camera_onboarding.dart` (verifyAndReadCamera) |
| ONB-03 | Post-verify reads are best-effort except the serial | D-06 |
| ONB-04 | Password rules: 8-32 characters, not `password` in any case | mobile `camera_account_rules.dart` |

### Port or rewrite: old VMS Python (`/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms/python/`)

| File | Verdict | Take | Fix / reason |
|------|---------|------|--------------|
| `ws_discovery_scanner.py` (254 lines) | Port the **probe template** only | Envelope text is identical to the Dart probe; `_get_tag_value` idea | Rewrite as asyncio with defusedxml; bind per interface (`IP_MULTICAST_IF`) via `ifaddr`; use `max(prefix, 24)` network instead of a gateway guess through `netifaces` and `8.8.8.8`; no threads, `print`, or global mutable state; add bounds (datagram <= 64 KiB, candidate cap) |
| `onvif_utils.py` | Port selectively | `parse_*_from_scopes`, MAC scope prefix, scope constants, SOAP builders for `SetUser`/`SetScopes` | `created` uses `%f` (microseconds) and `datetime.utcnow()` (deprecated); Dart uses `.000Z`. Escape all interpolated values. `compute_onvif_password_digest` is correct (same as the golden vector) |
| `onvif_http_client.py` (122 lines) | Rewrite | Idea of mapping `ter:NotAuthorized` | Uses `requests`, `verify=False` globally, no fault-before-status, rejects empty username (blank credentials are required), retries 3x on faults (lockout risk), `print`ing responses |
| `nuraeye_http_client.py` (117 lines) | Rewrite | - | Legacy single-endpoint JSON-RPC `POST /nuraeye` with `action`; the Dart client migrated to REST on 2026-08-10 `[CITED: nuraeye_client.dart:12-17]` |
| `onvif_device_service.py`, `onvif_media_service.py` (668 lines) | Reference only | SOAP element names for `GetProfiles`/`GetStreamUri` | Media v1 vs Media2 mix; IP-keyed; returns raw dicts; no typed results |
| `nuraeye_service.py`, `nuraeye_helper.py`, `nuraeye_js_interface.py`, `server.py` | Do not port | - | Flask RPC glue tied to the AngularJS UI and to IP identity (`camera_id = ip.replace('.', '_')`) |
| `mediamtx_client.py` | Phase 2 | `get_tls_fingerprint` Python-`ssl` fallback logic | Shell-pipeline openssl path fails on Windows; Phase 1 only ports the pure-Python fingerprint fetch into `camera/http.py` |
| `mediamtx/mediamtx.yml` | Never ship | - | `any` user with publish/read/playback, `recordDeleteAfter: 1d`, RTMP/SRT on, `*` CORS |

### Repo, CLI, database, CI

**`pyproject.toml` essentials.** `requires-python = ">=3.11"`, `.python-version` 3.13, hatchling `src` layout with `include` for `db/migrations/**` and `media/pins.json`. Entry point `[project.scripts] nvr = "vizenlink_nvr.cli.app:app"`. Pytest: `asyncio_mode = "auto"`, `pythonpath = ["sim"]`, `timeout = 30`, `addopts = "-m 'not hardware and not mediamtx' --strict-markers"`, markers `hardware`, `hardware_destructive`, `mediamtx`, `behavior(id)`. Ruff selects at least `E,F,I,B,UP,DTZ,S,ASYNC`. Mypy `strict = true` for `camera`, `services`, `secrets`.

**CLI surface** (every command accepts `--json` and `--data-dir`; passwords only via hidden prompt, or `--password-stdin` reading the next line(s) from stdin for tests):

| Command | Purpose | Notes |
|---------|---------|-------|
| `nvr cameras scan [--thorough] [--timeout S]` | CAM-01 | `--thorough` also runs the unicast sweep and merges (multicast on camera Wi-Fi can be partial `[CITED: ws_discovery_client.dart:66-69 doc comment]`) |
| `nvr cameras add --host H [--port P] [--name N] [--location L] [--group G]` | CAM-02/03/04/05/06/07/08 | Prompts: password; if factory: new password twice. With `--password-stdin`: line 1 password, then new password and confirmation |
| `nvr cameras list` / `show SERIAL` | registry | `show` renders `added_at` in the site zone (DST proof); never prints secrets |
| `nvr cameras rename SERIAL [--name] [--location] [--group]` | CAM-08 | name/location written to the camera first, cache updated after success; group is DB only |
| `nvr cameras reprobe SERIAL` | CAM-05/CAM-10 | checks reachability with the id header; on 421/unreachable runs the healer; then re-reads capabilities and profiles |
| `nvr cameras set-password SERIAL` | D-09 recovery | re-enter a changed password for an `auth_failed` camera (verify first, store after) |
| `nvr status` | health | DB ok, migration head, credentials decryptable, site zone, camera count and states |
| `nvr mediamtx check [--probe]` | FND-04 | generate, `--validate-conf`, optional live default-deny probes |
| `nvr settings set-timezone ZONE` | FND-03 | validates IANA name |

Prompts and progress go to **stderr**; stdout carries only the result (human table or JSON), so `--json` output is machine-parseable (the CliRunner experiment showed Typer writes the prompt text to stdout by default; pass `err=True`).

**Database (Alembic revision `0001_initial`).** Key tables (all timestamps `UtcDateTime` = INTEGER µs; PRAGMAs set on connect: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`):

| Table | Columns (summary) |
|-------|-------------------|
| `camera` | `serial` TEXT PK; `host`, `https_port`, `mac`, `name`, `location`, `group_tag` (NVR-only), `manufacturer`, `model`, `firmware_version`, `hardware_id`, `tls_fingerprint_sha256`, `state` (`active`/`auth_failed`/`tls_changed`/`unreachable`), `added_at`, `host_updated_at`, `identity_synced_at`, `last_error` |
| `camera_credential` | `serial` PK/FK CASCADE, `username`, `ciphertext`, `nonce`, `key_id`, `enc_version`, `updated_at` |
| `camera_capabilities` | `serial` PK/FK, `raw_json`, `probed_at`, `firmware_version_at_probe` |
| `camera_stream` | PK (`serial`, `role` in `main`/`sub`); `profile_token`, `profile_name`, `venc_token`, `codec`, `width`, `height`, `transport`, `port`, `path`, `sub_is_main`, `probed_at` |
| `app_setting` | `key` PK, `value` JSON text (`site_timezone`, `secrets_canary`, ...) |

Alembic runs programmatically with a **sync** URL for migrations (`sqlite:///...`) while the app uses `sqlite+aiosqlite`; `render_as_batch=True`; `render_item` maps `UtcDateTime` to `sa.BigInteger()` (F11). CI step: `alembic upgrade head` on an empty file then `alembic check` (must report no drift) and a test that the wheel contains the migration files.

**CI (`.github/workflows/ci.yml`).** Runner labels from the runner-images README: `ubuntu-latest` (Ubuntu 24.04 x64), `macos-latest` (macOS 26 arm64), `windows-latest` (Windows Server 2025) `[CITED: github.com/actions/runner-images README]`. Action versions current on 2026-10-26: `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.2`, `actions/cache@v6.1.0`, `actions/upload-artifact@v7.0.2` `[VERIFIED: gh api releases/latest]`.

```
matrix: os: [ubuntu-latest, macos-latest, windows-latest]; python: ["3.13"]   (+ one ubuntu-latest / 3.11 leg for the support floor)
steps: checkout -> setup-uv (cache) -> uv sync --locked
       -> uv run ruff check && ruff format --check          (ubuntu only)
       -> uv run mypy src                                    (ubuntu only)
       -> uv run pytest                                      (default markers: unit + contract + integration, all OS)
       -> uv run python tools/fetch_mediamtx.py              (cached by version+os; verifies sha256 from pins.json)
       -> uv run pytest -m mediamtx                          (all OS: proves default-deny with the real binary)
       -> uv run python tools/drift_check.py --self          (vendored copies match the lock; no sibling repo needed)
       -> uv run alembic upgrade head && uv run alembic check
```

Timeouts: job 20 min; mediamtx tests 120 s each. `NVR_SECRETS_BACKEND=file` in CI so tests never touch a runner's keychain; a separate test mocks `keyring` backends.

### Real-camera smoke suite (D-20) for the one factory-resettable camera

Lives in `tests/hardware/`, marker `hardware`, deselected by default. Environment: `NVR_HW_HOST`, `NVR_HW_USER` (default `admin`), `NVR_HW_PASSWORD` (the camera's current admin password; test-only environment variable, never a CLI flag), `NVR_HW_ALLOW_WRITE=1` for tests that modify the camera, `NVR_HW_ALLOW_RESET=1` for the reset test. The suite starts by recording the camera's serial, name, location and account list, and restores name/location at the end. Reports are written to a gitignored `tests/hardware/reports/<UTC timestamp>.md` with no passwords. **Soft reset only**: `FactoryResetMode.soft` keeps Wi-Fi credentials and the DHCP address; `hard` wipes them and sends the camera back to AP provisioning `[CITED: camera_api/lib/src/device_reset_types.dart enum FactoryResetMode soft/hard doc comments]`. A Soft reset also erases name, location and every extra account, and re-arms the first-password gate `[CITED: camera_api/test/live/live_support.dart "Soft factory reset removes every account and restores admin/password"]`. The Dart live-test helper `LiveCamera.prepare/restore` is the model to follow (prove the gate, change the password, reset at the end, wait for the camera to answer again). Space tests so no more than 3 wrong-password attempts happen inside a block window; Administrator blocks are only 15-30 s but a failed run should wait `retry_after` before continuing.

| ID | Test | Writes? | Settles |
|----|------|---------|---------|
| HW-01 | `nvr cameras scan` on multicast alone, then unicast alone, report which tier sees the camera, on each NIC of the dev host | no | CAM-01; whether the camera's Wi-Fi delivers multicast; macOS Local Network permission for the terminal |
| HW-02 | Manual add of the configured camera (correct password) | DB only | CAM-02/05/07/08, stream rows, codec, ports and paths actually returned |
| HW-03 | Wrong password once, expect `WRONG_CREDENTIALS` with the mobile wording; the simulator test proves the attempt count; on the camera, a correct login right afterwards must still succeed (the counter did not reach a block) | no | CAM-03 |
| HW-04 | Reset flow (needs `ALLOW_RESET`): Soft reset, `add` -> factory probe -> new password -> add succeeds; before the change, a direct `GetProfiles` must answer `PasswordChangeRequired` | camera | CAM-04, F13 |
| HW-05 | Re-IP: store a deliberately wrong host for the serial, run `reprobe`; expect host healed by serial. Also send a request with a wrong id header: expect 421 and a mismatch event | DB | CAM-10, D-12 |
| HW-06 | Header case on a real camera: exact-case `X-VizenLink-Camera-Id` wrong value -> 421; lower-case `x-vizenlink-camera-id` wrong value -> **not** refused if the firmware lookup is case-sensitive (the reason preservation matters) | no | research flag 1 |
| HW-07 | WSSE skew: logins with `created` -1 h, +1 h, -24 h and a good login between each | no | research flag 2 (F4) |
| HW-08 | Create a `User` account, RTSPS DESCRIBE with it on `/high`, delete the account | camera (accounts) | research flag 3 / A7 |
| HW-09 | RTSPS concurrency: N parallel DESCRIBE+SETUP+PLAY clients on one stream until one is refused; record N and whether the refusal is a TCP close before TLS | no | research flag 4 (expect 2) |
| HW-10 | `live-stream-uri` for `Profile_1/2/3`: record `transport`, `port`, `path`; if any is `webrtc`, try ONVIF `GetStreamUri` | no | research flag 5 / F5 / F6 |
| HW-11 | `GetProfiles` (Media2): count, tokens, sizes, `encoding`; RTSPS DESCRIBE each selected stream and read the SDP codec (`H264` vs `H265`) | no | CAM-07, F5 |
| HW-12 | Capabilities: all fields parse; `camera_id_check` true; `default_password_in_use` false after the change | no | CAM-05 |
| HW-13 | Rename and restore name/location (`SetScopes`), including a name with a space and a non-ASCII character; check the 32-character limit behaviour | camera | CAM-08, A11 |
| HW-14 | TLS: fingerprint of port 443 and of 554/555 (expected shared sample, 443 expired per SR-11) and confirm the pin accepts it | no | F3 |

The minimal RTSPS client for HW-08/09/11 (TLS socket, `DESCRIBE`/`SETUP`/`PLAY`, RFC 2617 Digest with realm `ONVIF`, MD5, no `qop`) is about 150 lines; model it on `nuraeye-rt/testing_utilities/rtsps_third_client_reject_test.py` and `simple_rtsp_client.py` (read-only references) `[CITED: API_REFERENCE.md "RTSPS streaming clients": realm="ONVIF", algorithm=MD5, no qop]`. Keep it in `tests/hardware/support/`, not in the product.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Authenticated encryption of stored camera passwords | AES wrapper with homemade nonce handling or XOR/base64 "obfuscation" | `cryptography` `AESGCM` with random 96-bit nonce and AAD | Nonce reuse or missing integrity ruins GCM; verified round trip and AAD failure |
| OS keystore access | Per-OS `ctypes` to Keychain/DPAPI/libsecret | `keyring` (+ the file fallback) | Three platform APIs, edge cases (locked keychains, headless) |
| Network interface/prefix enumeration | `socket.gethostbyname`, the `8.8.8.8` connect trick, `netstat` parsing | `ifaddr` | Pure Python, gives prefix lengths, works on all targets |
| XML parsing of network input | `re` on SOAP or ProbeMatches; `xml.etree` without hardening | `defusedxml.ElementTree` with `{*}Tag` lookups | Entity-expansion/XXE and namespace prefix variance |
| SOAP envelope building | Full ONVIF library (`onvif-zeep`) | ~8 hand-written operations with string templates + escaping helper | STACK.md decision; WSDL parse cost is wasted for the used subset |
| Timezone/DST math | Fixed UTC offsets, `+ timedelta(days=1)` for day ranges | `zoneinfo` + `tzdata`; compute local midnight bounds then convert | Days are 23/25 h twice a year (reproduced) |
| Single-flight login | Ad-hoc flags | A dict of in-flight `asyncio.Task` per key | Concurrent logins evict each other's sessions on the camera `[CITED: nuraeye_client.dart:75-87]` |
| Config validation for MediaMTX | A homemade schema | `mediamtx --validate-conf` of the pinned binary | Strict: rejects unknown fields and wrong types `[VERIFIED: experiment]` |
| CLI parsing and hidden prompts | `argparse` + `getpass` glue | Typer/click prompts and `CliRunner` | Cross-platform hidden input and testable |
| Archive extraction | `tar xf` via shell | `tarfile.extractall(filter="data")`, checked `zipfile` | Path traversal; Windows has no `tar` guarantees |
| Constant-time compare | `==` on digests/tokens | `hmac.compare_digest` | Cheap hygiene (identity reply compare is not secret, the habit still applies) |
| Secret redaction in logs | Hoping nobody logs a password | `SecretStr` + a logging filter + a test that greps outputs | Single test catches all regressions |

**Key insight:** the protocol surface is small but each quirk (header case, fault-before-status, single-flight login, blank-credential discovery, retry-once on 401) exists because of a real incident recorded in the Dart comments. Re-deriving them from the docs loses the incidents; mirroring the Dart behaviour with tests keeps them.

## Common Pitfalls

### Pitfall 1: Treating the TLS fingerprint as camera authentication
**What goes wrong:** the UI or docs say "certificate verified", but every camera presents the same public sample certificate (F3).
**Why it happens:** TOFU pinning assumes a unique certificate per device.
**How to avoid:** pin and enforce (it catches a future per-camera certificate or a rogue server with a different certificate), but word it as "certificate unchanged"; identity comes from the 421 serial check and digest auth. Never enable chain or expiry verification (the 443 certificate expired in 2023).
**Warning signs:** two cameras with an identical fingerprint in the DB (expected today, not a bug).

### Pitfall 2: Weakening TLS for the whole process
**What goes wrong:** `SECLEVEL=0` set on the default context makes every outbound connection (including future cloud calls) accept weak ciphers.
**How to avoid:** build one camera-only `SSLContext` in `camera/http.py`; test that the default `httpx` client elsewhere is unaffected.

### Pitfall 3: A default-deny test that cannot fail
**What goes wrong:** asserting `status != 200` or checking only the first HTTP response passes against an open server (404/400 for unknown paths, 302 on HLS) (F12).
**How to avoid:** assert the exact status per protocol, follow redirects, and run the permissive-config negative control.

### Pitfall 4: Alembic and SQLAlchemy defaults that break at run time
**What goes wrong:** `ImportError: ... requires ... 'greenlet'`; a migration containing `db.UtcDateTime()` raises `NameError` (F11); `server_default=CURRENT_TIMESTAMP` stores naive local text.
**How to avoid:** `sqlalchemy[asyncio]`; `render_item` hook; set timestamps in Python only; a CI test that runs `alembic upgrade head` on an empty database and `alembic check`.

### Pitfall 5: Prompts corrupt machine output
**What goes wrong:** `typer.prompt` writes to stdout, so `nvr cameras add --json` emits `Camera password: ` before the JSON.
**How to avoid:** `err=True` on every prompt; assert in a test that stdout parses as JSON when a password was prompted.

### Pitfall 6: Key custody differs between CLI user and service
**What goes wrong:** credentials encrypted under a key in the admin's keychain cannot be decrypted by the service account after a reboot, so every camera shows as failed (F10).
**How to avoid:** key source setting, key id and canary in the DB, an explicit "credentials unreadable" status, `file` as the service default decided in Phase 8, and a runbook note.

### Pitfall 7: Lockout from well-meaning retries
**What goes wrong:** each wrong digest counts toward the camera's block (5 consecutive failures; admin blocks 15-30 s) `[CITED: camera-rest-api.md:121-132]`. Retrying the stored password after a 401, probing the factory password twice, or sending a saved password during discovery all burn the counter.
**How to avoid:** D-03 and D-09 as hard rules, enforced by a simulator test that counts login attempts per scenario (factory probe = exactly 1; 401 on a stored password = no further attempts until `set-password`).

### Pitfall 8: Unicast sweep surprises
**What goes wrong:** firing 253 probes in a burst triggers an ARP storm that hides replies; sweeping a /16 takes about an hour at 50 ms; on Windows a UDP socket can raise `ConnectionResetError` after probes to closed ports (ICMP unreachable) `[ASSUMED]`; macOS may prompt for Local Network permission on first use `[ASSUMED]`.
**How to avoid:** pace at 50 ms `[VERIFIED: ws_discovery_client.dart:96 + doc comment 74-82]`, use `max(prefix, 24)`, use `asyncio` datagram protocols whose `error_received` ignores resets, and add a CI test on Windows that probes closed local ports and still receives a reply.

### Pitfall 9: Multi-NIC multicast
**What goes wrong:** one multicast socket leaves through the default route only, so cameras on another interface are missed; Docker bridges and link-local addresses add noise.
**How to avoid:** one send per eligible IPv4 adapter with `IP_MULTICAST_IF` set to that adapter's address (skip loopback and 169.254/16), merge replies by host. Python-side improvement over Dart (Dart uses one socket) that keeps the same wire probe.

### Pitfall 10: Trusting what a discovery response says
**What goes wrong:** a spoofed ProbeMatch can carry any `XAddrs` host (an internal service address), which the NVR would then connect to; oversized or malformed datagrams can waste memory.
**How to avoid:** take the host from the datagram source address (log a mismatch with `XAddrs`), use only port and scheme from `XAddrs`, cap datagram size (64 KiB) and candidate count (512), parse with `defusedxml`, validate hosts as IPv4/IPv6 literals or simple hostnames, and require RFC 1918/ULA/link-local addresses for manual add unless an explicit `--allow-public` flag is passed `[ASSUMED recommendation]`.

### Pitfall 11: Treating documentation as the contract
**What goes wrong:** the docs disagree with code and firmware: session cap 6 vs 10 (F1), live-view clients 3 vs 2 (F2), unicast cap 15 s vs 30 s (F9), ONVIF profiles 3 vs 2 and `/low` vs `/mobile` (F5), `H.264 only` vs H.265 default (F5), the REST 429 retry hint (F8).
**How to avoid:** rule of precedence: Dart code and firmware source first, then current published docs (`docs/external-api`, 2026-10-21), then older design docs. Fixtures cite the source line, and the smoke suite re-checks the facts that matter on the real camera.

### Pitfall 12: Stale or lowercase capabilities
**What goes wrong:** Dart's `CameraCapabilities` omits `camera_id_check` and `night_vision_*_capable`, and refuses a response without the two WAN booleans. Copying the class loses fields the NVR needs and can reject a valid dev build.
**How to avoid:** keep raw JSON plus a typed superset; mirror Dart's strict check only as a documented rule (CAP-01) and decide in the service whether a missing WAN flag blocks an add (recommend: it does not; log it).

### Pitfall 13: Name, location and scope encoding
**What goes wrong:** `SetScopes` accepts at most 2 scope entries and only updates the one it recognises `[CITED: design/FR-onvif-stack.md:78]`; names over 32 characters are truncated by the camera; percent-encoding must be UTF-8 and `unquote` symmetrical (`Back%20Yard`).
**How to avoid:** one entry per call, enforce the limit before sending (`kMaxDeviceNameLength = 32`), tests with spaces and non-ASCII; confirm whether the limit is characters or bytes on the camera (A11).

### Pitfall 14: Time-dependent tests that sleep
**What goes wrong:** tests for the 15 s session leeway, the 8 s silence timer, the 60 s verified window, and backoff become slow or flaky.
**How to avoid:** inject `clock` and every duration (defaults equal the Dart values); tests advance a fake clock; only the hardware suite uses real time.

### Pitfall 15: Event-loop affinity
**What goes wrong:** `asyncio.Lock`/`Task` objects cached at module import or reused across `asyncio.run` calls (CLI commands, `CliRunner`) raise "attached to a different loop".
**How to avoid:** all caches live in objects created per command invocation (or per app lifespan in Phase 3); no module-level asyncio primitives.

### Pitfall 16: 421 depends on firmware support
**What goes wrong:** the NVR relies on a 421 to notice a changed address, but older firmware ignores the header (`camera_id_check` false) and answers the wrong camera normally.
**How to avoid:** store `camera_id_check` from capabilities; when false, the reprobe/health path verifies the serial through `GetDeviceInformation` on each reconnect and warns the owner to enable a DHCP reservation. Also handle `503` "Firmware upgrade in progress" (retry after about 45 s) `[CITED: camera-rest-api.md:169-184]`.

### Pitfall 17: Leaving processes and files behind in tests
**What goes wrong:** a failed MediaMTX test leaves the binary listening on port 8554/9997 and breaks the next test or the next CI job.
**How to avoid:** context manager with `finally: terminate(); wait()`, random free ports in tests (the production config uses fixed loopback ports), and a session-scoped check that no `mediamtx` process remains. Use `tmp_path` for every data directory so the real data dir is never touched.

## Code Examples

**Verbatim contract constants used below** (each quoted from the file at the stated line):

| Quote | Where |
|-------|-------|
| `const String cameraIdHeaderName = 'X-VizenLink-Camera-Id';` | `camera_id_mismatch.dart:6` |
| `const int cameraIdMismatchStatus = 421;` | `camera_id_mismatch.dart:9` |
| `const challengePassword = 'are-you-onchip-nuraeye';` | `nuraeye_client.dart:559` |
| `const expectedReplyPlaintext = 'yes-i-am-onchip-nuraeye';` | `nuraeye_client.dart:560` |
| `return _post('/nuraeye/live-stream-uri', {'profile_token': p['profile_token']}, timeout);` | `nuraeye_client.dart:226` |
| `return _client.post('/nuraeye/identity', body)` / `return _client.post('/nuraeye/session/login', body)` | `rest_identity_discovery_client.dart:21, 35` |
| `const String kMainStreamProfileToken = 'Profile_1';` / `kSubStreamProfileToken = 'Profile_2'` / `kMobileOnlyStreamProfileToken = 'Profile_3'` | `live_stream_uri_client.dart:6, 9, 18` |
| `const _kScopeNamePrefix = 'onvif://www.onvif.org/name/';` / `_kScopeLocationPrefix = 'onvif://www.onvif.org/location/';` | `onvif_device_client.dart:13-14` |
| `const kMaxDeviceNameLength = 32;` / `const kMaxDevicePasswordLength = 32;` | `onvif_device_client.dart:19, 25` |
| `static const multicastAddress = '239.255.255.250';` / `static const port = 3702;` / `static const _localName = 'NetworkVideoTransmitter';` | `ws_discovery_client.dart:35, 36, 38` |
| `static const Duration _silentAfter = Duration(seconds: 8);` | `insecure_camera_http_client.dart:74` |
| `static const int _defaultExpiresInSec = 1800;` / `static const Duration _expiryLeeway = Duration(seconds: 15);` | `nuraeye_client.dart:59, 64` |
| `'%Y-%m-%dT%H:%M:%S.000Z'` | `wsse_digest.dart:51` (comment) |

### Example 1: Camera-only TLS context with pre-request pin `[VERIFIED: experiment, httpx 0.28.1, Python 3.13]`

```python
import hashlib, ssl

def camera_ssl_context(pin_sha256_hex: str | None) -> ssl.SSLContext:
    def _check(cert_der: bytes | None) -> None:
        if pin_sha256_hex is not None and (cert_der is None or hashlib.sha256(cert_der).hexdigest() != pin_sha256_hex):
            raise ssl.SSLCertVerificationError("camera certificate fingerprint changed")

    class _Obj(ssl.SSLObject):
        def do_handshake(self):
            super().do_handshake()                       # raises WantRead/WantWrite until done
            _check(self.getpeercert(binary_form=True))   # before any request bytes are written

    class _Sock(ssl.SSLSocket):
        def do_handshake(self, *a, **k):
            super().do_handshake(*a, **k)
            _check(self.getpeercert(binary_form=True))

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE                      # self-signed, shared, expired: pin instead
    ctx.set_ciphers("DEFAULT:@SECLEVEL=0")               # mbedTLS 2.28 on the camera
    ctx.sslobject_class, ctx.sslsocket_class = _Obj, _Sock
    return ctx
# httpx.AsyncClient(verify=ctx) -> match: HTTP 200; mismatch: ConnectError and the server saw no HTTP request.
```

### Example 2: WSSE digest and `created` `[VERIFIED: golden vector reproduced]`

```python
import base64, hashlib, os
from datetime import datetime, timezone

def created_now() -> str:                       # '%Y-%m-%dT%H:%M:%S.000Z'
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

def compute_digest(plaintext: str, *, nonce_b64: str, created: str) -> str:
    raw = base64.b64decode(nonce_b64) + created.encode() + plaintext.encode()
    return base64.b64encode(hashlib.sha1(raw).digest()).decode()

# Known answer: nonce 'AAAAAAAAAAAAAAAAAAAAAA==', created '2026-01-01T00:00:00.000Z', password 'test-password'
assert compute_digest("test-password", nonce_b64="AAAAAAAAAAAAAAAAAAAAAA==",
                      created="2026-01-01T00:00:00.000Z") == "F3ldVt6HHuN3/vvi4vYtwEH8+w8="
nonce_b64 = base64.b64encode(os.urandom(16)).decode()      # fresh per request
```

### Example 3: Header-case assertion at the wire (pattern for HTTP-01/02)

```python
# The simulator reads raw bytes, so names are compared exactly as received.
async def test_camera_id_header_is_sent_verbatim(sim, camera_client):
    await camera_client.get_serial()                        # connection carries serial "VZL-CAM-000001"
    raw = sim.requests[-1].raw_header_names                 # list[bytes], untouched
    assert b"X-VizenLink-Camera-Id" in raw and b"x-vizenlink-camera-id" not in raw
```

### Example 4: UTC type and the Alembic hook `[VERIFIED: experiment, `alembic check` reported no drift]`

```python
class UtcDateTime(TypeDecorator):
    impl = BigInteger; cache_ok = True
    def process_bind_param(self, v, dialect):
        if v is None: return None
        if v.tzinfo is None or v.utcoffset() is None: raise ValueError("naive datetime rejected")
        return (v.astimezone(UTC) - EPOCH) // timedelta(microseconds=1)
    def process_result_value(self, v, dialect):
        return None if v is None else EPOCH + timedelta(microseconds=v)

# migrations/env.py
def render_item(type_, obj, autogen_context):
    return "sa.BigInteger()" if type_ == "type" and isinstance(obj, UtcDateTime) else False
# context.configure(..., render_as_batch=True, render_item=render_item)
```

### Example 5: Seal and open a camera password `[VERIFIED: experiment]`

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
def seal(key: bytes, serial: str, username: str, password: str) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    aad = b"vizenlink-nvr/cred/v1|" + serial.encode() + b"|" + username.encode()
    return nonce, AESGCM(key).encrypt(nonce, password.encode(), aad)
# open(): AESGCM(key).decrypt(nonce, ct, aad) -> InvalidTag if the row was swapped or the key is wrong.
```

### Example 6: Default-deny probes (pattern; each assertion is the exact status)

```python
def rtsp_status(method, url, body=""):
    s = socket.create_connection(("127.0.0.1", 8554), timeout=5)
    s.sendall(f"{method} {url} RTSP/1.0\r\nCSeq: 1\r\n".encode() +
              (f"Content-Type: application/sdp\r\nContent-Length: {len(body)}\r\n".encode() if body else b"") + b"\r\n" + body.encode())
    line = s.recv(4096).split(b"\r\n")[0].decode(); s.close(); return line
assert rtsp_status("ANNOUNCE", "rtsp://127.0.0.1:8554/cam/test", SDP).endswith("401 Unauthorized")
assert httpx.get("http://127.0.0.1:8888/cam/test/index.m3u8", follow_redirects=True).status_code == 401   # 302 first
assert httpx.get("http://127.0.0.1:9997/v3/paths/list").status_code == 401                              # no `any` user
assert httpx.get("http://127.0.0.1:9997/v3/paths/list", auth=("nvr-control", CONTROL_PW)).status_code == 200
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Legacy `POST /nuraeye` JSON-RPC actions (old VMS Python) | Resource REST `/nuraeye/*` with bearer sessions | 2026-08-10 `[CITED: nuraeye_client.dart:12-17]` | Rewrite, do not port `nuraeye_http_client.py` |
| Separate `GetWebRtcUri` / `GET /nuraeye/rtsp-uri` | One `POST /nuraeye/live-stream-uri` | 2026-09-07 `[CITED: API_REFERENCE.md LiveStreamUriClient]` | One discovery call; transport still must be read from the reply |
| Three ONVIF profiles in older design docs | Two ONVIF profiles (`Profile_1/2`); `Profile_3` mobile-only | 2026-09-07 `[CITED: camera-onvif-api.md:467]` | Stream selection excludes `Profile_3` |
| `netifaces` | `ifaddr` | D-18 | No compiler needed on Windows/ARM |
| `datetime.utcnow()` | `datetime.now(UTC)` | deprecated in Python 3.12 | Ruff `DTZ` rules |
| Default MediaMTX `any` user | Explicit `authInternalUsers`, loopback binds | v1.21.3 ships `moq: true` and open defaults `[VERIFIED: shipped mediamtx.yml]` | Config generated from code and validated |
| `requests` + `verify=False` | One httpx client, pinned TLS context | this phase | Async, testable, no global TLS weakening |

**Deprecated/outdated:** `API_REFERENCE.md` default numbers for `scanUnicast` (15 s / 5 s); Dart comment "6 sessions"; STACK.md "H.264 only (H.265 disabled)" and "three streams: /high /medium /low with ONVIF profiles 1 and 2" (partly right, see F5); the roadmap's "3 concurrent RTSPS clients".

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `icacls <path> /inheritance:r /grant:r "<user>:F"` leaves only the current user able to read `data.key` on Windows | Pattern 8 | Key file readable by other local users; mitigated by a Windows CI test |
| A2 | asyncio UDP sockets on Windows survive `ConnectionResetError` from probes to closed ports | Pitfall 8 | Unicast sweep aborts early on Windows; CI test planned |
| A3 | macOS asks for Local Network permission on first LAN access from a terminal-launched Python | Pitfall 8, HW-01 | Scan appears to find nothing until permission is granted |
| A4 | A locked Linux Secret Service can block `keyring` calls | Pattern 8 | Boot hang; mitigated by thread + timeout |
| A5 | OS keystores are scoped per user/session, so service and CLI may not share a key | F10, Pitfall 6 | Decrypt failures after packaging; mitigated by canary and `file` backend |
| A6 | `GetScopes` and `GetDeviceInformation` answer with blank credentials on a configured camera, and `GetDeviceInformation` in the first-password gate | D-01 flow | Names fall back to Model (the Dart fallback already handles it) |
| A7 | A `User`-role account can open RTSPS `DESCRIBE`/`PLAY` | Research flags, HW-08 | Only matters if a dedicated streaming account is adopted later (deferred) |
| A8 | MediaMTX has no Windows arm64 asset; the amd64 build runs under emulation | Pattern 10 | Windows-on-ARM unsupported until verified (FND-06 is Phase 8) |
| A9 | The `sslobject_class` pin also works under httpx2 2.16.0 | Alternatives | Switch deferred until re-tested |
| A10 | `tzlocal.get_localzone_name()` returns a valid IANA name on Windows and in containers | Pattern 9 | Default zone falls back to `UTC`; user sets it in Phase 3 wizard |
| A11 | The 32 limit on camera name/location counts characters, not UTF-8 bytes | Pitfall 13 | Non-ASCII names truncated by the camera |
| A12 | The user's camera firmware matches the published docs (two ONVIF profiles, H.265 default, `/high` `/medium`) | F5 | Stream rows differ; HW-10/11 detect it |
| A13 | Exit codes 10-17 and the message wording for non-mobile outcomes | Pattern 4 | Cosmetic; tests pin whatever is chosen |
| A14 | Restricting manual add to private/link-local addresses by default is acceptable | Pitfall 10 | A user with an unusual routed subnet needs `--allow-public` |
| A15 | Using the datagram source address (not `XAddrs` host) for discovered candidates never breaks a real camera (single-homed) | Pitfall 10 | A multi-homed camera could be reached at the other address; the identity probe still validates |

## Open Questions

1. **ONVIF `GetStreamUri` fallback when `live-stream-uri` returns `webrtc`.**
   - What we know: current firmware always returns `rtsp` (F5); `camera_api` has no `GetStreamUri` client; the published ONVIF doc defines it (`camera-onvif-api.md` section 1.2 and Media2).
   - What's unclear: whether the owner accepts adding an operation that `camera_api` does not cover (project rule: stop and ask).
   - Recommendation: implement it as a small, simulator-covered fallback behind `transport != "rtsp"`, labelled "ONVIF standard operation", and ask for confirmation at plan approval. Without approval the add fails with `STREAMS_UNAVAILABLE` on a WebRTC-enabled dev build.
2. **Copy the four mobile-app files into `contracts/mobile_app/` or track hashes only?** Recommendation: copy (reference-only), because D-01..D-07 and D-12 are defined there.
3. **Key custody for services.** Confirm that Phase 8 may default services to the key file, and whether the CLI must work when run by a different OS user than the service (then both need read access to the same key file).
4. **Pin semantics wording.** Given F3, confirm that recording and enforcing a fingerprint, described only as "certificate unchanged", is wanted now, or defer pinning until the firmware issues per-camera certificates (SR-11).
5. **Scan retries (D-01 vs `camera_scan.dart`).** The mobile scan uses a single 3 s identity attempt per candidate; D-01 says "retries on first contact". Recommendation: single attempt for sweep results, plus one retry for candidates that answered WS-Discovery but failed the identity probe. Confirm.
6. **Unicast sweep range.** Dart assumes /24. Recommendation: `max(real_prefix, 24)` (never wider than /24). Confirm.
7. **Sub stream codec for Phase 3.** The sub stream (`Profile_2`, 720p) is H.265 by default (F5); browsers often cannot play H.265. Needs a Phase 3 decision (reconfigure the camera encoder to H.264 through Phase 6 settings, transcode, or Safari-only H.265). Phase 1 only records the codec.
8. **Reset test consent.** Confirm that a Soft reset (erases name, location, extra accounts; keeps Wi-Fi) is acceptable on the user's only camera, and who restores name/location afterwards.
9. **Python 3.11 CI leg.** STACK.md sets 3.11 as the support floor; adding one Linux leg is cheap. Confirm.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | project, CI | Yes (dev host) | 0.10.9 (latest is 0.13.5) | `uv self update` or CI `setup-uv` pins a version |
| CPython 3.13 | runtime | Yes (uv resolved Homebrew 3.13.16; system 3.14.0 also present) | 3.13.16 | uv downloads it |
| Git, `gh` | repo, release lookups | Yes | - | - |
| Dart SDK | optional conformance traces | Yes | 3.13.3 (camera_api needs ^3.12.2) | skip the optional step |
| MediaMTX v1.21.3 binary | FND-04 proof | Downloadable; darwin arm64 ran on this host | v1.21.3 | none (checksum-pinned download in CI) |
| ffmpeg | not needed in Phase 1 | Yes (Homebrew) | - | - |
| Docker | not needed | No | - | - |
| Node | not needed in Phase 1 | Yes | - | - |
| Windows host | verify Windows-only assumptions | No (CI runner only) | - | `windows-latest` CI job |
| Linux host | verify Linux-only assumptions | No (CI runner only) | - | `ubuntu-latest` CI job |
| Real camera | hardware suite | Yes (one, factory-resettable, per D-20) | firmware unknown | simulator for everything else |

**Missing dependencies with no fallback:** none for planning. **With fallback:** Windows/Linux behaviours are verified only by CI.

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.1 (`asyncio_mode = "auto"`) + pytest-timeout 2.4.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (none yet: Wave 0) |
| Quick run command | `uv run pytest -x -q` (default markers exclude `hardware` and `mediamtx`; target under 30 s using the in-process simulator and injected clocks) |
| Full suite command | `uv run pytest && uv run pytest -m mediamtx` (the second needs `uv run python tools/fetch_mediamtx.py` once) |
| Hardware suite | `NVR_HW_HOST=... NVR_HW_PASSWORD=... uv run pytest -m hardware` (add `NVR_HW_ALLOW_WRITE=1` / `NVR_HW_ALLOW_RESET=1` for the destructive tests) |
| Drift check | `uv run python tools/drift_check.py --upstream /Users/gokul/Desktop/vizenlinkvms/nuraeye-rt --mobile /Users/gokul/mobilecctvapp` (local only) and `--self` (CI) |

### Success Criteria -> How each is verified

| # | Success criterion | Automated verification | Manual / hardware |
|---|-------------------|------------------------|-------------------|
| 1 | Scan lists model, name, IP; manual add works | `tests/integration/test_scan.py` (simulator UDP responder + TLS camera: asserts rows, name fallback to model then `Camera at <host>`, and that **no request in `sim.requests` carries credentials**); `test_cli_scan_json.py` (stdout is valid JSON) | HW-01, HW-02 |
| 2 | Failure reasons; default password blocks add; no half-added camera | `test_add_error_taxonomy.py` (parametrized faults: refused/timeout -> UNREACHABLE, 401 -> WRONG_CREDENTIALS, wrong digest/404 -> UNSUPPORTED, 429 -> BLOCKED, 428 -> NEEDS_NEW_PASSWORD); `test_factory_flow.py` (exactly one factory login, rules 8-32 and not `password` in any case, no row until the change succeeded); `test_atomic_add.py` (fault at each step plus DB exception -> zero rows in all four tables; retry succeeds) | HW-03, HW-04 |
| 3 | Registered by serial with name, location, capabilities, main/sub; re-IP does not duplicate | `test_registry.py`, `test_stream_selection.py` (1, 2, 3 profiles, equal resolution, codec, missing VideoEncoder, Profile_3 never chosen), `test_reprobe.py`, `test_reip.py` (421 and unreachable triggers, one match updates host, two matches change nothing, none -> backoff, blank credentials only, add of a known serial at a new host updates instead of duplicating) | HW-05, HW-11, HW-12 |
| 4 | MediaMTX default-deny | `tests/unit/test_mediamtx_config.py` (generated dict has no `any` user, loopback binds, `rtmp/srt/moq` false, `recordDeleteAfter: 0s`, every CORS list empty; `--validate-conf` exits 0 for the pinned binary); `tests/mediamtx/test_default_deny.py` (real binary, exact-status probes of Example 6, startup-log listener assertions, refused ports, API creds 200, plus negative control) | `nvr mediamtx check --probe` on the target box |
| 5 | Contract tests and golden fixtures on Linux, macOS, Windows; UTC and DST | `tests/contract/` (all behaviour ids in the catalogue; meta-tests: every id has a test, mirror headers match the lock, vendored files match the lock hashes, OpenAPI field parity); `tests/integration/test_time_model.py` (round trip, naive rejected, both DST transitions in `America/New_York`, `Europe/London`, `Australia/Lord_Howe`, day lengths 23/24/25 h, `nvr cameras show` renders the site zone) | CI matrix on three OS |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| FND-03 | UTC storage, site-zone rendering across DST | unit/integration | `uv run pytest tests/integration/test_time_model.py -x` | No (Wave 0) |
| FND-04 | Default-deny config and live proof | unit + mediamtx | `uv run pytest tests/unit/test_mediamtx_config.py && uv run pytest -m mediamtx` | No |
| FND-05 | Mirror, fixtures, lock, header case, SOAP faults, 421 | contract | `uv run pytest tests/contract -x` | No |
| CAM-01 | Scan lists cameras | integration | `uv run pytest tests/integration/test_scan.py` | No |
| CAM-02 | Manual add by host | integration | `uv run pytest tests/integration/test_add_manual.py` | No |
| CAM-03 | Three failure reasons (+blocked) | integration | `uv run pytest tests/integration/test_add_error_taxonomy.py` | No |
| CAM-04 | Forced password change | integration | `uv run pytest tests/integration/test_factory_flow.py` | No |
| CAM-05 | Capabilities probed, cached, re-probed | integration | `uv run pytest tests/integration/test_capabilities_probe.py tests/integration/test_reprobe.py` | No |
| CAM-06 | Atomic add | integration | `uv run pytest tests/integration/test_atomic_add.py` | No |
| CAM-07 | Main/sub selection | unit + integration | `uv run pytest tests/unit/test_stream_selection.py tests/integration/test_streams_persisted.py` | No |
| CAM-08 | Name, location, group | integration | `uv run pytest tests/integration/test_rename.py` (asserts the camera received only name/location, never the group) | No |
| CAM-10 | Serial identity, re-IP | integration | `uv run pytest tests/integration/test_reip.py` | No |

Cross-cutting tests that guard locked decisions: `test_no_secrets_leak.py` (a sentinel password never appears in stdout, stderr, logs, exception text, `--json`, or the raw SQLite file bytes); `test_credentials_at_rest.py` (AES-GCM round trip, AAD binding, key file mode 0600 on POSIX, Windows ACL test, `keyring` mocked, canary mismatch); `test_architecture_rules.py` (AST check: `camera/` imports nothing from `db`, `services`, `cli`; `cli/` imports no `camera` module directly).

### Sampling Rate
- **Per task commit:** `uv run pytest -x -q` (quick suite).
- **Per wave merge:** full default suite on the three-OS matrix plus `-m mediamtx`.
- **Phase gate:** everything green in CI, drift check clean, `alembic check` clean, and the hardware report attached (HW-01..HW-14, with HW-04 run once under `NVR_HW_ALLOW_RESET=1`) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `pyproject.toml`, `uv.lock`, `.python-version`, `.github/workflows/ci.yml`, `.gitignore` (data dirs, `tests/hardware/reports/`)
- [ ] `tests/conftest.py`: simulator fixture (TLS camera + UDP responder), fake clock, `tmp_path` data dir, `NVR_SECRETS_BACKEND=file`, session-wide "no mediamtx left running" check
- [ ] `sim/fake_camera/` with the behaviours in Pattern 12
- [ ] `contracts/camera_api/` copies, `camera_api.lock.json`, `behaviors.yaml`, `fixtures/`, `tools/vendor_contracts.py`, `tools/drift_check.py`
- [ ] `src/vizenlink_nvr/db/migrations/` (env.py with `render_item`, `0001_initial`)
- [ ] `tools/fetch_mediamtx.py` + `media/pins.json`
- [ ] Framework install: `uv sync` (nothing exists yet)

## Security Domain

`security_enforcement` is enabled (ASVS level 1, block on high).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Partly | Phase 1 has no NVR user accounts (CLI is the local trust boundary: OS file permissions). Camera credentials: digest-only on the wire, never retried after 401, lockout-aware (D-03, D-09). |
| V3 Session Management | Partly | Camera bearer sessions cached in memory only, never persisted or logged; cleared on credential change. |
| V4 Access Control | Yes | Data dir 0700, DB 0600, key file 0600 (POSIX) / owner-only ACL (Windows); MediaMTX API user limited to loopback; role failures (`Forbidden`) never trigger re-login. |
| V5 Input Validation | Yes | Host/port validation, discovery datagram bounds, `defusedxml`, XML escaping of every interpolated value, percent-encoding of scope values, IANA zone validation, password length/rules. |
| V6 Cryptography | Yes | `cryptography` AES-256-GCM with random nonce and AAD; random data key; no custom crypto; SHA-1 digest only because the camera protocol requires it. |
| V7 Error Handling and Logging | Yes | Redacting log filter; `SecretStr`; no stack traces with credentials; `Authorization` and tokens never logged. |
| V8 Data Protection | Yes | Passwords never printed, never in `--json`, never in process arguments (D-16), never returned by any service API. |
| V9 Communications | Yes | Camera TLS: self-signed shared certificate (SR-11), pinned for change detection only; weak-cipher context limited to camera connections. |
| V10 Malicious Code / supply chain | Yes | `uv.lock`, pinned MediaMTX sha256, safe archive extraction, one dependency review checkpoint. |
| V14 Configuration | Yes | Default-deny MediaMTX generated from code, loopback binds, strict validation on every start. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Rogue device answers WS-Discovery with a hostile `XAddrs` (SSRF-style) | Spoofing / Tampering | Use datagram source address; ignore `XAddrs` host; private-range check; identity probe before any credential use |
| Stored password sent to a different device after a DHCP change | Information disclosure | Serial header on every request (421), blank credentials during healing, no auth retries |
| Camera lockout by repeated bad passwords (self-inflicted DoS) | Denial of service | One factory probe; `auth_failed` state; honour `retry_after` |
| XXE / entity expansion in SOAP or ProbeMatch | Tampering / DoS | `defusedxml`, size caps |
| Injection through SOAP values (username, scope, password) | Tampering | Escape `& < > "` and percent-encode scopes (Dart omits escaping the WSSE username; Python escapes it) |
| Password disclosure via logs, `ps`, history, JSON, DB file | Information disclosure | Prompt-only input, redaction, ciphertext-only DB, leak test over all outputs and the DB bytes |
| Weak/shared camera certificate enables LAN MITM (SR-11) | Spoofing / Tampering | Accept as camera limitation; document; pin to detect change; keep tokens short-lived; track SR-11 |
| Key file or DB readable by other local users | Information disclosure | Mode checks at start, refuse to run on loose permissions |
| MediaMTX left anonymous or LAN-exposed | Elevation / Information disclosure | Generated default-deny config, loopback binds, per-OS CI proof with negative control |
| Tampered MediaMTX download | Tampering | sha256 from the pinned table, extract with `filter="data"` |
| Path traversal / command injection in helpers (`icacls`, `mediamtx`) | Tampering | `subprocess.run([...], shell=False)`, no string-built commands |

## Sources

### Primary (HIGH confidence)
- Dart reference, read in full this session: `camera_result.dart`, `camera_connection.dart`, `lan/camera_id_mismatch.dart`, `lan/wsse_digest.dart`, `lan/insecure_camera_http_client.dart`, `lan/nuraeye/{nuraeye_client,nuraeye_rest_client,rest_identity_discovery_client,rest_result,capabilities_client,live_stream_uri_client}.dart`, `lan/onvif/{onvif_device_client,soap_fault}.dart`, `lan/onvif/onvif_video_encoder_client.dart` (profiles part), `lan/discovery/ws_discovery_client.dart`, and the tests listed in the inventory (`/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/`).
- Mobile app flows: `/Users/gokul/mobilecctvapp/lib/app_state/{camera_onboarding,camera_scan,camera_address_recovery}.dart`, `lib/utils/camera_account_rules.dart`.
- Firmware source: `nuraeye-rt/onvif/core/user_table.c`, `utils/digest_utils.c`, `nuraeye/nuraeye_session.h`, `ameba-rtos-pro2/project/nuraeye/src/module_rtsps.h`.
- Published camera documentation (2026-10-21): `nuraeye-rt/docs/external-api/{camera-rest-api.md,camera-onvif-api.md,quick-start.md,README.md}`.
- MediaMTX v1.21.3 release assets, `checksums.sha256`, shipped `mediamtx.yml`, and the binary itself (run on macOS arm64): github.com/bluenviron/mediamtx/releases/tag/v1.21.3.
- Experiments run in a scratch venv on this host (Python 3.13.16, OpenSSL 3.5.9): httpx 0.28.1 and httpx2 2.16.0 header case; certificate pin via `sslobject_class`; `SECLEVEL=0`; AES-GCM AAD; keyring fail backend; SQLAlchemy 2.1.6 + aiosqlite 0.22.1 atomicity and UTC type; Alembic `render_item`; Typer prompts under `CliRunner`; zoneinfo DST lengths; MediaMTX default-deny probes and negative control.
- PyPI JSON API (versions, `requires_python`, first-release dates); GitHub API for action releases; actions/runner-images README for runner labels.

### Secondary (MEDIUM confidence)
- `nuraeye-rt/design/{FR-camera-firmware.md,FR-onvif-stack.md,Camera-ONVIF-API.md,Camera-WAN-MQTT-API.md,Camera-REST-API.openapi.yaml}`, `kb/wiki/known-security-risks.md` (SR-11), `testing_utilities/{onvif_client.py,nuraeye_rest_client.py,camera_id_check_test.py,rtsps_third_client_reject_test.py,set_camera_admin_password.py}` (firmware-side Python references; some design docs lag the published docs).
- Old VMS: `nuraeye-rt/vms/python/*.py`, `vms/mediamtx/mediamtx.yml`.
- Project research: `.planning/research/{STACK,ARCHITECTURE,PITFALLS,SUMMARY}.md`.

### Tertiary (LOW confidence, flagged `[ASSUMED]` above)
- Windows and macOS runtime behaviours not observable from this host (A1-A4, A8, A10).
- Whether the user's camera firmware matches the published documents (A12).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. Versions read from PyPI today; header case, pinning, AES-GCM, DB and Alembic behaviours were executed.
- Architecture and wire behaviour: HIGH. Taken from Dart source and tests read in full, firmware source and current docs; conflicts between sources are listed with a precedence rule.
- MediaMTX baseline: HIGH on macOS arm64 (binary run, strict validation, probes with negative control); MEDIUM for Windows/Linux until CI runs.
- Camera facts needing hardware (profile count, codec, concurrency, skew): MEDIUM; smoke test HW-07, HW-09 to HW-11 settle them.
- Pitfalls: HIGH for items reproduced here, MEDIUM for `[ASSUMED]` ones.

**Research date:** 2026-10-26
**Valid until:** 2026-11-09 for MediaMTX facts (fast release cadence; re-run `--validate-conf` and the probes on any version bump) and library versions; 2026-11-25 for camera protocol facts unless `nuraeye-rt` changes (the drift check reports it).

