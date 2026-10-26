# Project Research Summary

**Project:** VizenLink NVR
**Domain:** LAN NVR/VMS for VizenLink/NuraEye IP cameras. Python + MediaMTX control and media planes, React/TypeScript UI, OpenAPI REST API shared with Flutter. Home (2-8 cameras) and community/small business (8-32, target ~16).
**Researched:** 2026-10-26
**Confidence:** MEDIUM-HIGH overall. Event transport, Windows/macOS hooks, browser codec matrix and packaging are unverified and need spikes.

## Executive Summary

This is a headless recorder with a browser UI. Video bytes never pass through Python. MediaMTX pulls one RTSPS connection per camera stream, records fMP4 segments, and serves live (WHEP, LL-HLS) and playback (`:9996`) directly to clients. Python is the control plane: registry, reconciled MediaMTX state, segment catalog, retention, events, health, auth, and the REST/SSE API.

The core value is "never miss footage." The old VMS fails this many ways: MediaMTX paths lost on restart, `recordDeleteAfter: 1d` deleting footage, an unmounted drive filling the system disk, an index built from a lossy webhook and a rewritten JSON file, anonymous media access, and IP-keyed camera identity. Each has a v1 mechanism: DB-as-truth reconciler, one janitor as the only deleter, a volume-identity guard, a filesystem scanner as index truth, MediaMTX auth bridged to NVR roles, and serial-keyed identity with a re-IP healer. The recorder must be built and soaked headless before any UI ships.

Main risks: (1) No documented NuraEye LAN alert feed exists; ONVIF PullPoint is the only documented LAN event path, which contradicts PROJECT.md's "NuraEye alerts primary." (2) MediaMTX has no pre-roll, so event recording must be "record continuously, protect ranges." (3) Unverified platform behaviour (fMP4 power loss, Windows hook quoting, playback across gaps, multi-NIC WebRTC, H.265 browsers).

## Key Findings

### Recommended Stack

- **Backend:** CPython 3.13 via uv (floor 3.11). FastAPI ~=0.162 (built-in SSE), Uvicorn ~=0.54 with workers=1, Pydantic ~=2.14, SQLAlchemy ~=2.1 + aiosqlite + Alembic (render_as_batch), httpx 0.28.1 behind one wrapper (httpx2 is the successor), PyJWT ~=2.15, pwdlib[argon2], xmltodict for a ported SOAP client, ifaddr, zeroconf. Avoid Celery/Redis/RQ, APScheduler, onvif-zeep, netifaces, passlib, python-jose, SQLModel, ffmpeg-python.
- **MediaMTX v1.21.3** pinned with SHA-256. Generate mediamtx.yml from code. `recordFormat: fmp4`; `recordDeleteAfter: 0s` on every path; `recordPartDuration: 1s`; `recordSegmentDuration: 5m`; `playback: true` on :9996; `authMethod` explicit (see Open Decisions); `apiAddress: 127.0.0.1:9997`; moq/rtmp/srt off; `rtspTransport: tcp`; `sourceFingerprint` per camera; WebRTC interface/additional-host settings from detected LAN IPs.
- **Frontend:** React ^19.3, Vite ^8.3, TypeScript ~6.0.3 (TS 7 lacks a stable programmatic API until 7.1; typescript-eslint caps at <6.1), TanStack Query, Zustand, React Router 8 (one router only), Tailwind 4, shadcn/ui, openapi-typescript + openapi-fetch (TS 6 peer override), zod, d3-scale/d3-time for a canvas timeline.
- **Players:** custom useWhep hook on RTCPeerConnection (~100 lines), hls.js ^1.7 fallback, native video for fMP4, custom canvas timeline. No Video.js/Vidstack.
- **Packaging:** one wheel with backend, migrations and web/dist. Linux: uv tool install + systemd (optional Docker host-network). Windows: PyInstaller onedir + WinSW. macOS: PyInstaller, codesigned/notarized, launchd. Pi 32-bit (armv7) best-effort or dropped.

### Expected Features (FEATURES.md IDs)

