# Architecture Research

**Domain:** LAN network video recorder (NVR/VMS) for VizenLink/NuraEye IP cameras. Python + MediaMTX backend, React/TypeScript web UI, versioned REST API shared with a Flutter mobile app.
**Researched:** 2026-10-26
**Confidence:** MEDIUM-HIGH. MediaMTX facts are from the official docs, OpenAPI and config reference fetched today (HIGH). Camera facts are from the camera design docs in `nuraeye-rt/design` and `docs/external-api` (HIGH as written, but several items are marked "build-verified, not hardware-verified"). General NVR structure comes from Frigate and Moonfire NVR docs plus domain knowledge (MEDIUM). Items that need a spike are listed in "Open Questions and Spikes".

---

## 0. Read This First: Findings That Change the Brief

These came out of reading the camera contracts, the old VMS and the current MediaMTX. Each one changes a design decision below.

| # | Finding | Consequence |
|---|---------|-------------|
| 1 | **No documented NuraEye LAN alerts push/pull API exists.** The camera REST OpenAPI (`design/Camera-REST-API.openapi.yaml`) has alert-rule and event-preference *configuration* (`/nuraeye/alert-rules`, `/nuraeye/events/preferences`, `/nuraeye/events/response-actions`). It has no event feed. Alerts reach clients by **AWS IoT MQTT** (`vizenlink/alerts/<thing>`, WAN only) and **ONVIF PullPoint** (LAN). The mobile app deliberately removed its LAN PullPoint hub, so no Dart code shows a LAN event consumer. `PrivacyModeChanged` is documented as WAN-MQTT only. | The brief's "NuraEye alerts primary, ONVIF fallback" is inverted for a LAN-only NVR. **ONVIF PullPoint is the only documented LAN event path.** Build an `EventSource` interface, ship PullPoint as the v1 adapter, and leave a slot for a NuraEye LAN feed if firmware adds one. Confirm with the firmware owner before the events phase. State changes that exist only on MQTT (privacy mode) must be **polled** over REST. |
| 2 | **The camera limits concurrent RTSPS live-view clients per stream.** `RTSPS_LIVEVIEW_MAX_CLIENTS` is verified with 2 clients and a rejected 3rd (FR-CF-153, Partial). ONVIF replay is single-client by design. The REST bearer session table holds 6 sessions with LRU eviction. | The NVR must hold **exactly one upstream RTSPS connection per camera stream** (one on main, optionally one on sub) and fan out through MediaMTX. This is the core reason an NVR exists. It also leaves a slot for the phone's direct-to-camera path. Never open per-viewer camera connections. |
| 3 | **MediaMTX has moved on from the bundled `mediamtx.yml`.** Latest fetched release is v1.21.3. It has a playback server (`:9996`, `/list`, `/get?format=mp4`), `fmp4` as the default record format, a `/v3/recordings/*` API, JWT and HTTP auth, and a default `recordPath` that includes `%z`. The old VMS ran with `playback: false`, `authMethod: internal` and an `any`-user that can publish, read and playback. | Re-derive the MediaMTX config from the current reference. Use the playback server for playback and clip export instead of the old FFmpeg remux webhook. Lock down auth (see 4.4 and 4.9). Pin the version. |
| 4 | **The old VMS keys cameras by IP** (`camera_id = ip.replace('.', '_')`). The registry lives in a frontend-owned JSON blob (`save_user_data`). `camera_api` says identity is `macAddress ?? host`, "never key on host", and the camera answers HTTP 421 on a serial mismatch. | Registry primary key is the **camera serial** (`thingName`, `VZL-CAM-nnnnnn`). Build a re-IP healer. The server owns all registry state. |
| 5 | **Old code lessons that must not be ported.** `os.uname()` is called first, so it crashes on Windows. A per-camera `segments.json` is read-modified-written non-atomically on every segment. A synchronous FFmpeg remux runs inside the Flask webhook. `atexit` deletes every MediaMTX path, which stops recording on exit. `shell=True` runs an openssl pipeline. Flask runs with `debug=True`. Recordings are served as unauthenticated static files. | See Anti-Patterns. Core Value ("never miss footage") fails on every one of these. |
| 6 | **Storage arithmetic dominates the design.** 16 cameras at 4 Mbps main stream is about 690 GB/day (4 Mbps x 86,400 s / 8 = 43 GB per camera per day). 30 days is about 20 TB. | Retention, per-camera quotas, record-profile choice and disk-full handling are first-class components, not afterthoughts. See Scaling. |

---

## Standard Architecture

### How NVRs Are Typically Structured

Open-source NVRs (Frigate, Moonfire NVR, ZoneMinder, Shinobi) converge on the same shape:

1. **Ingest plane.** One long-lived pull per camera stream from the camera's RTSP. Frigate uses go2rtc plus FFmpeg. Moonfire uses its own RTSP client. Here MediaMTX does this job.
2. **Recorder.** Segments are written to disk without re-encoding (stream copy). Frigate cuts 10-second chunks and moves them from a cache to disk only if they match a retention rule. Moonfire writes a "sample file directory" of frames.
3. **Metadata index.** SQLite (Frigate, Moonfire) or MySQL (ZoneMinder, Shinobi) holds one row per segment and one per event. Usage is computed from the index, not by scanning disk (Frigate). The index is reconciled against the filesystem after a crash (Moonfire `check`, garbage collection).
4. **Retention and space manager.** Time-based retention per class, plus a pressure rule that deletes oldest-first when free space is low. Frigate deletes oldest when under roughly one hour of headroom, regardless of policy.
5. **Event pipeline.** Events are stored as rows. Segments overlapping an event are kept longer, and many events can reference the same segments (Frigate).
6. **Control-plane API and UI.** A REST API plus push (WebSocket, SSE or MQTT) for live status. The UI talks only to this API and to the media server.
7. **Supervisor.** A parent that restarts the media server and workers.

The central design rule: **the data plane (video bytes) never flows through the application server.** Python orchestrates and authorizes. MediaMTX moves the bytes, directly between camera, disk and browser or phone.

### System Overview

