# Technology Stack

**Project:** VizenLink NVR (Python + MediaMTX backend, React/TS web UI, REST API for Flutter, LAN only)
**Researched:** 2026-10-26
**Overall confidence:** MEDIUM-HIGH. Versions and MediaMTX behaviour were checked against the live PyPI/npm registries and MediaMTX v1.21.3 source and config (HIGH). Packaging, bundled-binary and hardware-specific points rest on reasoning or secondary sources and are marked MEDIUM or LOW.

Confidence tags: **HIGH** = verified in a primary source this session (registry, release, source code, official docs). **MEDIUM** = primary source plus judgement, or cross-checked secondary sources. **LOW** = single secondary source or unverified inference, so validate in a spike before committing.

---

## Headline decisions (read this first)

1. **Switch recording from `mpegts` to `fmp4`.** The old VMS records `mpegts`. MediaMTX's playback server (`/list`, `/get`) returns the error `"MPEG-TS format is not supported yet"` for mpegts, and `/v3/recordings/*` reports `duration: null` for mpegts. fMP4 is required for the built-in playback server, for exact segment durations, and for clip export without ffmpeg. HIGH, read from `internal/playback/on_get.go` and `on_list.go` at v1.21.3.
2. **FastAPI (async) replaces Flask.** The workload is many concurrent camera I/O calls, long-lived ONVIF PullPoint connections, SSE/WebSocket push, and an OpenAPI contract that the Flutter app and the React app both consume. Flask offers none of that natively. HIGH.
3. **One Python process, no external broker.** Use asyncio tasks supervised from the FastAPI lifespan, with SQLite in WAL mode. Do not add Celery, Redis, RQ or arq. They break "runs on a Pi and on Windows with one install". HIGH.
4. **MediaMTX stays the media plane. Python is the control plane.** Python supervises the MediaMTX subprocess, writes its config, registers camera paths through the Control API, indexes recordings and enforces auth through MediaMTX's HTTP-auth callback. Python never touches video bytes. HIGH.
5. **Pin TypeScript to 6.0.x, not 7.x, for now.** TS 7.0.2 is `latest` on npm (GA 2026-07-08) but ships no stable programmatic API until 7.1. `typescript-eslint` 8.72 declares `typescript <6.1.0`. HIGH.
6. **Do not build on a player framework.** Use a custom WHEP hook (about 100 lines on `RTCPeerConnection`), `hls.js` for the fallback, a native `<video>` for playback and a custom canvas timeline. No React NVR timeline component of production quality exists. MEDIUM.

---

## Recommended Stack

### Runtime baseline

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| CPython | **3.13** shipped (support floor 3.11) | Backend runtime | SQLAlchemy 2.1 (`>=3.11`), pydantic-settings 2.16 (`>=3.11`) and Starlette 1.10 (`>=3.11`) set the floor at 3.11. Raspberry Pi OS Bookworm ships 3.11. JetPack 6 (Ubuntu 22.04) ships 3.10, which is too old. Ship an interpreter managed by `uv` or embedded by PyInstaller and never depend on system Python. | HIGH (floor), MEDIUM (3.13 pick) |
| uv | 0.13.x | Python and venv bootstrap on Linux, dependency locking, dev workflow | Downloads standalone CPython for aarch64 and x86_64 Linux, so Jetson JetPack 6 works. One lockfile (`uv.lock`) for every platform. | HIGH |
| Node.js | 24 LTS or newer (build-time only) | Web UI build | Vite 8 needs `^20.19 \|\| >=22.12`. react-router 8 needs `>=22.22`. Never ships to the target machine. | HIGH |

### Backend core

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastAPI | `~=0.162` | REST API, OpenAPI, SSE, static UI hosting | Auto-generated OpenAPI 3.1 is the "documented NVR REST API" requirement. Pydantic v2 models double as the typed result/error model that mirrors `camera_api`. Built-in SSE (`fastapi.sse.EventSourceResponse`), so `sse-starlette` is not needed. Note: 0.x versioning, so pin a compatible range and run CI on upgrades. | HIGH (version), MEDIUM (SSE history from secondary source) |
| Starlette | (transitive, 1.10.x) | ASGI toolkit | Use directly for `StaticFiles` and WebSocket. | HIGH |
| Uvicorn | `~=0.54`, plain install (no `[standard]` extra) | ASGI server | Run **one worker** (`workers=1`): in-process state (ONVIF pollers, MediaMTX supervisor, SQLite writer). Plain `uvicorn` uses h11 and asyncio, which are portable. The `[standard]` extra adds uvloop (not on Windows) and httptools (compile risk on armv7). HIGH-level throughput is irrelevant at about 16 cameras. | HIGH |
| Pydantic | `~=2.14` | Models, validation, OpenAPI schemas | Required by FastAPI. | HIGH |
| pydantic-settings | `~=2.16` | Typed config (env + TOML in data dir) | Same model layer as the API. | HIGH |
| httpx | **0.28.1** (see note) | Async client for MediaMTX Control API, camera REST and ONVIF SOAP | `httpx.DigestAuth`, `verify=False` or custom `SSLContext` for self-signed camera certs, `AsyncClient` connection pooling. Replaces the old `requests` + `urllib3` code. **Caveat:** httpx 0.28.1 dates from 2024-12 and the 1.0 line is stuck at `1.0.dev6`. Pydantic has taken over as `httpx2` 2.16.0 (2026-10-21, `import httpx2`, anyio-based, `>=3.11`). FastAPI's `[standard]` extra now lists `httpx2`. **Decision:** wrap all HTTP in one internal `http.py` module so swapping `httpx` for `httpx2` is a one-file change. Re-evaluate at roadmap kickoff. | HIGH (facts), MEDIUM (which to pick) |
| anyio | `~=4.15` | Structured concurrency (`TaskGroup`, cancel scopes) for supervised background tasks | Already a dependency of Starlette. Task groups give clean shutdown of per-camera tasks. | HIGH |