- **v1 table stakes:**
  - Onboarding: CAM-01 to CAM-09 (discovery, manual add, credential test with typed reasons, forced default-password change, capability probe, atomic add, profiles, naming, remove with keep/delete).
  - Live: LIVE-01 to LIVE-06 (WebRTC with HLS fallback, 1x1 to 4x4 grid, sub in grid/main on enlarge, honest per-tile state, tile controls, layout memory).
  - Recording: REC-01/02/03/04/06/07/08/09/10/11 (fMP4 segments, modes, schedule, event pre/post-roll, NVR retention, disk-full overwrite-oldest with reserve, DB index with reconciliation, auto-reconnect, audio toggle).
  - Playback: PLAY-01 to PLAY-07, PLAY-09 (timeline with gaps distinct from beyond-retention, day picker, transport, stitching, event jump, MP4 export via stream copy, snapshot).
  - Events: EVT-01 to EVT-06 (persisted event index, list/filters, ingest snapshot, live feed, source health).
  - Settings: SET-01 to SET-06, SET-10 (capability-gated; factory reset admin-only).
  - Auth: AUTH-01 to AUTH-06, AUD-01 (first-run owner, local accounts with lockout, server-side RBAC, per-device tokens, user management, audit log, Simple/Advanced as visibility only).
  - Health: HEALTH-01/02/03/04/05/06/08 (two badges, dashboard, gap detection, storage and horizon, storage failure separate from offline, recorder health, alerts).
  - Gallery/search: GAL-01/02, SRCH-01.
  - Mobile: MOB-01 to MOB-07 (OpenAPI, mDNS plus manual IP, pairing and revocation, relay live, recordings and Range playback, health, permission-gated management).
- **Differentiators cheap in v1:** AUTH-07 data model only, HEALTH-07, HEALTH-09.
- **Defer v1.x:** REC-12/13, SET-07 to 09, SET-13, LIVE-07/08/10, PLAY-08/10/12, EVT-07/08/10, CAM-10/11/13, AUTH-08/09, HEALTH-10 to 12, MOB-08 to 10.
- **Defer v2:** REC-14 (SD back-fill, needs spike), REC-15, EVT-09, AUTH-10, SET-11, HEALTH-14, SRCH-03.
- **Anti-features:** generic ONVIF, NVR-side AI and gender/age search, PTZ, web two-way talk, video wall, remote access, email/SMS/push, expiring share links, motion-pixel triggers, transcoding on ingest, firmware orchestration, camera Wi-Fi provisioning, licensing limits, MFA/SSO in v1, infra dashboards, default accounts.

### Architecture Approach

One asyncio core (API, camera layer, registry, reconciler, catalog/indexer, retention, events, health, auth, export worker, bus) plus a supervisor running MediaMTX and the core as independently restartable children. The data plane never flows through the app server.

1. **Supervisor:** restarts children independently; orphan prevention (Job Object, PDEATHSIG/cgroup, launchd, pidfile).
2. **Camera Layer (camera/):** only ONVIF/NuraEye code. Typed Success/Failure/Timeout. SOAP-fault-first, case-preserving headers, X-VizenLink-Camera-Id check (421 = wrong camera), WSSE digest, per-camera session lock (6-session LRU), narrow per-camera TLS pinning.
3. **Registry:** SQLite, PK = camera serial (thingName); last_host, MAC, fingerprint, profiles, desired mode, cached capabilities; credentials encrypted, never returned.
4. **Reconciler:** diffs desired paths against /v3/config/paths/list; add/patch/delete; at startup, on change, on MediaMTX restart, every 30-60 s. Replaces atexit cleanup.
5. **Catalog + Indexer:** one row per segment (open to complete to deleting), UTC microseconds. Hook helper as accelerator; startup and periodic scan as correctness. Coverage spans to clients; no file paths exposed.
6. **Retention/Disk Manager (sole deleter):** per-camera days and quotas; watermarks and hard reserve max(5 GB, 3%); honours protection ranges and locks; oldest-first under pressure; publishes retention horizon; volume sentinel disables recording with critical alert when missing.
7. **Event Ingest:** per-camera task behind EventSource; v1 adapter ONVIF PullPoint; normalize, debounce, raw_json, snapshot, protection range; linker is a read-time pure function.
8. **Health:** per-camera states: recording, online_not_recording, connecting, offline, auth_failed, tls_changed, identity_mismatch, privacy, disabled. Recording-age watchdog is the key signal.
9. **Auth:** Argon2id, hashed opaque sessions with rotating refresh, roles to permissions table, require(permission) on each route. Media tokens scoped {action, path, exp}. Cognito identity-only, never on login or recording path.
10. **API /api/v1:** OpenAPI 3.1 committed and diffed in CI; problem+json; SSE; cursor pagination; jobs for long operations.
11. **Export worker:** /get?format=mp4 to temp then rename; leases; bounded concurrency.

### Critical Pitfalls