```
                      CLIENTS (LAN)
  ┌──────────────────────┐        ┌──────────────────────────┐
  │ React web UI (Vite)  │        │ Flutter mobile app       │
  │ served by NVR core   │        │ (mDNS discovery + REST)  │
  └───────┬──────┬───────┘        └───────┬──────┬───────────┘
          │REST  │media (token)           │REST  │media (token)
          │+SSE  │                        │+SSE  │
┌─────────▼──────┼────────────────────────▼──────┼───────────────────────────┐
│ NVR CORE (Python, asyncio, one process)        │                           │
│ ┌────────────────────────────────────────────┐ │                           │
│ │ API layer  /api/v1  (FastAPI-style)        │ │   MediaMTX ports exposed  │
│ │  auth+roles · media-token issuer · SSE hub │ │   to clients only with a  │
│ └──┬───────┬──────────┬──────────┬───────────┘ │   scoped token            │
│    │       │          │          │             │                           │
│ ┌──▼────┐ ┌▼────────┐ ┌▼───────┐ ┌▼─────────┐  │                           │
│ │Camera │ │Recording│ │Events  │ │Health    │  │                           │
│ │Registry│ │Catalog  │ │Ingest +│ │Monitor   │  │                           │
│ │+Camera │ │+Indexer │ │Linker  │ │          │  │                           │
│ │Layer   │ │+Retention││        │ │          │  │                           │
│ └─┬──┬───┘ └─┬───┬───┘ └─┬──────┘ └─┬────────┘  │                           │
│   │  │       │   │       │          │           │                           │
│ ┌─▼──▼───────▼┐ ┌▼───────▼──────────▼──────┐    │                           │
│ │MediaMTX     │ │ SQLite (WAL)              │    │                           │
│ │Reconciler   │ │ cameras·segments·events·  │    │                           │
│ │+ client     │ │ users·sessions·audit·...  │    │                           │
│ └─────┬───────┘ └───────────────────────────┘    │                           │
└───────┼──────────────────────────────────────────┘                           │
        │ control API 127.0.0.1:9997 (+ hooks back to core)                    │
┌───────▼──────────────────────────────────────────────────────────────────────┤
│ MEDIAMTX (pinned binary, child of supervisor)                                │
│  RTSPS pull ─► path cam/<serial>/main ─► record fMP4 ─► recordings dir       │
│            └─► path cam/<serial>/sub  ─► WebRTC (WHEP) / LL-HLS fan-out      │
│  playback server :9996  (/list, /get?format=mp4)                             │
└───────┬──────────────────────────────────────────────────────────────────────┘
        │ RTSPS (self-signed TLS, digest auth) 554/555/556
┌───────▼───────────────┐   ONVIF/REST over HTTPS      ┌───────────────────────┐
│ VizenLink / NuraEye   │◄──── Camera Layer (Python)───┤ NVR core              │
│ cameras (x ~16)       │   PullPoint events, settings,│ (control + events)    │
└───────────────────────┘   health, snapshots          └───────────────────────┘

SUPERVISOR (tiny launcher, one per host, wrapped by systemd / launchd / Windows service)
  spawns and restarts: [mediamtx] and [nvr-core]; the two restart independently.
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Supervisor** | Start, watch and restart MediaMTX and NVR core independently; clean child shutdown; OS service entry point | Small asyncio launcher; per-OS wrapper (systemd, launchd, WinSW) |
| **Camera Layer** (`camera/`) | The only code that speaks ONVIF/NuraEye to cameras. Mirrors `camera_api` contracts: typed result, capability flags, session cache, camera-ID check, SOAP-fault-first parsing | Pure Python package, no web or DB imports |
| **Camera Registry** | Source of truth for cameras: serial identity, credentials (encrypted), chosen profiles, desired recording mode, last known IP, TLS fingerprint, cached capabilities | SQLite table plus service class |
| **MediaMTX Reconciler** | Compute desired MediaMTX state from the registry and push it. Heal drift continuously | Idempotent diff loop against `GET /v3/config/paths/list` |
| **Recording Catalog + Indexer** | One row per segment (camera, start, end, size, path, state). Fed by MediaMTX hooks, healed by a startup and periodic scan | SQLite + hook endpoint + scanner |
| **Retention / Disk Manager** | Delete by policy and by pressure; honour protection ranges and locks; guard the volume; surface the retention horizon | Periodic task; DB-first deletion state machine |
| **Event Ingest** | One task per camera: ONVIF PullPoint (and optional adapters). Normalize, debounce, store, snapshot, notify | `EventSource` adapters and a normalizer |
| **Event-Recording Linker** | Turn an event into a protection range plus a playback reference | Pure function over catalog and events |
| **Health Monitor** | Camera state machine, recording-gap watchdog, storage and process health | Poll loops plus MediaMTX path stats |
| **Auth** | Local accounts, sessions, roles, optional Cognito identity link, media-token issuing | Argon2id, opaque session tokens, signed media tokens |
| **API layer** | `/api/v1` REST, SSE stream, OpenAPI contract, static web UI | ASGI app (see STACK.md) |
| **Export worker** | Clip export jobs via the MediaMTX playback server | DB-backed job queue |
| **Discovery** | WS-Discovery probe, verify with `/nuraeye/identity`, serial-based re-discovery | UDP multicast plus unicast sweep fallback |

### Component Boundaries (what talks to what)

| Component | Calls | Called by | Must NOT |
|-----------|-------|-----------|----------|
| API layer | Registry, Catalog, Events, Health, Auth, Camera Layer (settings proxy) | Web UI, mobile app | Touch video bytes; open camera sockets directly |
| Camera Layer | Cameras only (HTTPS, RTSP probe, UDP) | Registry (add flow), Events, Health, API settings routes | Import FastAPI, SQLAlchemy or MediaMTX code; throw across its boundary |
| Registry | DB, Camera Layer, Reconciler (notify) | API, Discovery | Talk to MediaMTX itself |
| Reconciler | MediaMTX control API, Registry (read), Volume guard | Registry changes, scheduler tick, MediaMTX-restart detector | Own any durable state; it is derived |
| Indexer | DB, filesystem, MediaMTX recordings API (heal only) | MediaMTX hook endpoint, scheduler | Delete files |
| Retention | DB, filesystem | Scheduler, disk-pressure signal | Decide what an event is; it reads protection ranges only |
| Event Ingest | Camera Layer, DB, in-process bus | Registry (start/stop per camera) | Query video; it produces events only |
| Linker | DB (catalog + events) | Event Ingest, API (`/events/{id}`) | Mutate segments |
| Health | MediaMTX paths API, Camera Layer health calls, Catalog, psutil/disk | Scheduler | Restart processes (Supervisor does) |
| MediaMTX | Cameras (RTSPS), disk, hook callbacks to core, JWKS/auth to core | Clients (media ports), Reconciler | Be the system of record |

### Process Model and Supervision

```
OS service manager (systemd | launchd | Windows service via WinSW)
  └── vizenlink-nvr supervisor            (asyncio, ~300 lines, almost never changes)
        ├── mediamtx   (pinned binary; own restart policy; recording survives a core crash)
        └── nvr-core   (API + workers; restarts independently; reconciler re-attaches)
```

**Decisions:**

- **MediaMTX survives a core crash and the reverse.** The old VMS tied them together. Recording must continue while the API restarts. On core restart the Reconciler diffs MediaMTX's live path list against the DB and fixes it. On MediaMTX restart, the supervisor restarts it and the Reconciler (which watches `GET /v3/info` and path list) re-pushes every path. MediaMTX API-created paths are not persisted across a MediaMTX restart, so the registry in SQLite is the persistent truth.
- **No orphan children.** Windows: assign children to a Job Object with `KILL_ON_JOB_CLOSE`. Linux: `PR_SET_PDEATHSIG` or systemd `KillMode=control-group`. macOS: launchd kills the process group by default. All platforms: pidfile plus stale-process reaping at start as the universal fallback.
- **Platform detection** uses `platform.system()` and `platform.machine()`. Do not use `os.uname()` (absent on Windows). Download a **pinned, checksummed** MediaMTX release asset per OS and arch at build or install time rather than shipping five oddly named binaries.
- **Docker** is an optional Linux-only distribution. WS-Discovery multicast and WebRTC UDP need `network_mode: host`. Docker Desktop on macOS and Windows cannot do this, so native install is the default for those.
- **One core process, asyncio.** At 16 cameras there is no need for Celery, Redis, Kafka or multiprocess workers. Blocking work (SQLite, filesystem walks, FFmpeg) goes to a thread pool or `asyncio.create_subprocess_exec`. Each background service is a supervised task with backoff, so one failing worker does not take the API down.
- **In-process event bus** (small asyncio pub/sub) carries domain events: `SegmentCompleted`, `CameraStateChanged`, `EventReceived`, `StorageStateChanged`. The SSE hub subscribes to the same bus.

---

## Recommended Project Structure

```
vizenlink-nvr/
├── contracts/                          # drift prevention (see "Contract mirroring")
│   ├── camera-rest-api.openapi.yaml    # vendored copy of nuraeye-rt/design/Camera-REST-API.openapi.yaml
│   ├── camera_api.lock.json            # sha256 of every mirrored Dart file / doc section + review date
│   ├── behaviors.yaml                  # testable rules extracted from API_REFERENCE / SETTINGS_API_GUIDE
│   └── fixtures/                       # golden vectors: WSSE digest, SOAP faults, request traces
├── src/vizenlink_nvr/
│   ├── camera/                         # == camera_api mirror. No web/DB imports.
│   │   ├── result.py                   # Success | Failure(kind, reason, http_status) | Timeout
│   │   ├── connection.py               # CameraConnection(serial, host, creds, ports, mac)
│   │   ├── capabilities.py             # CameraCapabilities (field names == GetCapabilities wire names)
│   │   ├── generated/                  # pydantic models generated from the vendored OpenAPI
│   │   ├── nuraeye/                    # session cache, recordings, health, live-stream-uri, snapshot...
│   │   ├── onvif/                      # device, media, events (PullPoint), imaging, soap_fault
│   │   └── discovery/ws_discovery.py
│   ├── media/                          # MediaMTX: process spec, control client, reconciler, volume guard
│   ├── recording/                      # catalog, indexer, hook handler, retention, exports
│   ├── events/                         # sources/ (onvif_pullpoint.py, ...), normalizer, linker, store
│   ├── health/                         # camera state machine, gap watchdog, storage probe
│   ├── auth/                           # users, sessions, roles, cognito link, media tokens
│   ├── api/v1/                         # routers, schemas, deps (require(perm)), sse.py, problem.py
│   ├── db/                             # models, migrations
│   ├── supervisor/                     # launcher, per-OS service installers
│   └── bus.py                          # in-process pub/sub
├── web/                                # React + TS (Vite); client generated from openapi.json
├── sim/fake_camera/                    # simulator implementing the camera OpenAPI + ONVIF subset
├── tools/                              # drift_check.py, gen_clients.sh, dart_conformance/ (optional)
└── tests/                              # unit · contract · integration(sim) · hardware(marked)
```

### Structure Rationale

- **`camera/` is a standalone package.** It is the Python twin of `camera_api`. Keeping it free of web and DB imports means the same contract tests run against it, the simulator, and a real camera. It also lets the rest of the NVR be tested with a fake `camera/` implementation.
- **`media/` is separate from `recording/`.** `media/` knows MediaMTX's config and API. `recording/` knows segments, files and policy. A MediaMTX upgrade should only touch `media/`.
- **`contracts/` is committed, versioned data.** Drift prevention is mechanical, not a convention.
- **`events/sources/` is plugin-shaped** so the PullPoint adapter and a future NuraEye LAN feed implement one interface.

---

## Architectural Patterns

### Pattern 1: Declarative Reconciler for MediaMTX

**What:** The DB (registry plus desired recording state) is the truth. A reconciler computes desired MediaMTX path configs and diffs them against `GET /v3/config/paths/list`, then issues `add`, `patch` or `delete` calls. Run it on registry change, on startup, on MediaMTX-restart detection, and every 30-60 seconds to heal drift.
**When to use:** Always. MediaMTX API-created paths vanish on MediaMTX restart.
**Trade-offs:** Slightly more code than imperative add and remove calls. In return it is crash-safe and removes the old `atexit` cleanup hazard.

```python
def desired_paths(cameras, now, volume_ok) -> dict[str, PathConf]:
    out = {}
    for cam in cameras:
        want_record = volume_ok and recording_enabled(cam, now)   # mode + schedule + privacy
        out[f"cam/{cam.serial}/main"] = PathConf(
            source=cam.rtsps_url(cam.record_profile),          # creds percent-encoded
            sourceFingerprint=cam.tls_fingerprint,
            sourceOnDemand=False,                               # always pulled: this IS the recorder
            record=want_record, recordFormat="fmp4",
            recordPartDuration="1s", recordSegmentDuration="5m",
            recordDeleteAfter="0s",                             # Retention manager owns deletion
        )
        out[f"cam/{cam.serial}/sub"] = PathConf(
            source=cam.rtsps_url(cam.live_profile),
            sourceFingerprint=cam.tls_fingerprint,
            sourceOnDemand=True, record=False,                  # camera slot used only while watched
        )
    return out