### Database and persistence

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| SQLite | bundled with Python (WAL mode) | Recordings index, events, cameras, users, settings | Zero-install, single file, runs on every target. Expected volume is small: 16 cameras at 5-minute segments is about 4.6k rows/day, so about 140k rows for 30 days. Set `PRAGMA journal_mode=WAL; synchronous=NORMAL; foreign_keys=ON; busy_timeout=5000`. | HIGH |
| SQLAlchemy | `~=2.1` (2.1.6) | ORM and Core, async | Typed 2.x style, `AsyncSession`. Do **not** use SQLModel (0.0.48, pre-1.0, thin layer over SQLAlchemy) because it hides the 2.x features you need. | HIGH |
| aiosqlite | `~=0.22` | Async SQLite driver for SQLAlchemy | Keeps the event loop free. Use one engine, short transactions, and funnel heavy writers (segment indexer) through a single task. Last release 2025-12, so stable but slow-moving. | MEDIUM |
| Alembic | `~=1.20` | Migrations | Run `alembic upgrade head` programmatically at startup. Use `render_as_batch=True` for SQLite ALTER limits. Migration scripts must be listed as PyInstaller data files. | HIGH |
| platformdirs | `~=4.13` | Per-OS data, config and log directories | Windows `%PROGRAMDATA%`, macOS `~/Library/Application Support`, Linux `/var/lib` or XDG. | HIGH |

Recordings themselves live on the filesystem (MediaMTX-owned). The DB stores only an index that is rebuildable from disk (see ARCHITECTURE: filesystem is source of truth).

### Background work

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| asyncio tasks + anyio TaskGroup in the FastAPI `lifespan` | stdlib / anyio | MediaMTX supervisor, per-camera health ping, per-camera ONVIF PullPoint loop, segment indexer/reconciler, retention sweeper, recording-mode scheduler, mDNS announce | One loop, no broker, trivially portable. A 30 s tick loop that evaluates schedules and PATCHes `record` is simpler and more testable than a scheduler library. | HIGH |
| `asyncio.to_thread` / `ProcessPoolExecutor` | stdlib | Rare CPU or blocking work (thumbnails, MP4 header parsing) | Keeps loop responsive. | HIGH |
| psutil | `~=7.2` | Disk, CPU, memory, temperature for the health endpoint | Cross-platform wheels. Use `shutil.disk_usage` for free-space checks on the recordings volume. | HIGH |

**Not used:** APScheduler (3.11.3 is stable but 4.x is still alpha, and a plain tick loop is enough), Celery/Redis/RQ/arq (need a broker), `watchfiles` (only as an optional accelerator for the indexer, not a hard dependency).

### Media plane: MediaMTX

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **MediaMTX** | **v1.21.3** (2026-10-25). Pin the exact version and verify the SHA-256 from `checksums.sha256`. | RTSP(S) ingest from cameras, relay (RTSP/WebRTC/HLS), fMP4 recording, playback server | Release assets exist for darwin amd64/arm64, linux amd64/arm64/armv6/armv7 and windows amd64, covering every target. v1.21.x adds `duration` to fMP4 segments, fixes `recordPath` timezone handling and recorder timestamp discontinuities, and ends sessions when a JWT expires. Ten-plus releases since 2026-04 means a fast cadence, so pin and upgrade deliberately. | HIGH |

