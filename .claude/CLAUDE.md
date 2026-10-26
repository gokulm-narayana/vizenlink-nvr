<!-- GSD:project-start source:PROJECT.md -->

## Project

**VizenLink NVR**

A rebuild of the existing VizenLink/NuraEye VMS (`nuraeye-rt/vms`) as a network video recorder that records, plays back and manages VizenLink/NuraEye cameras on the local network. It keeps the proven Python + MediaMTX recording approach, replaces the AngularJS web UI with a modern one, and aligns all camera behaviour with the shared `camera_api` contracts so the NVR and the VizenLink mobile app behave identically with the same camera. It serves both home users (2–8 cameras, simple UX) and communities/small businesses (8–32 cameras, guard/manager operators) from one product with tiered views and roles.

**Core Value:** **Never miss footage** — every added camera records reliably 24/7 (plus events), and that footage is always findable on a timeline from both the web UI and the mobile app.

### Constraints

- **Tech stack (backend)**: Python + MediaMTX — keeps proven recording path and runs on all target hardware
- **Tech stack (frontend)**: React + TypeScript (Vite) — best ecosystem for video grids, timeline scrubbing, WebRTC/HLS players
- **Platform**: Platform-independent Python for all non-AI features; hardware not yet decided (Pi, Jetson, Linux PC, Windows/macOS all possible)
- **Network**: LAN only for v1
- **Compatibility**: Camera behaviour must match `camera_api` contracts; changes to `camera_api` itself require explicit owner confirmation
- **Cameras**: VizenLink/NuraEye only
- **Scale**: ~16 cameras target on mid-range hardware

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Headline decisions (read this first)

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

### Background work

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| asyncio tasks + anyio TaskGroup in the FastAPI `lifespan` | stdlib / anyio | MediaMTX supervisor, per-camera health ping, per-camera ONVIF PullPoint loop, segment indexer/reconciler, retention sweeper, recording-mode scheduler, mDNS announce | One loop, no broker, trivially portable. A 30 s tick loop that evaluates schedules and PATCHes `record` is simpler and more testable than a scheduler library. | HIGH |
| `asyncio.to_thread` / `ProcessPoolExecutor` | stdlib | Rare CPU or blocking work (thumbnails, MP4 header parsing) | Keeps loop responsive. | HIGH |
| psutil | `~=7.2` | Disk, CPU, memory, temperature for the health endpoint | Cross-platform wheels. Use `shutil.disk_usage` for free-space checks on the recordings volume. | HIGH |

### Media plane: MediaMTX

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **MediaMTX** | **v1.21.3** (2026-10-25). Pin the exact version and verify the SHA-256 from `checksums.sha256`. | RTSP(S) ingest from cameras, relay (RTSP/WebRTC/HLS), fMP4 recording, playback server | Release assets exist for darwin amd64/arm64, linux amd64/arm64/armv6/armv7 and windows amd64, covering every target. v1.21.x adds `duration` to fMP4 segments, fixes `recordPath` timezone handling and recorder timestamp discontinuities, and ends sessions when a JWT expires. Ten-plus releases since 2026-04 means a fast cadence, so pin and upgrade deliberately. | HIGH |
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