```

### Pattern 2: Typed Result Instead of Exceptions (mirror of `CameraResult`)

**What:** Every Camera Layer call returns `Success[T] | Failure | Timeout`, never raises. `Failure` carries a closed `kind` enum (`UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `UNSUPPORTED`, `ID_MISMATCH`, `PASSWORD_CHANGE_REQUIRED`, `CREDENTIALS_MISSING`, `BAD_RESPONSE`, `OTHER`), the human `reason`, and `http_status`.
**When to use:** Every outbound camera call. Consumers use `match`.
**Trade-offs:** Slightly verbose. It makes the API-layer error mapping total and testable, and it matches the Dart package's stated stability contract ("no client ever returns a formatted string, throws an app-level exception, or exposes a raw HTTP/SOAP error").

```python
@dataclass(frozen=True)
class Success(Generic[T]): value: T
@dataclass(frozen=True)
class Failure: kind: FailureKind; reason: str; http_status: int | None = None
@dataclass(frozen=True)
class Timeout: pass
CameraResult = Success[T] | Failure | Timeout

match await recording_mode.get_mode(conn):
    case Success(value): ...
    case Failure(kind=FailureKind.FORBIDDEN): ...   # camera account role too low: do NOT retry, do NOT re-login
    case Failure(reason=r): ...
    case Timeout(): ...
```

**HTTP mapping at the API boundary** (one table, one function):

| CameraResult | NVR API response | Note |
|--------------|------------------|------|
| `Success` | 200/201/204 | |
| `Failure(UNSUPPORTED)` | 409 `camera_capability_missing` | Raised by the capability gate before any network call |
| `Failure(FORBIDDEN)` | **502/409 `camera_forbidden`, never 403** | 403 means the *NVR user* lacks permission. A camera-side role problem is a different thing and the UI must say so |
| `Failure(UNAUTHORIZED)` | 409 `camera_auth_failed` | Triggers camera state `auth_failed`, not an NVR logout |
| `Failure(ID_MISMATCH)` | 409 `camera_identity_mismatch` | Also triggers the re-IP healer |
| `Timeout` | 504 `camera_timeout` | |
| other `Failure` | 502 `camera_error` | |

### Pattern 3: Retention by Protection Ranges (pre-roll and event mode without start/stop races)

**What:** Always record into short segments. An event does not start or stop MediaMTX recording. It inserts a row in `protection_ranges(event_id, camera_id, t0, t1)`. Retention deletes unprotected segments after the camera's buffer window and never deletes a segment overlapping a protection range or a user lock.
**When to use:** Event-triggered recording mode and pre-roll. Also gives "Evidence locked" (`review_status`, event-metadata-schema) for free.
**Trade-offs:** Event-mode cameras write to disk continuously for a short window (buffer minutes) instead of only on events. The old approach (PATCH `record` on and off per event) loses pre-roll, adds start latency, and races segment boundaries. Frigate uses the same idea: segments pass through a retention check, and alerts and detections keep overlapping segments. The camera's own firmware only implemented post-roll (FR-CF-041), so the NVR can beat the camera on pre-roll.

Scheduled mode is different. FR-VMS-097 says footage outside the window is "withheld from NVR storage". The Reconciler therefore toggles `record` at window boundaries (a `PATCH`, no source restart), because writing and then deleting does not satisfy "withheld".

### Pattern 4: Two-Source Segment Indexing (hooks for latency, scan for correctness)

**What:** MediaMTX `runOnRecordSegmentCreate` and `runOnRecordSegmentComplete` call a tiny helper that POSTs to a loopback endpoint with a shared secret. A startup scan and a periodic scan walk the recordings directory and adopt files with no row, mark rows with no file `missing`, and close stale `open` rows. A hook that is lost (core restarting) is therefore never a gap in the catalog.
**When to use:** Always.
**Trade-offs:** Two code paths. Cheap compared with trusting a single webhook.
**Cross-platform note:** Avoid shell variable expansion (`$MTX_SEGMENT_PATH`) in the hook command. Use `"<abs path to python>" -m vizenlink_nvr.hook complete`, and let the helper read `MTX_PATH`, `MTX_SEGMENT_PATH`, `MTX_SEGMENT_DURATION` from its environment. This works regardless of whether MediaMTX runs the command via `sh -c` or `cmd /c`. Verify on all three OSes (spike).

### Pattern 5: Scoped, Short-Lived Media Tokens (data plane auth without proxying)

**What:** The NVR API issues a token bound to `{action, path, exp, user}` (for example `POST /api/v1/cameras/{id}/live` returns a WHEP URL, an HLS URL and a token). MediaMTX is configured to verify it, either `authMethod: jwt` (core serves a JWKS on loopback) or `authMethod: http` (MediaMTX calls the core for each new session). Clients hit MediaMTX ports directly, so no video flows through Python.
**When to use:** Always. The old setup granted `publish`, `read` and `playback` to the anonymous user, which exposes every camera to anyone on the LAN.
**Trade-offs:** Token expiry **closes the session** (v1.21.3 notes: "Sessions close when their JWT expires"). A UI left open on a wall display must renew and re-negotiate **make-before-break** at about 80% of the TTL. Use TTL of 30-60 minutes for live and 5-10 minutes for playback or export URLs.
**Recommendation:** `authMethod: jwt` so live view survives a brief core restart (MediaMTX verifies locally). Fall back to `http` if JWKS-on-loopback proves brittle. The choice is global in MediaMTX (one `authMethod`). Keep `api`, `metrics`, `pprof` loopback-only through `authInternalUsers` or `authJWTExclude`/`authHTTPExclude`. Spike this (see Open Questions).

### Pattern 6: Capability-Gated Everything (mirror of Dart capability flags)

**What:** Fetch `GET /nuraeye/capabilities` at onboarding and on demand, and store it per camera. All settings and recording-mode routes call `require_capability(...)` first and return `Failure(UNSUPPORTED)` before any network call. The web UI and the mobile app build their controls from the capability document returned by `GET /api/v1/cameras/{id}/capabilities`, never from model or firmware sniffing.
**Details to carry over verbatim from `camera_api`:**
- `null` means "unknown", not "unsupported". Tri-state flags (`wanLiveViewCapable`) stay `bool | None`.
- "Firmware too old to report" yields empty list, `0` or `false`, never an error.
- Check before calling: `supportedRecordingModes` before `setMode`; `cardPresent` before `LocalStorage.setEnabled(true)`; clip-duration min/max before `setClipDuration`; deterrence eligibility before `ActivateDeterrence`.
- Capabilities are **always a live call** at the Camera Layer. Caching belongs to the Registry, not the client.

---

## Subsystem Designs

### 4.1 Camera Layer: mirroring `camera_api` without importing Dart

**Contract surface to mirror** (from `API_REFERENCE.md`, `SETTINGS_API_GUIDE.md`, `STREAMING_GUIDE.md`):

| Contract | Python mirror |
|----------|---------------|
| `CameraResult<T>` = Success / Failure(reason) / Timeout, plus `CameraForbidden` as a Failure subtype | `result.py` as above; `FailureKind.FORBIDDEN` |
| `CameraConnection` (host, username, password, httpsPort, rtspPort, thingName, macAddress, wan flags) with `identityKey = macAddress ?? host` | `connection.py`. NVR registry uses **serial first**, then MAC. Never host |
| Camera-ID check: send `X-VizenLink-Camera-Id: <serial>` on every LAN HTTP call; HTTP 421 = a different camera answered; no header sent when serial is unknown | Camera Layer HTTP wrapper; 421 emits `CameraIdMismatch` on the bus and the re-IP healer re-discovers by serial |
| WSSE-style SHA-1 digest login: `Base64(SHA1(nonce + created + password))` | `wsse.py` with golden vectors |
| Bearer session cached per host and account, refreshed on activity, one re-login on 401, **concurrent logins for one host serialized** (camera holds 6 sessions, LRU) | Per-camera `asyncio.Lock` plus session cache. Never one short-lived client per call |
| SOAP `<Fault>` checked **before** HTTP status (camera returns faults on HTTP 200 and on non-200) | `soap_fault.py`; test with both shapes |
| Self-signed TLS accepted deliberately and narrowly; outgoing header case preserved | Dedicated HTTP client factory (confirm the chosen library can preserve header case; the quick-start shows a requests adapter with `SECLEVEL=0` ciphers) |
| HTTP 428 = factory password must be changed first | `FailureKind.PASSWORD_CHANGE_REQUIRED`; onboarding flow handles it |
| Pagination: `getAllRecordings` pages with `start = last.start + 1` while `truncated`, `maxPages = 20` | Port the algorithm; test with sim |
| Role semantics: User < Operator < Administrator; role failure is `FORBIDDEN`, not a credentials problem | Documented in the error table above |
| Profile tokens `Profile_1/2/3` via `POST /nuraeye/live-stream-uri`; **never hardcode the number of streams**, read the profile list | `StreamResolver` returns the profile list and URLs |