**Required configuration decisions** (generate `mediamtx.yml` from code, based on the v1.21.3 default, never copy the old repo's file, which predates several renamed keys):

| Setting | Value | Reason |
|---------|-------|--------|
| `recordFormat` | `fmp4` | Playback server, durations, export. (See headline 1.) |
| `recordPath` | `<rec>/%path/%Y-%m-%d_%H-%M-%S-%f_%z` | v1.21.3 default includes `%z`. Without it, segments can overwrite or mis-order across DST changes (v1.21.3 now warns). Parse start time plus offset from the filename in the indexer. |
| `recordSegmentDuration` | `5m` (configurable) | Matches the old VMS. Gives clean retention granularity and bounded index growth. `recordPartDuration: 1s` is the crash RPO. |
| `recordDeleteAfter` | per-path, from retention policy | Time-based retention handled by MediaMTX. **Size-based and disk-full retention must be done by the backend** (delete oldest segments via `POST /v3/recordings/segments/delete` or the filesystem). |
| `playback` | `true`, `playbackAddress: :9996` | Timeline playback and clip export. `GET /list?path=&start=&end=` returns `[{start, duration, url}]` with adjacent segments concatenated. `GET /get?path=&start=&duration=&format=fmp4\|mp4` streams the result. |
| `authMethod` | `http` | MediaMTX calls `POST /internal/mtx-auth` on the Python backend for every non-excluded action. Keep `authHTTPExclude: [api, metrics, pprof]` and bind `apiAddress` to `127.0.0.1:9997`. See the Auth section. v1.21.x lets the HTTP auth response set a session expiry. |
| `moq`, `rtmp`, `srt` | `false` | `moq: true` is the new default and opens 8892/8893. Disable everything unused to shrink attack surface and avoid port conflicts. |
| `rtspTransport` per camera path | `tcp` | As in the old client. Avoids UDP loss on Wi-Fi cameras. |
| `sourceFingerprint` | SHA-256 of camera cert | Cameras expose self-signed RTSPS. Port the old `get_tls_fingerprint` logic but **use only the pure-Python `ssl` fallback**. The `openssl ... \| cut \| tr` shell pipeline in the old code fails on Windows. |
| `webrtcAdditionalHosts` / `webrtcIPsFromInterfaces*` | set from the backend's detected LAN IPs | WHEP fails silently when ICE candidates carry a wrong or Docker-bridge IP. |
| `hlsVariant` | `lowLatency` (LL-HLS) | Fallback for browsers or networks where WebRTC UDP (8189) is blocked. |

**Path layout:** two paths per camera: `cam_<id>` (main stream, record target) and `cam_<id>_sub` (low-res stream for multiview grids; fall back to main if the camera exposes only one profile). The backend is the source of truth and **re-registers all paths idempotently on every MediaMTX (re)start**. Paths added through the Control API are not persisted, so the old client's `atexit` cleanup should not be ported.

**Control API calls used:** `/v3/config/paths/{add,patch,replace,delete}`, `/v3/paths/list` (online/ready state, reader counts), `/v3/recordings/list` and `/v3/recordings/get/{name}` (segment starts and durations for reconciliation), `/v3/recordings/segments/delete`.

**Process supervision:** start MediaMTX with `asyncio.create_subprocess_exec` (works with the Windows Proactor loop), capture stdout into the app log, restart with exponential backoff, and expose "recorder health" from `/v3/paths/list` plus process liveness. Do not use `runOnConnect`-style shell hooks for correctness.

**Segment indexing strategy:** a periodic reconciler that diffs `/v3/recordings/list` (or the directory scan) against the DB every 30-60 s is the correctness path. `runOnRecordSegmentComplete` is an optional low-latency accelerator only. Reason: MediaMTX runs hooks through a shell, and the old `curl ... $MTX_SEGMENT_PATH` command depends on `sh` variable expansion and `curl` being present, which breaks on Windows. A hook is also lost while the backend is down. If a hook is wanted, give it a tiny cross-platform entrypoint (`vizenlink-nvr hook segment`) and treat missed calls as normal. MEDIUM (Windows shell behaviour inferred, not tested).

### Camera protocols (ONVIF, NuraEye, discovery)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **Port the existing hand-rolled SOAP client** (`onvif_http_client.py`, `onvif_utils.py`, `onvif_*_service.py`, `nuraeye_http_client.py`) onto `httpx` + `xmltodict` | `xmltodict ~=1.0` | ONVIF Device/Media/Imaging/Analytics and NuraEye `/nuraeye/*` REST | The old code already implements WS-UsernameToken digest (nonce + created), self-signed TLS handling and the exact service subset VizenLink cameras need, and it is what `camera_api` was validated against. A generic ONVIF library adds a WSDL parse cost, large memory and PyInstaller data-file pain for no feature gain, since third-party cameras are out of scope for v1. Make it async, add typed Pydantic results, and add a `Result[T, CameraError]` shape matching `camera_api`'s `CameraResult`. | MEDIUM-HIGH |
| ONVIF events | same client, new module | PullPoint: `CreatePullPointSubscription`, `PullMessages`, `Renew`, `Unsubscribe` | Needed as the LAN event path (camera notes say `EventMgr_Send()` also delivers via ONVIF PullPoint). One asyncio task per camera with long-poll `PullMessages` plus renew and resubscribe on failure. **There is no PullPoint code in the old repo** (only `onvif_analytics_service.py`), so this is new work and the first thing to spike on a real camera. | MEDIUM |
| WS-Discovery | **port `ws_discovery_scanner.py`** (raw UDP multicast `239.255.255.250:3702`, Probe with custom `namespace`/`local_name`) | Find VizenLink/NuraEye cameras | The scanner already does per-interface multicast plus unicast receive and VizenLink-specific type filtering. Replace the abandoned `netifaces` (last release 2021-05) with **`ifaddr`** (pure Python, no compile; already a transitive dependency of `zeroconf`). | MEDIUM-HIGH |
| ifaddr | `~=0.2` | Enumerate NICs and IPs for multicast joins | Pure Python, works on all targets. | HIGH |
| zeroconf | `~=0.151` | Advertise the NVR as `_vizenlink-nvr._tcp.local.` | Lets the Flutter app auto-find the NVR on the LAN (mobile side uses `nsd` or `multicast_dns`). Cheap, and removes manual IP entry. | MEDIUM |

**Do not use:** `onvif-zeep` (last PyPI release 2018-08), `python-onvif-zeep` (stale), `WSDiscovery` 2.1.2 (sync and threaded, last release 2025-01, would still need the VizenLink-specific probe), and `netifaces` (dead; no wheels for some ARM or Windows combos).

**Considered alternative:** `onvif-zeep-async` 4.3.0 (2026-09-28, Home Assistant's fork, actively maintained, uses aiohttp + zeep). It is the right pick if the product ever needs generic ONVIF cameras. Keep it as the documented escape hatch, not v1.

### Authentication and authorization

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyJWT (`pyjwt[crypto]`) | `~=2.15` | Issue and verify NVR tokens; verify Cognito RS256 tokens | `PyJWKClient` handles JWKS fetch, caching by `kid` and key rotation. `[crypto]` pulls `cryptography` 50.x. | HIGH |
| pwdlib (`pwdlib[argon2]`) | `~=0.3` | Password hashing | Argon2id, the FastAPI-documented replacement for passlib. Tune memory and time cost down on Pi-class CPUs and benchmark login latency. Do not use passlib (unmaintained). | HIGH (library), MEDIUM (tuning) |
| Local accounts + roles | in DB | Owner/Admin, Operator, Viewer | RBAC enforced by a FastAPI dependency (`require_role(...)`) on every route, with per-camera ACLs deferred. | HIGH |

**Token design:** short-lived access JWT (about 15 min, claims `sub`, `role`, `jti`) plus a rotating opaque refresh token stored hashed in SQLite (revocable, works offline). Sign with a per-install key generated on first run and kept in the data directory. HS256 is acceptable. Use ES256 if MediaMTX native JWT mode is ever adopted (it needs a JWKS URL and the `mediamtx_permissions` claim).

**Media access control (important):** set MediaMTX `authMethod: http` and implement `POST /internal/mtx-auth` in FastAPI. The request body carries `user`, `password`, `token`, `ip`, `action` (`read`/`playback`/`publish`/...), `path`, `protocol`, `query`. Accept the NVR access JWT from `token` (WHEP `Authorization: Bearer`), from `query` (HLS/playback `?jwt=`) or from the password field (RTSP clients that only take `user:pass`). Check the role against `action` and `path`. This gives viewers and mobile one credential for API, WHEP, HLS, RTSP and playback. The old VMS used `authInternalUsers: any`, which means unauthenticated media from anywhere on the LAN. A Viewer must never be able to `publish`.

**Optional Cognito link** (`auth_api` parity): the mobile app already holds Cognito tokens. It posts the ID or access token to `POST /auth/cognito/link`. The NVR verifies with `PyJWKClient("https://cognito-idp.<region>.amazonaws.com/<poolId>/.well-known/jwks.json")`, algorithm `RS256` only, then checks `iss == https://cognito-idp.<region>.amazonaws.com/<poolId>`, `exp`, `token_use`, and `aud` (ID token) or `client_id` (access token) against the configured app client. It then binds the Cognito `sub` to a local user and **issues a normal NVR token pair**. After linking, the NVR never needs the internet. Cache the JWKS on disk so offline re-link still works. Do **not** add `boto3`, `pycognito` or Amplify equivalents. Cognito signing keys rotate, so refresh on an unknown `kid`. HIGH (claim rules from AWS developer guide); the config field names (pool id, client id, region) must come from `auth_api`.

**CORS/CSRF:** with Bearer tokens in the `Authorization` header, CSRF is not applicable. Serve the React build from the same origin as the API so CORS stays off for the web UI, and enable a restricted `CORSMiddleware` only for dev (`localhost:5173`). The Flutter app is not a browser, so CORS does not apply to it. For the web refresh token use an `HttpOnly; SameSite=Strict` cookie (add `Secure` only when TLS is on).

### API contract and realtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| OpenAPI 3.1 from FastAPI (checked into `api/openapi.json` in CI) | n/a | The documented REST contract for web and Flutter | Single source of truth. Fail CI on unreviewed drift. Design resource-style REST (`GET /cameras`, `PATCH /cameras/{id}/recording`, `GET /cameras/{id}/recordings?from&to`) instead of the old `POST /api/vms/*` RPC with a `{success,data\|error}` envelope. Use HTTP status plus an RFC 9457-style error body, and keep camera-setting payloads and capability flags identical to `camera_api` semantics. | HIGH (mechanism), MEDIUM (style choice) |
| Server-Sent Events (`fastapi.sse`) | built in | Push of camera online state, events/alerts, recording state, disk warnings to web and Flutter | One-way push is all that is needed. SSE reconnects natively in browsers and is trivial from Dart's HTTP client. Prefer SSE over WebSocket here. Use WebSocket only if a bidirectional feature appears. | MEDIUM |
| orjson | `~=3.13` | Faster JSON for large list endpoints | Optional. Add only if profiling demands. | MEDIUM |

**Flutter note:** FastAPI emits OpenAPI 3.1. Many Dart generators handle 3.0 better. Spike generating a Dart client early (or hand-write a thin client over `dio`) before the mobile team depends on codegen. LOW (not verified, mobile side out of scope).

**LAN transport note:** iOS App Transport Security and Android cleartext policy block plain `http://` by default, and LL-HLS on Apple devices requires HTTPS (called out in MediaMTX's own config comments). Plan an optional self-signed or per-install CA TLS mode in the backend (via `cryptography`) from the start, and in v1 document the ATS and cleartext exceptions the Flutter app needs. MEDIUM.

### Frontend (React + TypeScript + Vite)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| React | `^19.3` | UI | Required by the project decision. | HIGH |
| Vite | `^8.3` | Dev server and build (Rolldown-based) | Requires Node `^20.19 \|\| >=22.12`. | HIGH |
| `@vitejs/plugin-react` | `^6.1` | React transform | v6 requires Vite 8. | HIGH |
| **TypeScript** | **`~6.0.3`** | Type checking and tooling | See headline 5. Optionally add TS 7 under an npm alias (`@typescript/native-preview` or `typescript7: npm:typescript@7`) for a fast non-blocking `tsc --noEmit` in CI. Revisit when 7.1 restores the API. | HIGH |
| TanStack Query | `^5.104` | Server state, polling, cache invalidation from SSE | Standard for REST plus push. | HIGH |
| Zustand | `^5.0` | Small client state (selected cameras, view mode, timeline cursor) | Lightweight. | HIGH |
| React Router | `^8.5` (library/SPA mode) | Routing | Needs Node `>=22.22` and React `>=19.2.7`. TanStack Router is a fine alternative, so do not mix them. | MEDIUM |
| Tailwind CSS + `@tailwindcss/vite` | `^4.3` | Styling | v4 Vite plugin supports Vite 8. | HIGH |
| shadcn/ui (CLI 4.x, copy-in components, Radix or Base UI primitives) | CLI `^4.22` | Accessible UI primitives (dialogs, dropdowns, tabs) | Components are copied into the repo (no runtime dependency). Fits the Simple/Advanced toggle and role-gated UI. | MEDIUM |
| openapi-typescript + openapi-fetch | `7.13` / `0.17` | Generate TS types from the FastAPI OpenAPI and a typed fetch client | Tiny, no runtime codegen. **Peer dependency is `typescript ^5.x`**, so under TS 6 use an npm `overrides`/`--legacy-peer-deps` entry and verify generation in CI. Fallback: `@hey-api/openapi-ts` 0.99 (peer accepts TS 6, but 0.x with churn). | MEDIUM |
| zod | `^4.6` | Runtime validation for forms and untrusted payloads | Pair with `react-hook-form ^7.91` for camera settings forms. | HIGH |
| lucide-react | `^1.61` | Icons | | HIGH |
| `@tanstack/react-virtual` | `^3.14` | Virtualised lists for events and recordings search | | HIGH |
| Vitest | `^5.0` | Unit and component tests | Peer supports Vite 8. | HIGH |
| Playwright | `^1.64` | E2E, including WebRTC video smoke tests in Chromium | | HIGH |
| ESLint + typescript-eslint | ESLint 9/10, ts-eslint `^8.72` | Lint | ts-eslint peer is `typescript >=4.8.4 <6.1.0`, the reason for the TS 6 pin. | HIGH |

### Video players and timeline

| Concern | Choice | Version | Why | Confidence |
|---------|--------|---------|-----|------------|
| **Live, single view and grid (primary)** | **WebRTC via WHEP**, custom `useWhep(path, token)` hook on `RTCPeerConnection` | none | MediaMTX serves WHEP at `http://host:8889/<path>/whep`: POST SDP offer, Bearer token, PATCH for trickle ICE, DELETE to close. About 100 lines, no dependency, and full control of reconnect and token refresh. Sub-second latency. Candidate libraries (`@eyevinn/webrtc-player` 0.13.0, `whip-whep` 1.2.0 from 2024) are small, single-vendor and add little over the hook. | MEDIUM-HIGH (protocol standard; MediaMTX URL shape widely documented, auth-header path confirmed only via secondary sources, so verify in the first spike) |
| **Live fallback** | **hls.js** (LL-HLS from MediaMTX `:8888`) | `^1.7.3` | Used when WebRTC fails (UDP 8189 blocked, VLAN or firewall) or for Safari. 2-3 s latency. Set `lowLatencyMode: true`. LL-HLS on Apple needs HTTPS (see LAN transport note). | HIGH |
| **Recorded playback** | Native `<video>` + MediaMTX playback `/get?...` (fMP4) | none | Docs say fMP4 plays natively in `<video>`. Source shows the response sets `Accept-Ranges: none`, so **the browser cannot range-seek**. Model "seek" as a new request: `start = clicked time`, `duration = remaining window`, and re-request when the stream ends or the cursor crosses a gap. `playbackRate` works natively for speed control. Use `format=mp4` only for downloads and export (it buffers the whole result). | MEDIUM-HIGH (source-verified header; browser behaviour must be spiked on Chrome, Safari and iOS) |
| Player chrome | Own components. Optional `media-chrome` 4.19 for web-component controls | `^4.19` | Video.js 10.2 (merged with Vidstack) and `@vidstack/react` 1.15 are VOD-centric frameworks. They fight a timeline-driven, multi-stream, token-refreshing NVR UI. | MEDIUM |
| **Timeline** | **Custom canvas component** using `d3-scale` + `d3-time` for the time axis | d3-scale `4.0.2` | Needs: 24 h or multi-day zoom, one row per camera, coverage bars from `/list` or the DB, event markers, drag-scrub, wheel and pinch zoom, DST-safe, synced cursor across a grid. Draw coverage and events on `<canvas>` with a DOM overlay for the cursor. Roughly 400-600 LOC and the highest-risk UI piece. Fallback for a prototype only: `vis-timeline` 8.5.5 (active, but DOM-per-item and awkward to wrap in React). Avoid `react-calendar-timeline` (still `0.30.0-beta.4`). | MEDIUM |

**Codec constraints that shape the player choice:** WebRTC in browsers needs H.264 (and MediaMTX WebRTC drops AAC audio; Opus or G.711 pass). HLS fMP4 carries AAC. H.265 cameras will not play over WebRTC in most browsers, and HEVC over HLS depends on hardware decode. Confirm the NuraEye stream codec and audio format per profile in the first camera spike. LOW-MEDIUM (browser codec matrix is general knowledge, not verified here).

**Multiview rule:** grids use `cam_<id>_sub` over WHEP, with the main stream only in the single-camera view. A 16-tile grid of main streams will saturate browser decode and LAN bandwidth. Cap concurrent live sessions per client and pause tiles that are off-screen.

### Packaging and distribution

| Target | Method | Tooling | Confidence |
|--------|--------|---------|------------|
| **Single deliverable** | One Python wheel containing the backend, migrations and the built `web/dist` (served via `StaticFiles`). The backend downloads or locates the pinned MediaMTX binary for its platform, verified by SHA-256 against a checksum list shipped in the wheel. | `uv build`, `hatchling` | MEDIUM |
| Linux x86_64 and arm64 (Raspberry Pi 64-bit, Jetson, PC) | **Install script + systemd unit** using `uv tool install` (uv fetches CPython 3.13, which makes JetPack 6's Python 3.10 irrelevant). Also publish a **multi-arch Docker image** (`linux/amd64`, `linux/arm64`) with `network_mode: host`. | uv, Docker buildx | MEDIUM |
| Raspberry Pi 32-bit (armv7) | Treat as best-effort. `cryptography` and `argon2-cffi` wheels for armv7 are not verified. Recommend 64-bit Pi OS and drop armv7 from v1 unless a customer requires it. | | LOW |
| Windows x64 | **PyInstaller `--onedir`** bundle with MediaMTX `windows_amd64` bundled, wrapped in an installer (Inno Setup) that registers a Windows service (WinSW 3.x, not NSSM which is unmaintained) and opens firewall rules for 8554/8889/8189/8888/9996. | PyInstaller 6.22, Inno Setup, WinSW | MEDIUM-LOW |
| macOS arm64 / x86_64 | PyInstaller `--onedir` + MediaMTX darwin build, **codesigned and notarized** (Developer ID), launched via a `launchd` agent. macOS "Local Network" privacy prompts affect WS-Discovery multicast. | PyInstaller, `codesign`, `notarytool` | MEDIUM-LOW |
| CI | GitHub Actions matrix on native runners (PyInstaller cannot cross-compile): ubuntu x64, ubuntu arm64, windows, macOS arm64 (+ Intel runner if still needed). | | MEDIUM |

**Why not just Docker everywhere:** on Docker Desktop (Windows and macOS) host networking is unavailable, so WebRTC UDP candidates and WS-Discovery multicast do not reach the container. Docker is Linux-only here.

**Why not Nuitka, Briefcase, Electron or pywebview:** Nuitka (4.3.1) is slower to build and gives no functional gain. Briefcase 0.4.6 targets GUI apps, and the NVR is a headless service with a browser UI. Electron/pywebview/Flutter desktop add a second runtime and were rejected in PROJECT.md.

**PyInstaller hazards to budget for:** uvicorn and SQLAlchemy dialect hidden imports, Alembic scripts and `web/dist` as data files, antivirus false positives on unsigned Windows binaries, and the macOS notarization pipeline. Run a smoke test of the packaged artifact (start, `/health`, register a mock camera) in CI for every platform.

### Optional media tooling

| Tool | Purpose | Recommendation |
|------|---------|----------------|
| ffmpeg (system binary, optional) | Recording thumbnails, snapshot frames from recordings | **Do not require it.** Clip export uses the MediaMTX playback `/get` endpoint (`format=mp4`), so no ffmpeg is needed. Detect ffmpeg at startup and enable thumbnails if present. |
| PyAV (`av` 19.0.2) | In-process thumbnail extraction if ffmpeg is unwanted | Defer. It bundles FFmpeg in wheels, but arm/Windows wheel coverage is unverified. LOW |
| Pillow | Snapshot gallery thumbnails | Add when the snapshot gallery is built. |
| `ffmpeg-python` | n/a | **Do not use.** Last release 2019, a thin command builder that adds nothing over `subprocess`. |

### Development tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| ruff | `~=0.17` | Lint and format | Replaces black, isort, flake8. |
| mypy | `~=2.4` | Static types | Or pyright (1.1.414). Pick one. Use strict mode on the `camera` and `api` packages. |
| pytest, pytest-asyncio | 9.1 / 1.4 | Tests | Use `pytest-httpx` (0.36) or `respx` (0.23) to mock camera and MediaMTX HTTP. If `httpx2` is chosen, confirm mock-library support first. |
| A fake camera and fake MediaMTX fixture | in-repo | Contract tests against `camera_api` fixtures | The riskiest layer (ONVIF/NuraEye parity) needs recorded request and response fixtures from real cameras. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Web framework | FastAPI | Flask (current) | Sync WSGI. No native async I/O, SSE or OpenAPI. The current `server.py` is a 1.8k-line RPC file. |
| Web framework | FastAPI | Litestar, Quart | Smaller ecosystem. Nothing that FastAPI lacks for this scope. |
| Task runner | asyncio in lifespan | Celery / RQ / arq / Dramatiq | Need a broker (Redis/RabbitMQ). Hostile to the Windows and Pi single-install goal. |
| Scheduler | tick loop | APScheduler 3.x/4.x | 4.x still alpha, 3.x adds a dependency to solve a 30 s loop. |
| DB | SQLite (WAL) | PostgreSQL / TimescaleDB | Server install on a Pi or Windows box. Row counts are tiny. |
| ORM | SQLAlchemy 2.1 | SQLModel 0.0.48 | Pre-1.0 wrapper. Hides 2.x features. |
| Recording format | fMP4 | mpegts (current) | Playback server rejects it, no durations. Only advantage was crash-tolerance, and fMP4's 1 s parts give the same RPO. |
| Playback | MediaMTX `/get` | Self-built HLS VOD from the index (EXT-X-MAP + byte ranges) or ffmpeg remux | Better seeking, but real work. Keep as the upgrade path if `Accept-Ranges: none` hurts scrubbing in the spike. |
| Live view | WebRTC (WHEP) + LL-HLS fallback | HLS only | 2-3 s latency is poor for PTZ and guard use. Keep HLS as fallback. |
| ONVIF | ported hand-rolled client | onvif-zeep-async 4.3.0 | Heavy, generic, data-file packaging cost. Revisit for third-party cameras. |
| ONVIF | ported hand-rolled client | onvif-zeep 0.2.12 | Last released 2018. |
| HTTP client | httpx (behind a wrapper) | requests (current) | Sync, blocks the loop. |
| HTTP client | httpx (behind a wrapper) | aiohttp 3.14 | Fine and active, but `httpx.DigestAuth` and FastAPI test integration favour httpx. |
| Password hash | pwdlib[argon2] | passlib, bcrypt | passlib unmaintained. bcrypt truncates at 72 bytes. |
| JWT | PyJWT | python-jose, authlib | python-jose is poorly maintained. authlib is heavier than needed. |
| Cognito | PyJWT + JWKS | boto3 / pycognito | Large dependency. Verification only needs the public JWKS. |
| Realtime push | SSE | WebSocket | One-way push is enough. SSE is simpler across Flutter and browsers. |
| TS types | openapi-typescript | Orval 8.45, @hey-api/openapi-ts | Orval pulls more tooling. hey-api is 0.x. Reconsider if TS 6 peer pain is large. |
| Timeline | custom canvas | vis-timeline, react-calendar-timeline | See timeline row. |
| Player framework | custom hooks + hls.js | Video.js 10, Vidstack | VOD-oriented, fights multi-stream grid and token handling. |
| Desktop packaging | PyInstaller + installers | Briefcase, Nuitka, Electron | See packaging section. |
| Router | React Router 8 | TanStack Router | Both fine. Choose one. |
| Interface discovery | ifaddr | netifaces | Abandoned in 2021. |

## What NOT to Use (summary)

- `netifaces`, `onvif-zeep`, `python-onvif-zeep`, `ffmpeg-python`, `passlib`, `python-jose`: unmaintained.
- `requests` inside the event loop: blocking.
- MediaMTX `authInternalUsers: any` for media: leaves RTSP, WebRTC, HLS and playback open to the whole LAN.
- Shell-pipeline hooks (`curl ... $VAR`, `openssl ... | cut | tr`) in cross-platform code paths.
- `recordFormat: mpegts`: incompatible with playback and `/v3/recordings` durations.
- TypeScript 7 as the primary compiler until 7.1 (tooling gap).
- Multiple Uvicorn workers: breaks in-process supervisors and SQLite write ownership.
- Docker Desktop for Windows or macOS as an install path: breaks WebRTC UDP and multicast discovery.
- Copying the old `mediamtx.yml`: stale key set; generate from the v1.21.3 template.

## Installation

```bash
# --- Backend (Python 3.13 via uv) ---
uv init --package vizenlink-nvr --python 3.13
uv add "fastapi~=0.162" "uvicorn~=0.54" "pydantic~=2.14" "pydantic-settings~=2.16" \
       "sqlalchemy[asyncio]~=2.1" "aiosqlite~=0.22" "alembic~=1.20" \
       "httpx==0.28.1" "anyio~=4.15" "xmltodict~=1.0" "ifaddr~=0.2" "zeroconf~=0.151" \
       "pyjwt[crypto]~=2.15" "pwdlib[argon2]~=0.3" "psutil~=7.2" "platformdirs~=4.13"
uv add --dev "pytest~=9.1" "pytest-asyncio~=1.4" "respx~=0.23" "ruff~=0.17" "mypy~=2.4" "pyinstaller~=6.22"

# --- MediaMTX (pinned, verify checksum) ---
# https://github.com/bluenviron/mediamtx/releases/tag/v1.21.3
#   mediamtx_v1.21.3_{linux_amd64,linux_arm64,darwin_arm64,darwin_amd64,windows_amd64}

# --- Web UI (Node 24 LTS+) ---
npm create vite@latest web -- --template react-ts
cd web
npm install react@^19.3 react-dom@^19.3 react-router@^8.5 \
            @tanstack/react-query@^5.104 zustand@^5 hls.js@^1.7 \
            zod@^4 react-hook-form@^7.91 lucide-react @tanstack/react-virtual \
            d3-scale@^4 d3-time@^3 openapi-fetch@^0.17
npm install -D vite@^8.3 @vitejs/plugin-react@^6.1 typescript@~6.0.3 \
            tailwindcss@^4.3 @tailwindcss/vite@^4.3 openapi-typescript@^7.13 \
            vitest@^5 @playwright/test@^1.64 eslint typescript-eslint@^8.72
# openapi-typescript peer dep is typescript ^5.x: add an "overrides" entry for TS 6 and verify in CI.
```

## Version verification log (2026-10-26)

PyPI: fastapi 0.162.0, uvicorn 0.54.0, sqlalchemy 2.1.6, alembic 1.20.1, aiosqlite 0.22.1, pydantic 2.14.1, pydantic-settings 2.16.1, pyjwt 2.15.1, pwdlib 0.3.1, httpx 0.28.1 (httpx2 2.16.0), zeep 4.3.3, onvif-zeep-async 4.3.0, zeroconf 0.151.5, psutil 7.2.2, pyinstaller 6.22.3, cryptography 50.0.2, uv 0.13.5, ruff 0.17.2, pytest 9.1.1.
npm: react 19.3.1, vite 8.3.5, @vitejs/plugin-react 6.1.2, typescript latest 7.0.2 (6.0.3 is the newest 6.x), @tanstack/react-query 5.104.5, zustand 5.0.16, react-router 8.5.0, hls.js 1.7.3, tailwindcss 4.3.3, vitest 5.0.5, playwright 1.64.1, openapi-typescript 7.13.0, openapi-fetch 0.17.0, zod 4.6.7, typescript-eslint 8.72.0.
GitHub: MediaMTX latest release v1.21.3 (2026-10-25).

## Sources

- MediaMTX v1.21.3 release notes and assets (`gh api repos/bluenviron/mediamtx/releases`): HIGH
- MediaMTX v1.21.3 `mediamtx.yml` (recordFormat, recordPath `%z`, hook env vars `MTX_PATH`/`MTX_SEGMENT_PATH`/`MTX_SEGMENT_DURATION`, `moq: true` default, auth options): HIGH
- MediaMTX `internal/playback/{server,on_get,on_list}.go` at HEAD: `/list` + `/get` only, `"MPEG-TS format is not supported yet"`, `Accept-Ranges: none`: HIGH
- MediaMTX `api/openapi.yaml` v1.21.3 (`/v3/recordings/list|get|segments/delete`, `RecordingSegment.duration` null for MPEG-TS): HIGH
- https://mediamtx.org/docs/features/record and https://mediamtx.org/docs/features/playback: MEDIUM-HIGH
- PyPI JSON API and npm registry (versions, peer dependencies, Python requirements): HIGH
- https://github.com/pydantic/httpx2 (maintenance rationale): MEDIUM
- https://infoq.com/news/2026/08/typescript-7-released/ and related TS 7 coverage (no stable programmatic API until 7.1): MEDIUM, consistent with the typescript-eslint peer range, which is HIGH
- https://fastapi.tiangolo.com/reference/sse/ (built-in SSE): MEDIUM, exact introducing version unconfirmed
- https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html (JWKS URL, claim checks): HIGH
- Old VMS reference: `python/mediamtx_client.py`, `python/server.py`, `python/ws_discovery_scanner.py`, `python/onvif_*.py`, `mediamtx/mediamtx.yml`: HIGH (read directly)
- `camera_api` `API_REFERENCE.md`, `STREAMING_GUIDE.md` (RTSPS plus Digest, PullPoint mention, recording modes): HIGH
- Not verified, flagged LOW: armv7 wheel availability, Windows hook shell behaviour, WHEP Bearer behaviour on MediaMTX in practice, browser fMP4 progressive playback across Safari and iOS, Dart OpenAPI 3.1 codegen quality.