1. **State only in MediaMTX/browser:** DB is truth; reconciler at boot and every 30 s; treat paths/add 400 as an error to inspect. (P1, P3)
2. **MediaMTX deletes footage (recordDeleteAfter 1d in old config):** set 0s on every path; one deleter; test. (P3)
3. **Live OK while recording dead:** separate recording state; stall = no segment within 2x duration plus grace; volume sentinel; free-space checks on recordings volume; measured bytes/hour. (P3, P9)
4. **Webhook plus JSON index:** SQLite single writer and Alembic from day one; scanner is correctness; no remux in request path; index spans. (P3)
5. **Power-loss corruption:** fMP4, 1 s parts, no post-remux; startup sweep marks damaged tails; no exFAT/FAT; 10 hard kills. (P1 spike, P3)
6. **Anonymous MediaMTX exposure:** no any-user; authMethod bridged; API on loopback; RTMP/SRT off; unauthenticated ffprobe must fail. (P1 default-deny; P4 bridge; nothing to LAN before P4)
7. **Timestamp/DST errors:** UTC microseconds; NVR clock authoritative; re-stamp events when camera clock uncertain; tz library; DST tests. (P1, P3)
8. **Reconnect gaps hidden:** per-camera states; re-resolve URIs before reconnect; rediscover by serial; timeline shows gap distinctly. (P2, P3, P7)
9. **Contract drift with Dart camera_api:** contract matrix; generated models; golden fixtures; behaviours as tests; camera_api changes need owner sign-off. (P1, P2)
10. **Multiview/WebRTC load:** sub streams in tiles; pause off-screen; audio off in grid; HLS audio; interface config; TCP fallback; relative media URLs. (P4)

Also: H.265 is not browser-playable everywhere (camera is H.264 only; capability message); SD wear (USB SSD for recordings); Windows hook/path issues.

## Implications for Roadmap

Phase 3 ships headless before phase 4 exposes anything. Phases 4 and 5 may run in parallel after phase 3.

### Phase 1: Foundations and Secure Process Model
- **Delivers:** repo, uv/Python 3.13, typed settings, SQLite WAL + Alembic, bus, supervisor skeleton, pinned default-deny MediaMTX config, UTC time model, secrets and static-serving rules, contract matrix and fixtures, CI on Linux/macOS/Windows.
- **Avoids:** P1, P2, P6 (config), P7 (time), P9, P10, P14, P20, P21.
- **Spikes:** 24 h recording on one real camera; 10 hard-kill test; MediaMTX restart with API paths; %s vs %z.

### Phase 2: Camera Layer and Onboarding
- **Delivers:** camera/ package (result type, connection, WSSE, sessions, SOAP faults, capabilities, identity check, snapshot, live-URI resolution, ONVIF device/media); WS-Discovery on ifaddr; manual add; typed credential test; 428 flow; TOFU fingerprint with tls_changed; serial registry; simulator; behaviors.yaml and lock file.
- **Addresses:** CAM-01 to CAM-09, CAM-13 basic, SET-01 read.
- **Avoids:** P8, P14, P15, P16, P17.
- **Research: needed.** PullPoint and Search payloads on hardware; case-preserving HTTP client; WSSE clock-skew tolerance; non-admin streaming account; RTSP with WEBRTC_STREAMING on.

### Phase 3: Recording Core, Headless (Core Value slice)
- **Delivers:** Registry + Reconciler to MediaMTX paths (cam/<serial>/main recording, cam/<serial>/sub on demand); modes (continuous; scheduled via record toggles at window boundaries; event as always-record plus protection ranges); catalog + indexer (hook + scanner); janitor (days/size, watermarks, reserve, protection, sentinel); recovery sweep; gap watchdog; health state machine; storage probe.
- **Addresses:** REC-01/02/03/06/07/08/09/10/11; HEALTH-01/03/04/05/06/08.
- **Avoids:** P1 to P6, P8, P13 (no start/stop pre-roll), P22, P24, P25.
- **Spikes:** %s token in playback lookup; Windows/macOS hook quoting (helper executable); /get across gaps; slow USB disk; janitor-only deletion test.

### Phase 4: API v1, Auth, Media Tokens, Live View, Web Shell
- **Delivers:** local accounts and roles; permission dependencies; authMethod bridge; media-token issuer with make-before-break renewal near 80% TTL; /api/v1 cameras/recording/live/system/users; problem+json; SSE; OpenAPI diffed in CI; React shell with generated client; useWhep; hls.js; grid on sub with off-screen pause; Simple/Advanced toggle (visibility only); audit log; scope data model.
- **Addresses:** LIVE-01 to 06; AUTH-01 to 06; AUD-01; MOB-01 skeleton; HEALTH-02.
- **Avoids:** P9, P10, P11, P18, P19.
- **Spikes:** jwt vs http; renewal; multi-NIC WebRTC with UDP blocked; H.265 matrix.