**Camera facts the layer must encode** (from camera design docs):
- Three physical streams: `/high` on 554, `/medium` on 555, `/low` on 556 (RTSPS, digest). ONVIF describes only `Profile_1` and `Profile_2`. `Profile_3` exists only through `/nuraeye/live-stream-uri`. Docs disagree on the stream 2 resolution (640x360 in FR-CF-010 vs 720p in the ONVIF doc), so read the live list.
- H.264 only (H.265 is built but disabled). This matters for browser WebRTC.
- Camera accounts: one Administrator plus up to four Operator/User. The NVR can create a dedicated `Operator` account at onboarding for streaming, events and health, and keep the Administrator credential only for admin operations (Wi-Fi, storage, recording mode, accounts). Treat this as a recommended option, not a requirement.
- Camera clock state is exposed by `/nuraeye/health` (`clockSyncState`, `uncertainSince`). Segments are timestamped by the **NVR clock**, never the camera's.

**Drift prevention (the central risk for this layer):**

Ranked by value per cost. Do items 1-4 in the first camera-layer phase; 5-6 later.

1. **Generate wire models from the same OpenAPI the Dart generator uses.** `design/Camera-REST-API.openapi.yaml` is the input to `tools/generate_dart_rest_client.py` (per API_REFERENCE). Vendor a copy into `contracts/` and generate pydantic models from it (`datamodel-code-generator` or equivalent). CI fails if the generated output differs from the committed output. A scheduled check compares the vendored file's sha256 with the upstream path when the mobile repo is available.
2. **A contract lock file for hand-mirrored behaviour.** ONVIF SOAP has no OpenAPI, and much of `camera_api` is behaviour (retry once on 401, SOAP fault first, 421 handling, pagination, capability gating). `contracts/camera_api.lock.json` records the sha256 of each Dart source file and doc section each Python module mirrors, plus the date of last review. Each Python module carries a `# mirrors: camera_api/lib/src/lan/nuraeye/recordings_client.dart` header. `tools/drift_check.py --mobile-repo <path>` reports files whose hash changed since the lock, and the fix is to re-review, update Python and bump the lock. This costs nothing at runtime and catches "someone changed the Dart client".
3. **`behaviors.yaml`: rules as testable assertions.** Each rule has an ID, a source reference (doc section and FR id) and a pytest that exercises it against the simulator. Examples: `soap-fault-before-http-status`, `login-retry-once-on-401`, `login-serialized-per-host`, `recordings-paginate-until-not-truncated`, `set-mode-requires-supported-mode`, `forbidden-is-not-retried`, `421-emits-mismatch`, `unknown-capability-fails-open-for-wan-only`.
4. **Golden fixtures.** WSSE digest vectors (fixed nonce, created and password give a fixed digest), SOAP samples copied from `docs/external-api/camera-onvif-api.md`, and error bodies from the OpenAPI examples.
5. **Simulator (`sim/fake_camera/`).** Implements the camera OpenAPI plus the ONVIF subset the NVR uses (device info, media profiles, events service with PullPoint, recording service). It supports fault injection (421, 401, 403, 428, timeouts, HTTP-200 SOAP faults, truncated recording lists, session LRU eviction at 6, 3rd RTSPS client rejected). Contract tests and integration tests run against it. Marked `hardware` tests run the same scenarios against a real camera.
6. **Cross-implementation request-trace equivalence (optional, high value).** A small Dart script under `tools/dart_conformance/` depends on `camera_api` **by path (read-only, no changes to the package)** and runs a fixed scenario against the simulator through a recording proxy. The captured request traces (method, path, headers, normalized body, with nonce and timestamps masked) become fixtures. The Python client must emit equivalent requests. This verifies the Python client against the actual Dart implementation, not against a reading of the docs. `camera_api` changes require owner confirmation, so this design deliberately needs none.

**What not to do:** do not attempt to share code via FFI, a Dart sidecar service, or transpilation. The contract surface is small enough to mirror and test, and a Dart runtime on a Pi or in a Windows service is an operational cost with no payoff.

### 4.2 Camera Registry and Add Flow

```
Discover (WS-Discovery multicast; unicast /24 sweep only if multicast finds nothing)
   └─► verify: POST /nuraeye/identity challenge (with retry on first contact)
         └─► credentials entered by user (HTTP 428 → force Administrator password change)
               └─► login → GET /nuraeye/capabilities → ONVIF GetDeviceInformation (serial, MAC)
                     └─► POST /nuraeye/live-stream-uri per profile → RTSPS URLs
                           └─► TLS: fetch cert fingerprint with Python ssl (trust on first use, shown to user)
                                 └─► persist row (serial PK) → Reconciler adds paths → recording starts
```

- **Primary key is the camera serial.** Store `last_host`, `mac`, and `host_updated_at`. A re-IP healer subscribes to `CameraIdMismatch` and to repeated connect failures, runs WS-Discovery, matches by serial, updates `last_host`, and triggers the Reconciler. This is the NVR-side equivalent of the app's `CameraAddressRecovery`. Also run a slow periodic re-discovery (for example every 15 minutes while any camera is offline).
- **Credentials** are stored encrypted (AES-GCM or Fernet), with the key in the OS keyring when available, otherwise a `0600` key file under the data directory. They cannot be hashed because they must be replayed. A passphrase-derived key (as `CameraSecureStorage` does for the phone) is wrong for an unattended server that must reboot and record. The old VMS kept them in plaintext JSON in `app_data`. Camera passwords may contain URL-reserved characters; **percent-encode them** in RTSPS URLs given to MediaMTX. Camera passwords are 1-32 characters.
- **TLS fingerprint pinning** uses MediaMTX's `sourceFingerprint`. Fetch it with Python's `ssl` (`getpeercert(binary_form=True)`, sha256) and not `shell=True` openssl. A later fingerprint mismatch (camera factory reset regenerated its cert) must put the camera in state `tls_changed` and require an explicit admin "trust new certificate" action. Silent re-trust defeats the pin.
- **Snapshot-per-camera and profile choice:** `record_profile` (default main/`Profile_1`) and `live_profile` (default sub). Offering `record_profile = medium` is the cheapest disk-saving lever for home users.

### 4.3 MediaMTX Control: paths, recording, playback

**Path naming:** `cam/<serial-lowercase>/main` and `cam/<serial-lowercase>/sub`. Serial-based, collision-free, and stable across IP changes. Auth permissions can target `~^cam/<serial>/` by regex.

**Pinned config skeleton (generated by `media/` at start, not hand-edited):**

```yaml
# values are intent; verify each against the pinned MediaMTX version's mediamtx.yml
api: yes
apiAddress: 127.0.0.1:9997
playback: yes
playbackAddress: :9996          # exposed, token-protected
rtsp: yes
rtspAddress: 127.0.0.1:8554     # internal only (FFmpeg audio path, debugging)
rtmp: no
srt: no
webrtc: yes
webrtcAddress: :8889
hls: yes
hlsAddress: :8888
hlsVariant: lowLatency
authMethod: jwt                 # or http; see Pattern 5
pathDefaults:
  recordFormat: fmp4
  recordPartDuration: 1s
  recordSegmentDuration: 5m
  recordDeleteAfter: 0s         # Python owns deletion
  recordPath: <recordings_dir>/%path/<time token incl. zone or epoch>   # see spike
  runOnRecordSegmentComplete: "<abs python> -m vizenlink_nvr.hook complete"
```