### Camera protocols (ONVIF, NuraEye, discovery)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **Port the existing hand-rolled SOAP client** (`onvif_http_client.py`, `onvif_utils.py`, `onvif_*_service.py`, `nuraeye_http_client.py`) onto `httpx` + `xmltodict` | `xmltodict ~=1.0` | ONVIF Device/Media/Imaging/Analytics and NuraEye `/nuraeye/*` REST | The old code already implements WS-UsernameToken digest (nonce + created), self-signed TLS handling and the exact service subset VizenLink cameras need, and it is what `camera_api` was validated against. A generic ONVIF library adds a WSDL parse cost, large memory and PyInstaller data-file pain for no feature gain, since third-party cameras are out of scope for v1. Make it async, add typed Pydantic results, and add a `Result[T, CameraError]` shape matching `camera_api`'s `CameraResult`. | MEDIUM-HIGH |
| ONVIF events | same client, new module | PullPoint: `CreatePullPointSubscription`, `PullMessages`, `Renew`, `Unsubscribe` | Needed as the LAN event path (camera notes say `EventMgr_Send()` also delivers via ONVIF PullPoint). One asyncio task per camera with long-poll `PullMessages` plus renew and resubscribe on failure. **There is no PullPoint code in the old repo** (only `onvif_analytics_service.py`), so this is new work and the first thing to spike on a real camera. | MEDIUM |
| WS-Discovery | **port `ws_discovery_scanner.py`** (raw UDP multicast `239.255.255.250:3702`, Probe with custom `namespace`/`local_name`) | Find VizenLink/NuraEye cameras | The scanner already does per-interface multicast plus unicast receive and VizenLink-specific type filtering. Replace the abandoned `netifaces` (last release 2021-05) with **`ifaddr`** (pure Python, no compile; already a transitive dependency of `zeroconf`). | MEDIUM-HIGH |
| ifaddr | `~=0.2` | Enumerate NICs and IPs for multicast joins | Pure Python, works on all targets. | HIGH |
| zeroconf | `~=0.151` | Advertise the NVR as `_vizenlink-nvr._tcp.local.` | Lets the Flutter app auto-find the NVR on the LAN (mobile side uses `nsd` or `multicast_dns`). Cheap, and removes manual IP entry. | MEDIUM |

### Authentication and authorization

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyJWT (`pyjwt[crypto]`) | `~=2.15` | Issue and verify NVR tokens; verify Cognito RS256 tokens | `PyJWKClient` handles JWKS fetch, caching by `kid` and key rotation. `[crypto]` pulls `cryptography` 50.x. | HIGH |
| pwdlib (`pwdlib[argon2]`) | `~=0.3` | Password hashing | Argon2id, the FastAPI-documented replacement for passlib. Tune memory and time cost down on Pi-class CPUs and benchmark login latency. Do not use passlib (unmaintained). | HIGH (library), MEDIUM (tuning) |
| Local accounts + roles | in DB | Owner/Admin, Operator, Viewer | RBAC enforced by a FastAPI dependency (`require_role(...)`) on every route, with per-camera ACLs deferred. | HIGH |

### API contract and realtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| OpenAPI 3.1 from FastAPI (checked into `api/openapi.json` in CI) | n/a | The documented REST contract for web and Flutter | Single source of truth. Fail CI on unreviewed drift. Design resource-style REST (`GET /cameras`, `PATCH /cameras/{id}/recording`, `GET /cameras/{id}/recordings?from&to`) instead of the old `POST /api/vms/*` RPC with a `{success,data\|error}` envelope. Use HTTP status plus an RFC 9457-style error body, and keep camera-setting payloads and capability flags identical to `camera_api` semantics. | HIGH (mechanism), MEDIUM (style choice) |
| Server-Sent Events (`fastapi.sse`) | built in | Push of camera online state, events/alerts, recording state, disk warnings to web and Flutter | One-way push is all that is needed. SSE reconnects natively in browsers and is trivial from Dart's HTTP client. Prefer SSE over WebSocket here. Use WebSocket only if a bidirectional feature appears. | MEDIUM |
| orjson | `~=3.13` | Faster JSON for large list endpoints | Optional. Add only if profiling demands. | MEDIUM |

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

### Packaging and distribution