### Phase 5: Events and Event-to-Recording Linking
- **Delivers:** EventSource interface; ONVIF PullPoint adapter (create, pull with clamped timeouts, renew, recreate on 404); SetEventPreferences; normalizer and debounce; camera-clock vs receive-time handling; snapshot at ingest; protection ranges with pre/post-roll at read time; source health and watchdog; findEvents backfill after reconnect; polled state changes as events; list, filters, live feed.
- **Addresses:** EVT-01 to 06; REC-04; REC-05; PLAY-05 link data; SET-08 warning.
- **Avoids:** P13, P7.
- **Research: needed, highest priority.** Confirm with firmware owner whether a NuraEye LAN feed exists; 24 h PullPoint capture; power-cycle test; rates and overflow.

### Phase 6: Camera Settings Proxy
- **Delivers:** settings groups (identity, encoder, imaging, OSD, reboot, admin-gated factory reset, health, masks, event preferences, response actions), all capability-generated; per-camera bulk results.
- **Addresses:** SET-01 to 06, SET-10.
- **Avoids:** P27, P16, role confusion.
- **Standard pattern** (SETTINGS_API_GUIDE).

### Phase 7: Playback, Timeline, Export, Gallery
- **Delivers:** canvas timeline from spans and events; day picker; one /get per contiguous span (fmp4; seek = new request); event jump; export job (mp4, temp then rename, leases, ffprobe check); snapshot; gallery; search.
- **Addresses:** PLAY-01 to 07, PLAY-09; GAL-01/02; SRCH-01.
- **Avoids:** P6, P13, P23, P7 (DST).
- **Depends on phase 3 spike.** Seek without range support; Safari/iOS fMP4; Flutter video_player with mp4.

### Phase 8: Mobile Integration Hardening
- **Delivers:** oasdiff CI gate; Dart client (spike) or thin dio client; mDNS with api_version TXT; pairing and revocation; SSE to mobile; RecordingsList-shaped view (decided with mobile owner); permission-gated management; playback path decision.
- **Addresses:** MOB-01 to 08.
- **Avoids:** P14, P11.
- **Research: moderate.** Dart OpenAPI 3.1 (LOW); mobile TLS; Cognito timing.

### Phase 9: Packaging, Services, Soak
- **Delivers:** systemd/launchd/WinSW installers; pinned MediaMTX per OS/arch; wheel with web/dist; PyInstaller smoke tests; upgrade and DB backup/restore; volume guard per platform; sleep prevention; firewall docs; 16-camera soak with 2 viewers; hardware matrix (Pi with USB SSD, Jetson, PC, Windows, macOS).
- **Avoids:** P3, P19, P20, P21, P22; "looks done but isn't" checklist.
- **Research: needed.** WinSW vs pywin32; Pi/Jetson at 16; USB hot-unplug; notarization; AV exclusions.

**Ordering rationale:** recording before UI; auth lands with first data API (nothing to LAN before phase 4); events independent of UI; playback needs catalog, tokens and event links; mobile API freezes late.

**Standard patterns (skip research-phase):** Phase 1 except MediaMTX config spikes; Phase 6.

## Reconciliation of Cross-Researcher Points

1. **Event source (conflict with PROJECT.md):** PROJECT.md says "NuraEye alerts primary, ONVIF fallback." STACK and ARCHITECTURE found no documented NuraEye LAN feed (NuraEye alerts go over AWS IoT MQTT, WAN only; the REST API configures rules only). Recommend: EventSource interface, ONVIF PullPoint as v1 adapter, reserved NuraEye LAN slot. Open question for the firmware owner; update PROJECT.md and REC-05 once confirmed.
2. **Event recording:** MediaMTX has no pre-roll. Record continuously and protect ranges; pre/post-roll at read time (REC-04 staging; ARCHITECTURE Pattern 3).
3. **MediaMTX auth:** STACK says authMethod http (per-action callback; one credential everywhere). ARCHITECTURE says jwt (local verification survives core restart; sessions close on JWT expiry in v1.21.3). Spike both in phase 4. Anonymous access never allowed.
4. **Recording format:** fMP4, 1 s parts, 5 m segments, recordDeleteAfter 0s, NVR owns retention. FEATURES.md still mentions mpegts in REC-01 and PLAY-04; superseded, update requirements. recordPath token: %z (STACK) vs %s (PITFALLS, ARCHITECTURE); spike in phase 3.
5. **Old-VMS security issues:** informational, not v1 scope. Plaintext credentials, static serving of project dir, path traversal on delete, debug=True on 0.0.0.0, shell=True openssl, * CORS, anonymous MediaMTX. The v1 replacements are already in the requirements above.
6. **Cognito timing:** PROJECT.md Active (v1) vs FEATURES AUTH-09 (v1.x). Recommend: identity model and cognito_sub column in v1; link in v1.x unless owner says v1.