**Recording format decision: fMP4, not MPEG-TS.** The old VMS used MPEG-TS plus a per-segment FFmpeg remux (`-analyzeduration 100M`, `-fflags +genpts`) to fix "blank video" and wrong durations, and deleted sub-10 KB "drift-reset" segments. Current MediaMTX writes fMP4 with 1-second parts, serves it browser-ready from the playback server, and exports a trimmed and concatenated MP4 (`/get?format=mp4`) with no FFmpeg. Tradeoff: on a hard crash the last part (about 1 s) is lost, which MediaMTX documents. That is acceptable; MPEG-TS's flush behavior does not justify per-segment CPU cost on a Pi. **Spike on a real camera:** fMP4 with this camera's H.264 and AAC audio, timestamp behavior (`useAbsoluteTimestamp: false` was needed in the old config because the camera's RTP clock produced "8-minute files"), and tiny-segment artifacts on timestamp jumps.

**Time-in-filename:** v1.21.3 changed segment names to local time zone and made the default path include `%z`. DST makes local-time names ambiguous. Prefer a UTC-unambiguous token (docs list `%s` as Unix epoch) if MediaMTX's playback lookup accepts it. If not, keep the default with `%z` and parse the offset. The catalog stores UTC microseconds either way, so the filename is only an adoption aid for the scanner.

**Playback server usage:**
- `GET :9996/list?path=cam/<serial>/main&start=<RFC3339>&end=<RFC3339>` returns spans with `start`, `duration` and a ready URL. Use it as a cross-check, not as the catalog. The catalog drives the timeline UI (coverage spans plus event markers), because the NVR needs event, protection and retention data MediaMTX does not have.
- `GET :9996/get?path=...&start=...&duration=...&format=fmp4|mp4` streams concatenated footage. `fmp4` is browser-playable; `mp4` is for downloads and for players with limited fMP4 support (Flutter `video_player` on some platforms). Seeking across a long range means a new request with a new `start`. Behavior across **gaps** must be checked (spike). The UI should issue one request per contiguous coverage span from the catalog.
- Clip export = a server-side job that downloads `/get?format=mp4` from loopback to `exports/`, then serves the file with a token. No FFmpeg needed for the core path. Cap duration per request (the old VMS used 1 hour).

**Live paths:** the sub path is `sourceOnDemand: true`, so the camera sees a second connection only while someone watches. Full-screen or single view can switch to the always-on main path with no new camera connection. Audio: browsers' WebRTC does not decode AAC. Live audio over WebRTC therefore needs an on-demand FFmpeg transcode to Opus (the old VMS's `_audio` path did this). Make it **opt-in per viewer** (unmute), not a permanently registered path. LL-HLS carries AAC natively and is the no-transcode audio route.

### 4.4 Live Streaming Fan-Out

```
camera ──RTSPS (1 conn/stream)──► MediaMTX path ──┬─ WebRTC/WHEP  :8889  (sub-second; browsers; flutter_webrtc)
                                                  ├─ LL-HLS       :8888  (Safari/iOS, audio, fallback)
                                                  └─ recorder (main path only)
```

- **Grid (multiview):** WebRTC/WHEP from the `sub` path. 16 simultaneous WebRTC sessions is fine on a LAN; the cost is NVR CPU for DTLS/SRTP and UDP port usage. Offer an HLS fallback tile mode.
- **Single view:** WHEP from `main` (higher quality, no additional camera connection).
- **Mobile "live via NVR":** same token flow. The phone gets WHEP or HLS URLs from the NVR, so it never touches the camera's stream slots.
- **WebRTC networking pitfalls on LAN:** set `webrtcIPsFromInterfaces`/`webrtcAdditionalHosts` correctly for multi-NIC hosts. Open UDP 8189 in host firewalls (Windows Defender prompts). HTTP (not HTTPS) is acceptable on a LAN for WHEP playback since no `getUserMedia` is involved, but mixed-content rules apply if the UI is ever served over HTTPS.
- **Codec:** H.264 only today. If the camera's H.265 is ever enabled, browser WebRTC support is poor, so the sub profile must stay H.264.
- **Freshness (FR-VMS-023):** the stream descriptor from the API includes `state` (`live`, `connecting`, `stalled`, `offline`, `privacy`) so the UI never shows a frozen frame as live.

### 4.5 Recording Index / Segment Catalog

```
segments(
  id INTEGER PK, camera_serial TEXT, path_name TEXT,
  file_path TEXT UNIQUE,              -- relative to recordings root
  start_utc_us INTEGER, end_utc_us INTEGER NULL,   -- NULL while open
  size_bytes INTEGER, format TEXT,
  state TEXT CHECK(state IN ('open','complete','missing','deleting')),
  created_at, indexed_via TEXT        -- 'hook' | 'scan'
)  INDEX(camera_serial, start_utc_us)

protection_ranges(id, event_id NULL, camera_serial, t0_us, t1_us, reason, expires_at NULL)
  INDEX(camera_serial, t0_us, t1_us)

events(...)   -- see 4.7
exports(id, camera_serial, t0, t1, state, file_path, created_by, ...)
```

- **UTC integer microseconds everywhere.** Display timezone is a UI concern. Moonfire's experience (separate wall time from media time, timestamps to diagnose time jumps) argues for storing both `start_utc_us` and the NVR monotonic offset, but the simple version is enough: never trust camera clocks for segment times.
- **SQLite WAL, single writer, batched commits.** 16 cameras at one segment per 5 minutes is about 0.05 writes per second. This is nothing. Do not add a database server.
- **Never expose file paths or segment IDs to clients.** The API is time-addressed (`camera + start + duration`). Retention can then delete freely without breaking client links.
- **Gap detection is a query over this table** (`LAG(end)` per camera), which gives the coverage bar and the "zero recording gaps" success metric directly.
- **State machine for crash safety:** `open → complete` (hook or scan), `complete → deleting → (row deleted)`. A crash between mark and unlink resumes on restart. `missing` rows are kept briefly then pruned, so a vanished external drive does not silently erase the index.
- **Mobile compatibility option:** `GET /api/v1/cameras/{id}/recordings` can mirror `RecordingsList`/`RecordingClip` (`id`, `start`, `end`, `size_bytes`, `active`, `trigger`, epoch seconds, plus `truncated`/`storage_available`) and `.../recordings/dates` can mirror `RecordingDatesList`. The Flutter recordings UI could then treat the NVR as a "camera with a very large SD card". `trigger` is filled from linked events, matching camera semantics. This needs a decision with the mobile owner.

### 4.6 Retention and Disk Manager

**Why not MediaMTX's `recordDeleteAfter`:** it is time-only, per path, and blind to disk pressure, protection ranges, locks and exports. Set it to `0s` and own deletion in Python.

**Policy per camera:** `continuous_days`, `event_days`, `buffer_minutes` (event mode), plus an optional `max_gb` quota. **Global:** high and low watermarks, a hard free-space reserve.

**Algorithm (runs every 60 s and on `StorageStateChanged`):**

1. Mark `deleting` then unlink segments past their class window. Skip any overlapping a `protection_range` (event or lock) or an in-progress export.
2. If free space is below the high watermark, delete oldest-first across cameras in rounds: first over-quota cameras, then fair-share, **mandatory-recording cameras overwrite oldest rather than stop** (FR-VMS-095). Never delete the open segment.
3. Maintain a hard reserve (for example `max(5 GB, 3% of volume)`) so MediaMTX never hits ENOSPC mid-write. Frigate does the equivalent: under about one hour of headroom, delete oldest regardless of policy.
4. If protected data alone exceeds the quota, raise a **critical** health condition (never silent stop).
5. Compute and publish the **retention horizon**: `(used + free - reserve) / ingest_rate`. If the horizon is shorter than the configured days, surface it in the UI (this is the honest answer to "how long do I keep footage").

**Volume guard (classic NVR failure):** if the recordings directory is on an external or USB drive and it unmounts, MediaMTX will happily write into the empty mountpoint folder on the system disk and fill it. Keep a sentinel file (`.vizenlink-volume-id`) in the recordings root. The Reconciler sets `record: false` and raises a critical alert when the sentinel is absent or the volume id differs. This is not optional.

**Orphans:** a sweeper adopts files with no row (from a lost hook), and deletes `.tmp` leftovers and partial files from crashed exports.

### 4.7 Event Ingestion and Event-to-Recording Linking

**Sources (per camera, one supervised task each):**

| Source | Status | Notes |
|--------|--------|-------|
| **ONVIF PullPoint** (v1 primary on LAN) | Documented. `FR-OV-070` Implemented (build-verified 2026-08-07; confirm hardware verification) | `CreatePullPointSubscription` (default 1 h, min 60 s), `PullMessages` with `Timeout` clamped at 10 s and `MessageLimit` clamped at 2, `Renew`, recreate on 404. Topics seen: `tns1:RuleEngine/PersonDetector/Person` and `tns1:VideoSource/ImagingSettings/IrCutFilterChanged`. Camera disables event types by default (`event_type_enabled_mask` all-disabled), so the NVR **must call `SetEventPreferences`** for the types it wants, and the UI must make that visible. A disabled type is suppressed at the source for **every** consumer including the phone (per direct user decision in FR-CF-143) |
| **NuraEye LAN alerts feed** | **Not found in docs** | Reserve an adapter slot. Do not design around it until firmware confirms |
| **Polled state** | Documented REST | `GET /nuraeye/privacy-mode` (privacy-mode change is MQTT-only), `/nuraeye/health` (reboot count, clock sync), `/nuraeye/local-storage`, in the Health loop. Emit them as events of kind `state_change` |
| **MQTT / cloud** | Out of scope (WAN) | |
| **NVR-originated** | Own | Recording gap, camera offline, disk pressure, as events with severity |

**Normalization.** Map every source to the shared event shape in `kb/wiki/event-metadata-schema.md` (draft): `event_id` (UUID assigned at ingest), `site_id`, `camera_id`, `event_type`, `object_class`, `event_start_utc`, `event_end_utc`, `severity`, `review_status` (`New → Viewed → ... → Evidence locked`), `rule_id`, `snapshot_reference`, `retention_class`, `source`, `raw`. Persist `raw_json` so a schema change never loses data. Align with that schema so the phone and NVR do not diverge on `review_status`.