| Target | Method | Tooling | Confidence |
|--------|--------|---------|------------|
| **Single deliverable** | One Python wheel containing the backend, migrations and the built `web/dist` (served via `StaticFiles`). The backend downloads or locates the pinned MediaMTX binary for its platform, verified by SHA-256 against a checksum list shipped in the wheel. | `uv build`, `hatchling` | MEDIUM |
| Linux x86_64 and arm64 (Raspberry Pi 64-bit, Jetson, PC) | **Install script + systemd unit** using `uv tool install` (uv fetches CPython 3.13, which makes JetPack 6's Python 3.10 irrelevant). Also publish a **multi-arch Docker image** (`linux/amd64`, `linux/arm64`) with `network_mode: host`. | uv, Docker buildx | MEDIUM |
| Raspberry Pi 32-bit (armv7) | Treat as best-effort. `cryptography` and `argon2-cffi` wheels for armv7 are not verified. Recommend 64-bit Pi OS and drop armv7 from v1 unless a customer requires it. | | LOW |
| Windows x64 | **PyInstaller `--onedir`** bundle with MediaMTX `windows_amd64` bundled, wrapped in an installer (Inno Setup) that registers a Windows service (WinSW 3.x, not NSSM which is unmaintained) and opens firewall rules for 8554/8889/8189/8888/9996. | PyInstaller 6.22, Inno Setup, WinSW | MEDIUM-LOW |
| macOS arm64 / x86_64 | PyInstaller `--onedir` + MediaMTX darwin build, **codesigned and notarized** (Developer ID), launched via a `launchd` agent. macOS "Local Network" privacy prompts affect WS-Discovery multicast. | PyInstaller, `codesign`, `notarytool` | MEDIUM-LOW |
| CI | GitHub Actions matrix on native runners (PyInstaller cannot cross-compile): ubuntu x64, ubuntu arm64, windows, macOS arm64 (+ Intel runner if still needed). | | MEDIUM |

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

# --- Backend (Python 3.13 via uv) ---

# --- MediaMTX (pinned, verify checksum) ---

# https://github.com/bluenviron/mediamtx/releases/tag/v1.21.3

#   mediamtx_v1.21.3_{linux_amd64,linux_arm64,darwin_arm64,darwin_amd64,windows_amd64}

# --- Web UI (Node 24 LTS+) ---

# openapi-typescript peer dep is typescript ^5.x: add an "overrides" entry for TS 6 and verify in CI.

## Version verification log (2026-10-26)

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

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

## Session Handoff (multiple Claude accounts)

This project is worked on from several Claude accounts and sessions, which share no chat history. The repo is the only memory.

- **At the start of every session**, before doing anything else, read `.planning/handoff/LATEST.md`, then `.planning/STATE.md`. If a `.continue-here.md` exists under `.planning/`, use `/gsd-resume-work`.
- **When the user says "write handoff"** (or is about to switch accounts or stop), write `.planning/handoff/log/<YYYY-MM-DD-HHMM>-<slug>.md` using the template in `.planning/handoff/README.md`, copy it over `LATEST.md`, and commit it as `docs(handoff): <slug>`.
- Record the *why* behind decisions in the handoff, not just the *what*. The next session can't ask you.

## Related Codebases (read-only reference)

- **Old VMS** — `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/vms`: Flask + AngularJS + MediaMTX. Port logic from it only where it matches `camera_api`; do not carry over its known defects (see `.planning/research/PITFALLS.md`): IP-keyed cameras, `segments.json` index, `atexit` path deletion, `recordDeleteAfter: 1d`, anonymous MediaMTX, `debug=True`, static serving of the project dir.
- **Camera API contracts** — `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api` (`API_REFERENCE.md`, `SETTINGS_API_GUIDE.md`, `STREAMING_GUIDE.md`), plus `auth_api` and `alerts_api` alongside it. These Dart packages define camera behaviour; the Python camera layer mirrors them.
- **Mobile app** — `/Users/gokul/mobilecctvapp` (Flutter). Consumes the NVR's `/api/v1` over LAN in Phase 7.

## Project Rules

- **`camera_api` is the source of truth for camera behaviour.** Never modify anything under `nuraeye-rt/mobile_app/packages/**` or `mobilecctvapp/packages/**` without the user's explicit confirmation. If the NVR needs camera behaviour the contracts don't cover, stop and ask.
- **Never touch the old VMS or mobile app repos** from this project unless the user asks — they are reference only.
- **Core value is "never miss footage".** The NVR retention janitor is the only component that deletes recordings; MediaMTX runs with `recordDeleteAfter: 0s`. The SQLite DB is the source of truth; MediaMTX paths are reconciled from it.
- **Nothing is exposed to the LAN without auth** (API and media). Phases 1–2 are loopback/CLI only.
- **Time:** store UTC; NVR clock is authoritative; display in the site IANA time zone.
- **Scope (v1):** LAN only, VizenLink/NuraEye cameras only, no AI in the core. Event source is ONVIF PullPoint behind an `EventSource` interface until the firmware owner confirms a NuraEye LAN feed.
- Stack: Python 3.13 (uv) + FastAPI + SQLite/Alembic + MediaMTX v1.21.3 (fMP4); React 19 + TypeScript ~6.0 + Vite. See `.planning/research/STACK.md`.