## Open Decisions

1. Event source (owner: firmware; needed before phase 5).
2. authMethod http vs jwt (spike, phase 4).
3. recordPath %z vs %s (spike, phase 3).
4. Cognito link in v1 or v1.x (owner).
5. Mobile TLS posture (decide phase 1 origin strategy; finalise phase 8).
6. Default recording profile and retention in onboarding: 4 Mbps x 16 cameras is about 690 GB/day; dedicated recording disk required for 8+ cameras.

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | MEDIUM-HIGH | Versions verified against registries and MediaMTX v1.21.3 source (HIGH); packaging, Windows hooks, armv7, Dart codegen MEDIUM/LOW |
| Features | MEDIUM-HIGH | Internal sources HIGH; competitor behaviour MEDIUM; seed docs are drafts |
| Architecture | MEDIUM-HIGH | MediaMTX HIGH; camera contracts HIGH as written but several "build-verified, not hardware-verified" |
| Pitfalls | MEDIUM-HIGH | Old-VMS findings HIGH; [exp] items need validation |

**Overall: MEDIUM-HIGH.** Three items could change the roadmap: event source, auth mode, playback across gaps.

### Gaps to Address

- **Event source (critical):** ONVIF PullPoint behind EventSource; firmware owner confirmation before phase 5; PullPoint on hardware.
- **RTSPS concurrency:** verified 2 clients per stream (partial, FR-CF-153); PITFALLS rates LOW. One upstream per stream; test 3 clients in phase 2.
- **Playback across gaps and seeks:** Accept-Ranges none; spike phase 3; self-built HLS VOD as fallback.
- **Windows/macOS hooks:** unverified; scanner is correctness; helper executable, never shell strings.
- **fMP4 power loss:** documented, not measured on this camera; soak and hard-kill tests.
- **WebRTC:** multi-NIC, UDP blocked, load at 16 sessions; phase 4 spike; HLS fallback.
- **H.265:** camera H.264 only; capability message; browser matrix in phase 4.
- **Camera clock:** no RTC; NVR clock authoritative; re-stamp when uncertain.
- **Hardware sizing:** Pi 4/5 with SSD floor for ~8; 16 unmeasured; measure in phase 9.
- **Dart OpenAPI codegen:** LOW; spike before phase 8 or hand-write a thin client.
- **event-metadata-schema is a draft:** align with mobile owner; store raw_json.

## Sources

- **Primary (HIGH):** MediaMTX v1.21.3 release, mediamtx.yml, api/openapi.yaml; MediaMTX docs (record, playback, authentication, control-api, webrtc-specific-features, hls, webrtc); MediaMTX internal/playback source; camera_api contracts (API_REFERENCE, SETTINGS_API_GUIDE, STREAMING_GUIDE, test/); camera design docs (Camera-REST-API.openapi.yaml, Camera-ONVIF-API.md, FR-vms.md, FR-camera-firmware.md, FR-onvif-stack.md, docs/external-api); old VMS (server.py, mediamtx_client.py, ws_discovery_scanner.py, main.py, mediamtx.yml, nuraeye_user_data.json); PyPI/npm data 2026-10-26; AWS Cognito JWT verification guide; PROJECT.md.
- **Secondary (MEDIUM):** Frigate record/export docs; Moonfire NVR schema guide; Synology and UniFi Protect docs; httpx2 repo; TypeScript 7 coverage; FastAPI SSE reference; seed document and vms-* scenarios (drafts).
- **Tertiary (LOW):** MediaMTX issue #4188 (H.265 duration, one report); Windows hook quoting, Pi throttling, hvc1, PullPoint expiry (`[exp]`); armv7 wheels; Dart OpenAPI codegen; per-platform HEVC support.

---
*Research completed: 2026-10-26*
*Ready for roadmap: yes (event source defaults to ONVIF PullPoint pending firmware-owner confirmation)*