**Debounce and grouping.** The camera historically logged one event per frame (the AI event-logging design is draft). Keep an open-event table keyed by `(camera, type, rule)`. Extend `event_end` on each repeat, close after a quiet gap (default 10 s), and group repeats within a window in the UI (FR-VMS-044), while retaining every raw row as evidence.

**Time.** Store both `camera_utc` (from the ONVIF message `UtcTime`) and `received_utc`. If camera `clockSyncState` is `uncertain`, use `received_utc` and flag the event (FR-VMS-015). Link with a tolerance (±5 s default).

**Snapshot at event time.** Fetch `GET /snapshot` immediately on event (the `medium` profile for thumbnails) and store the JPEG under `snapshots/`. This is cheaper and more accurate than extracting a frame from video later.

**Link algorithm (idempotent, retention-safe):**

```
on EventClosed(e):
    t0 = e.start - pre_roll(camera)         # default 5 s, max 60 s (Frigate-like)
    t1 = e.end   + post_roll(camera)        # default 10 s
    insert protection_range(event_id=e.id, camera, t0, t1)   # durable link
    # no FK to segments. Segments may not exist yet or may be deleted later.
playback_ref(e) = { camera, start = max(e.start - lead_in(3 s), first_available_in_range),
                    available = EXISTS(complete or open segment overlapping [t0,t1]) }
```

- Computed at read time from the catalog, so it self-heals when the segment completes after the event arrives.
- "Footage for any event found in under a minute" becomes: event row → `/playback?camera&start` → the playback server. No scanning.
- **Overlap with camera SD recordings** (FR-VMS-036 dedupe) is out of v1 scope. Keep a seam: the camera layer already mirrors `RecordingsList` and ONVIF Replay; backfill of NVR gaps from camera SD is a differentiator for a later phase. Note ONVIF replay allows one concurrent playback client and evicts on `GetReplayUri`.

### 4.8 Auth and Roles

**Local accounts:** Argon2id password hashing. **Opaque session tokens** stored hashed in SQLite (short access token plus rotating refresh token for the phone). A single-server LAN product gains nothing from stateless JWT sessions, and opaque tokens give instant revocation. The web UI keeps the access token in memory and the refresh token in an `HttpOnly; SameSite=Strict` cookie. The phone uses bearer tokens in secure storage. Login rate limiting with exponential backoff and lockout notification.

**Roles → permissions (server-side enforced; roles map to a permission set):**

| Permission | Owner/Admin | Operator | Viewer |
|------------|:-----------:|:--------:|:------:|
| View live, timeline, events | yes | yes | yes |
| Export clips, review/lock events | yes | yes | no |
| Camera settings (imaging, OSD, privacy masks) | yes | yes | no |
| Add/remove cameras, recording mode, retention | yes | no | no |
| Users, Cognito link, system config, firmware | yes | no | no |
| Deterrence / two-way talk | yes | yes (with confirmation + audit) | no |

Implement as `Depends(require("recordings.export"))`-style dependencies. The role table is data, so the later `FR-access-control.md` model (per-action permissions, home vs organization) can replace it without touching routes. Leave a nullable `user_camera_access` table for per-camera scoping (a guard sees only the gate camera).

**Two role layers:** NVR role (what the signed-in person may do) and **camera account role** (what the stored camera credential may do). A camera `403`/`CameraForbidden` is surfaced as a camera configuration problem, not as the NVR user lacking rights. The camera enforces `Administrator` for Wi-Fi, storage, recording mode and accounts.

**Optional Cognito link (never required):**

- The NVR's authorization is **always local**. Cognito only proves identity and maps to a local user via `cognito_sub`.
- Pair flow: user signs in locally on the NVR (or phone) once, then calls `POST /auth/cognito/link {id_token}`. The NVR verifies the token against the pool's JWKS (`https://cognito-idp.<region>.amazonaws.com/<poolId>/.well-known/jwks.json`), checks `iss`, `aud`/`client_id`, `exp`, `token_use`, and stores `cognito_sub`.
- Later sign-in: `POST /auth/cognito/exchange {id_token}` → local session if `sub` is linked. JWKS is cached on disk, so verification works offline after the first fetch. If the cache is cold and the NVR is offline, local password still works.
- No Cognito SDK on the NVR is needed. It is standard JWT verification. Pool and client IDs are configuration from `auth_api`.
- Keep `alerts_api`/MQTT out of the NVR (out of scope).

**Media authorization** is separate: see Pattern 5.

**Audit log:** logins, failures, camera add/remove/credential change, settings writes, playback and export access, deterrence actions, review/lock changes. Needed for FR-VMS-087/088 and cheap to add early.

### 4.9 REST API Design (web UI + Flutter app)

**One API, one contract.** Define it once as typed schemas on the server; the framework emits OpenAPI 3.1; commit `openapi.json`; generate the TS client for React and a Dart client for Flutter from it. Do not hand-write DTOs on either client.

**Versioning:**

- Path major version: `/api/v1`. Additive-only within v1 (new optional fields, new endpoints). Clients must ignore unknown fields. The camera docs state the same rule for firmware (`docs/external-api/README.md`).
- `GET /api/v1/system/info` (unauthenticated, minimal): `{nvr_id, name, api_version, min_client_version, features: [...]}`. `features` is a capability list in the spirit of the camera capability flags (`playback_mp4`, `events_pullpoint`, `cognito_link`, `export`). The phone gates UI on `features`, not on version arithmetic.
- CI runs an OpenAPI breaking-change diff (for example `oasdiff`) against the last released `openapi.json`. A breaking diff fails the build and forces `/api/v2`.
- Deprecation via `Deprecation`/`Sunset` headers plus a `features` removal notice. Mobile release cycles are slow, so v1 must live for as long as old app versions do.
- **Discovery:** advertise `_vizenlink-nvr._tcp` over mDNS (python-zeroconf) with `api_version` and `nvr_id` in the TXT record, so the phone finds it without typing an IP.

**Errors:** HTTP status plus RFC 9457 `application/problem+json` with a stable machine `code` enum (`camera_forbidden`, `camera_capability_missing`, `storage_full`, ...). This maps one-to-one to the Dart `CameraResult` pattern: 2xx → Success; problem+json → Failure(reason, code); transport timeout → Timeout. Do not reuse the old `{success, data|error}` envelope or the camera's `{error_code, error_msg, output}` envelope; plain HTTP semantics are better for generated clients.

**Resources (sketch):**

```
POST   /api/v1/auth/login | /refresh | /logout | /cognito/link | /cognito/exchange
GET    /api/v1/system/info | /system/health | /system/storage
GET/POST/PATCH/DELETE /api/v1/users[/{id}]

GET/POST /api/v1/cameras                  PATCH/DELETE /api/v1/cameras/{serial}
POST   /api/v1/discovery/scans   GET /api/v1/discovery/scans/{id}      # job, not a blocking call
GET    /api/v1/cameras/{serial}/status | /capabilities | /health
GET/PUT /api/v1/cameras/{serial}/recording            # mode, schedule, retention, record_profile
GET/PUT /api/v1/cameras/{serial}/settings/{group}     # imaging, encoder, osd, privacy-mode, ... capability-gated
GET    /api/v1/cameras/{serial}/snapshot
POST   /api/v1/cameras/{serial}/live                  # -> {whep_url, hls_url, token, expires_at, profile, state}
GET    /api/v1/cameras/{serial}/timeline?from&to      # coverage spans + event markers (catalog)
GET    /api/v1/cameras/{serial}/recordings[/dates]    # optional RecordingsList-shaped view
POST   /api/v1/cameras/{serial}/playback              # -> {url (mp4|fmp4), token, expires_at}
POST   /api/v1/exports   GET /api/v1/exports/{id}     # job; download URL carries a token
GET    /api/v1/events?camera&type&from&to&cursor      GET /api/v1/events/{id}  (includes recording ref)
PATCH  /api/v1/events/{id}                            # review_status, lock
GET    /api/v1/stream                                 # SSE: camera_state, event, segment_gap, storage, export
```

- **Cursor pagination** on events and recordings (the camera's own list truncates silently; do not copy that).
- **Time:** RFC 3339 UTC strings in JSON. If the mobile-compatible recordings view is adopted, use epoch seconds on that one resource to match `RecordingClip`.
- **Realtime push: SSE** (`text/event-stream`, `Last-Event-ID` resume) rather than WebSocket. It is server-to-client only, trivial in Flutter, and proxies well. Browsers' `EventSource` cannot set an `Authorization` header, so use a fetch-based SSE client, or a short-lived single-use stream ticket from `POST /stream/ticket`.
- **CORS:** same-origin for the bundled web UI (the old VMS used `*`). The phone needs no CORS.
- **Long operations** (discovery, export, firmware) are jobs with status resources, never a blocking POST.
- **Idempotency:** `PUT` for settings groups; `Idempotency-Key` on export creation.

### 4.10 Health Monitoring

Four layers, all feeding one per-camera state machine and one system banner (FR-VMS-045: failures are persistent banners, not scrolling feed items).

| Layer | Signal | Source | Cadence |
|-------|--------|--------|---------|
| Process | MediaMTX up, core workers alive, supervisor restarts | Supervisor, `GET /v3/info` | 5 s |
| Stream | path `online`/`available`, `inboundBytes` advancing, `inboundFramesInError`, readers | `GET /v3/paths/list` | 5-10 s |
| Camera | identity probe, `/nuraeye/health` (uptime, reboot count, clock sync), privacy mode, local-storage status | Camera Layer (cheap `areYouNuraeyeDevice` single-shot for reachability, as `LiveStreamUriClient.checkReachable` does) | 15-60 s, jittered |
| Recording | age of newest complete or open segment vs expected; gaps in last 24 h | Catalog | 30 s |
| Storage | free space, retention horizon, volume sentinel, I/O errors | Disk probe + Retention | 30-60 s |

**Camera states:** `recording`, `online_not_recording` (stalled: bytes flat while "online", or segment age over 2x segment length), `connecting`, `offline`, `auth_failed`, `tls_changed`, `identity_mismatch` (heals via re-IP), `privacy` (distinct from offline, FR-VMS-100), `disabled`. The **recording watchdog is the most important single signal** for the Core Value. A camera that is "online" but writing no segments is the failure users never see otherwise.

- MediaMTX already reconnects RTSP sources with its own backoff, so Python must not double-manage connections. Python only reacts to stall, auth, TLS and identity states.
- Health samples are rolled up (minute → hour) to keep SQLite small.
- Optional Linux `sd_notify` watchdog (`WatchdogSec`) on the supervisor.

---

## Data Flow

### Request Flow (control plane)

```
Browser/Phone ──► /api/v1/... ──► auth dep (session → role → permission)
                                     ↓
                    router ──► service ──► Registry/Catalog/Events (SQLite)
                                     ↓
                    (camera ops) ──► Camera Layer ──► CameraResult ──► problem+json mapper
```

### Key Data Flows

1. **Recording (data plane, no Python in the byte path):**
   `camera RTSPS → MediaMTX path (main) → fMP4 segment on disk → hook → Indexer → segments row (open → complete) → SegmentCompleted on bus → Health watchdog, SSE`.
   Retention later unlinks the file and deletes the row.

2. **Live view:**
   `UI → POST /cameras/{id}/live (role check, camera state) → signed token + WHEP/HLS URLs → UI connects directly to MediaMTX :8889/:8888 → MediaMTX verifies token → sub path starts on demand (one camera connection) → viewers share it`.

3. **Playback and timeline:**
   `UI → GET /timeline (catalog spans + events) → user picks a time → POST /playback (token) → UI plays :9996/get?path&start&duration&format=fmp4 → seek = new request`.

4. **Event → recording:**
   `camera PullPoint → Event Ingest (poll task) → normalize + debounce → events row → snapshot GET → protection_range → EventReceived on bus → SSE to UI/phone`.
   `UI opens event → GET /events/{id} → recording ref computed from catalog → /playback`.

5. **Camera add:**
   `Discovery → identity verify → creds → capabilities → stream URIs → TLS fingerprint → registry row → Reconciler pushes paths → recording begins → Event Ingest task starts → Health begins`.

6. **Camera comes back at a new IP:**
   `421 or connect failures → CameraIdMismatch → re-IP healer → WS-Discovery → match by serial → registry last_host updated → Reconciler patches path source → stream resumes`.

7. **Disk pressure:**
   `Retention tick → free below high watermark → delete oldest unprotected in fair-share rounds → StorageStateChanged → SSE banner if horizon < configured days`.

### State Management (web UI)

```
Server state: TanStack-Query-style cache over generated client  ←── SSE invalidates keys
UI state:     Simple/Advanced toggle (local), grid layout (local), selected camera/time (URL)
Capability document per camera drives which controls render
```

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 2-8 cameras (home) | Everything on one small box (Pi 4/5 class). Record the medium profile if disk is small. Live grid on sub streams only. No transcodes |
| 8-16 cameras (v1 target) | One host, one SQLite file. WebRTC session count and NIC are the first limits. Use sub streams in grids, `sourceOnDemand` for sub paths. Storage sizing is the main design input |
| 16-32 cameras (business) | Same architecture. First bottleneck is disk write throughput and capacity (dedicated recording disk, volume guard), then WebRTC CPU. Do not shard until proven necessary |

**Storage sizing (arithmetic, bitrate is an assumption):**

| Main-stream bitrate | Per camera / day | 16 cameras / day | 16 cameras / 30 days |
|---------------------|------------------|------------------|----------------------|
| 2 Mbps | 21.6 GB | 346 GB | 10.4 TB |
| 4 Mbps | 43.2 GB | 691 GB | 20.7 TB |
| 8 Mbps | 86.4 GB | 1.38 TB | 41.5 TB |

Ingest at 4 Mbps x 16 is about 8 MB/s of sequential writes, which is trivial for any disk but too heavy for an SD card (endurance). A real HDD or SSD is a hard requirement for the recording volume. The SQLite database (small, write-light) should live on flash, separate from the recording volume.

### Scaling Priorities

1. **First bottleneck: disk capacity/retention.** Solved by `record_profile`, quotas, horizon reporting.
2. **Second: WebRTC fan-out CPU/NIC.** Solved by sub-stream grids, HLS fallback tiles, on-demand paths.
3. **Third: camera HTTP concurrency.** Camera sessions (6) and RTSPS slots are the hard limits. Per-camera session lock and a single upstream per stream keep this under control.

---

## Anti-Patterns

### Anti-Pattern 1: Video through the application server

**What people do:** Proxy WHEP/HLS/MP4 through Flask or FastAPI to add auth.
**Why it's wrong:** Burns Python CPU and bandwidth, and couples live view to API health.
**Do this instead:** Scoped media tokens verified by MediaMTX (Pattern 5).

### Anti-Pattern 2: Per-viewer camera connections

**What people do:** Let each phone or browser open its own RTSP to the camera.
**Why it's wrong:** The camera allows few RTSPS clients per stream (2 verified) and 6 REST sessions; the NVR then blocks the owner's phone.
**Do this instead:** One upstream per stream into MediaMTX; clients read from MediaMTX.

### Anti-Pattern 3: Filesystem or JSON as the index

**What people do:** `segments.json` per camera, read-modify-written from a webhook (the old VMS).
**Why it's wrong:** Races between concurrent hooks, O(n) duplicate checks, no retention, no crash recovery, and times derived as `completed_at - duration`.
**Do this instead:** SQLite catalog with start times from the segment itself, state machine, and a scan that heals.

### Anti-Pattern 4: Heavy work inside the hook handler

**What people do:** FFmpeg remux inside the webhook request (the old VMS).
**Why it's wrong:** Blocks, uses CPU on a Pi, and a failure leaves segments unindexed.
**Do this instead:** The hook only records the fact. fMP4 needs no remux. Thumbnails or repairs run in a worker.

### Anti-Pattern 5: Cleaning up MediaMTX paths on exit

**What people do:** `atexit` deletes all registered paths.
**Why it's wrong:** Recording stops whenever the control process exits, which is the exact moment resilience matters.
**Do this instead:** Reconciler; MediaMTX keeps running under its own supervisor.

### Anti-Pattern 6: IP address as camera identity

**What people do:** `camera_id = ip.replace('.', '_')` (the old VMS).
**Why it's wrong:** A DHCP renewal orphans recordings and silently changes which camera a path records.
**Do this instead:** Serial primary key plus re-IP healer and the `X-VizenLink-Camera-Id` check.

### Anti-Pattern 7: Open media ports

**What people do:** Default MediaMTX permissions (`any` user can publish, read, playback).
**Why it's wrong:** Anyone on the LAN (guest Wi-Fi, a compromised IoT device) can watch cameras or publish a fake stream.
**Do this instead:** Loopback-only API, RTSP internal, RTMP/SRT off, token auth on WebRTC/HLS/playback.

### Anti-Pattern 8: Event-driven start/stop of recording for event mode

**What people do:** `PATCH record:true` on an event, `false` after.
**Why it's wrong:** No pre-roll, latency on first frames, boundary races, and a missed event means no footage.
**Do this instead:** Always record to a short buffer and protect ranges (Pattern 3).

### Anti-Pattern 9: Mirroring the Dart client by memory

**What people do:** Reimplement camera behavior from a skim of the docs.
**Why it's wrong:** The Dart package documents many hard-won quirks (SOAP faults on HTTP 200, 421, 6-session LRU, pagination truncation). Each one cost a real bug there.
**Do this instead:** Generated wire models, `behaviors.yaml`, lock file, fixtures, simulator.

### Anti-Pattern 10: Production-unsafe defaults carried from the old server

`debug=True`, CORS `*`, static file serving from the working directory, `shell=True` with interpolated hosts. Replace with an ASGI server, an explicit allow-list for static files, and `subprocess` argument lists.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Cameras (ONVIF/REST) | HTTPS, self-signed, WSSE digest and bearer session, `X-VizenLink-Camera-Id` | Header-case preservation; 6-session LRU; 428 on factory password; 421 on identity mismatch |
| Cameras (RTSPS) | Pulled by MediaMTX with `sourceFingerprint` | One upstream per stream; credentials percent-encoded |
| MediaMTX control API | `127.0.0.1:9997`, `/v3/config/paths/*`, `/v3/paths/list`, `/v3/recordings/*` | Pin the version. API-created paths are not persisted |
| MediaMTX playback | `:9996 /list /get` | Behavior across gaps needs a spike |
| MediaMTX hooks | Command hook calls helper, helper POSTs to loopback with secret | Cross-platform spike |
| FFmpeg (optional) | `create_subprocess_exec` | Live audio transcode (opt-in), thumbnails, repairs. Not on the recording path |
| AWS Cognito (optional) | JWKS fetch plus JWT verification | Cache JWKS; identity only, never authorization |
| mDNS | python-zeroconf | `_vizenlink-nvr._tcp` |
| OS service managers | systemd, launchd, WinSW | Installer subcommand per OS |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| API ↔ domain services | Direct calls | Thin routers |
| Domain ↔ Camera Layer | Direct async calls returning `CameraResult` | Camera Layer has no reverse dependency |
| Workers ↔ SSE | In-process bus | Bus events are the only coupling between ingest, health and push |
| Core ↔ MediaMTX | HTTP (control, hooks, auth) | Core restart must not stop recording; MediaMTX restart must not lose config |
| Web ↔ API | Generated TS client | Never hand-written DTOs |
| Mobile ↔ API | Generated Dart client (new `nvr_api` package in the mobile repo, with a sealed result wrapper like `CameraResult`) | Needs mobile-owner agreement; no change to `camera_api` |

---

## Suggested Build Order (dependencies)

```
[1 Foundations] ─► [2 Camera Layer core + sim + contract tooling]
        │                    │
        └────────────┬───────┘
                     ▼
[3 Registry + Reconciler + MediaMTX recording + Catalog/Indexer + basic Retention + Health watchdog]
                     │            ← "never miss footage" vertical slice, headless
        ┌────────────┼──────────────────────┐
        ▼            ▼                      ▼
[4 API v1 + Auth/Roles   [5 Events: PullPoint     [6 Camera settings proxy
  + media tokens           ingest, debounce,        (capability-gated) ]
  + Live (WHEP/HLS)        snapshot, linker,
  + React shell ]          protection ranges ]
        │                      │
        └──────────┬───────────┘
                   ▼
[7 Playback + timeline + event↔recording UI + Export]
                   ▼
[8 Mobile hardening: OpenAPI gate, Dart client, mDNS, Cognito link, SSE, RecordingsList view]
                   ▼
[9 Packaging: per-OS service installers, pinned MediaMTX per arch, upgrade/backup, hardware soak]
```

**Phase recommendations:**

| # | Phase | Why this order | Pitfalls it avoids | Research flag |
|---|-------|----------------|--------------------|---------------|
| 1 | Foundations: repo, config, SQLite + migrations, bus, supervisor skeleton, MediaMTX pinned launch with hardened config, volume guard | Everything else assumes a stable process model and secure MediaMTX | Orphan children, open ports, `os.uname` | Standard |
| 2 | Camera Layer core: result type, connection, WSSE, session cache, capabilities, discovery, identity, snapshot, simulator, `contracts/` tooling | The registry, health and events depend on it. Drift prevention is cheapest before code accumulates | Drift from Dart contracts; IP identity | **Needs research**: ONVIF PullPoint and Search payloads against a real camera; header-case/TLS client choice |
| 3 | Registry + Reconciler + recording + Catalog + Indexer + basic Retention + gap watchdog | This is the Core Value. Ship headless and soak it first | Gaps, disk-full, unmounted-volume writes, lost hooks | **Needs research (spike)**: fMP4 with this camera, timestamp behavior, hook invocation on Win/macOS/Linux, `%s` vs `%z` path tokens, playback `/get` across gaps |
| 4 | API v1, Auth/Roles, media tokens, live view (grid + single), React shell | Needs registry and MediaMTX; unlocks UI work | Open media ports; token-expiry session drops | **Needs research (spike)**: `jwt` vs `http` auth, JWKS laziness, make-before-break renewal, WebRTC on multi-NIC |
| 5 | Events: PullPoint ingest, `SetEventPreferences`, debounce, snapshots, protection ranges, event mode, alerts list | Needs camera layer, catalog, bus. Independent of UI | Wrong-way event source assumption; pre-roll loss | **Needs research**: confirm with firmware whether a NuraEye LAN feed exists; PullPoint hardware verification; event rates and ring-buffer overflow |
| 6 | Camera settings proxy (imaging, encoder, OSD, privacy, recording mode on camera) | Parallel after 2 and 4; large but mechanical, capability-gated | Ungated controls, role confusion | Standard (follows SETTINGS_API_GUIDE) |
| 7 | Playback timeline, event-to-recording jump, clip export, snapshot gallery | Needs 3, 4, 5 | Playback across gaps, huge exports | Spike result from phase 3 |
| 8 | Mobile integration: OpenAPI breaking-change CI gate, Dart client, mDNS, SSE, Cognito link, optional `RecordingsList`-shaped view | API must be stable first | Mobile/NVR drift; slow release cycles | Cognito link: moderate; coordinate with mobile owner |
| 9 | Packaging and soak: systemd/launchd/Windows service, upgrades, backup/restore of DB, hardware matrix (Pi, Jetson, PC, Windows, macOS) | Last, but start CI on Linux + macOS + Windows from phase 1 | Platform surprises discovered late | **Needs research**: WinSW vs pywin32, Jetson/Pi performance, USB disk hot-unplug |

Build **health and retention minimally in phase 3**, not later. A recorder that fills its disk or records into a missing mount fails the Core Value before any UI exists.

---

## Open Questions and Spikes

| # | Question | Why it matters | How to resolve |
|---|----------|----------------|----------------|
| 1 | Does the firmware offer any LAN alert push besides ONVIF PullPoint? Is PullPoint hardware-verified end-to-end (FR-OV-070 says build-verified 2026-08-07)? | Event architecture and the brief's stated priority order | Ask firmware owner; run PullPoint against a real camera |
| 2 | fMP4 vs MPEG-TS with this camera (timestamps, tiny segments, audio) | Recording format and whether any remux is needed | 24 h soak on one camera with fMP4, inspect gaps and durations |
| 3 | Does the playback server `/get` span gaps cleanly and seek well in `<video>` and Flutter `video_player`? | Playback UX design | Spike with synthetic gaps |
| 4 | Hook command execution on Windows/macOS/Linux; env var availability | Indexing latency | Spike; scanner remains the safety net |
| 5 | MediaMTX `jwt` vs `http` auth: JWKS fetch timing, behavior when core is down, session close on expiry | Live view resilience and renewal UX | Spike on pinned version |
| 6 | Exact RTSPS client limit per stream on shipped firmware, and whether sub-stream on-demand connect latency is acceptable in the grid | Live design and mobile coexistence | Test with 3 clients; measure on-demand start time |
| 7 | WebRTC viability on Pi/Jetson at 16 sessions | Live scaling | Load test on target hardware |
| 8 | Event-metadata-schema is a draft, not stable | Event table shape | Align with mobile owner; store `raw_json` to stay safe |

## Sources

- MediaMTX playback server, record, authentication docs: https://mediamtx.org/docs/features/playback , https://mediamtx.org/docs/features/record , https://mediamtx.org/docs/usage/authentication (HIGH, fetched 2026-10-26)
- MediaMTX Control API OpenAPI and current `mediamtx.yml` reference: https://raw.githubusercontent.com/bluenviron/mediamtx/main/api/openapi.yaml , https://raw.githubusercontent.com/bluenviron/mediamtx/main/mediamtx.yml (HIGH)
- MediaMTX releases (v1.21.3 notes: segment naming with time zone, session close on JWT expiry): https://github.com/bluenviron/mediamtx/releases (HIGH; page omitted the year)
- Frigate recording docs (segment cache, retention modes, pre/post capture, event-segment retention, low-headroom deletion): https://docs.frigate.video/configuration/record (HIGH)
- Moonfire NVR schema guide (SQLite plus sample-file directory, crash safety, wall vs media time): https://github.com/scottlamb/moonfire-nvr/blob/master/guide/schema.md (HIGH)
- Local primary sources (HIGH as written): `nuraeye-rt/mobile_app/packages/camera_api/{API_REFERENCE,SETTINGS_API_GUIDE,STREAMING_GUIDE}.md`; `nuraeye-rt/design/{Camera-REST-API.openapi.yaml,Camera-ONVIF-API.md,FR-vms.md,FR-camera-firmware.md,FR-nuraeye-service.md,FR-onvif-stack.md,FR-mobile-app.md}`; `nuraeye-rt/docs/external-api/{README,quick-start}.md`; `nuraeye-rt/kb/wiki/{event-metadata-schema,ai-detection-event-logging-design}.md`
- Old VMS (read-only reference): `nuraeye-rt/vms/{main.py,python/server.py,python/mediamtx_client.py,python/ws_discovery_scanner.py,mediamtx/mediamtx.yml}`
- General NVR structure for ZoneMinder/Shinobi and Windows/Python service wrapping: domain knowledge (MEDIUM, not re-verified this session)

---
*Architecture research for: LAN NVR/VMS for VizenLink/NuraEye cameras*
*Researched: 2026-10-26*
