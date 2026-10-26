# Pitfalls Research

**Domain:** LAN network video recorder (NVR/VMS) for VizenLink/NuraEye IP cameras. Python + MediaMTX backend on Pi / Jetson / Linux PC / Windows / macOS, React + TypeScript web UI, REST API consumed by a Flutter app on the LAN.
**Researched:** 2026-10-26
**Confidence:** MEDIUM-HIGH. Findings tagged `[code]` were verified by reading the old VMS source or the `camera_api` guides. Findings tagged `[docs]` were verified against mediamtx.org. Findings tagged `[exp]` come from general NVR and embedded-camera experience, or could not be confirmed from docs, and need a hardware or platform spike before the design relies on them.

**Inputs read:**
- `/Users/gokul/Desktop/Vizenlink_Vms/.planning/PROJECT.md`
- Old VMS: `vms/python/mediamtx_client.py`, `vms/python/server.py`, `vms/main.py`, `vms/mediamtx/mediamtx.yml`, `vms/app_data/nuraeye_user_data.json`
- `camera_api`: `STREAMING_GUIDE.md`, `SETTINGS_API_GUIDE.md`, `API_REFERENCE.md`, `test/` directory
- mediamtx.org pages on recording, playback, authentication, control API, WebRTC and HLS

**Provisional phase vocabulary.** The roadmapper may rename these. Every pitfall below maps to one of them.

| Tag | Phase |
|-----|-------|
| P1 | Foundations: repo, process supervision, DB schema, config, time model, camera identity, contract-test harness |
| P2 | Camera layer: Python mirror of `camera_api` (auth, discovery, capabilities, stream resolution) and onboarding |
| P3 | Recording engine: MediaMTX control plane, segment index, retention, storage health |
| P4 | Live view and multiview (web) |
| P5 | Timeline playback and export |
| P6 | Events, alerts and event-to-footage linking |
| P7 | Auth, roles and the REST API for mobile |
| P8 | Camera settings (capability-driven) |
| P9 | Packaging, cross-platform services, hardening |

---

## Critical Pitfalls

These cause silent footage loss (the Core Value), a security breach, or a rewrite.

### Pitfall 1: Recording state lives only in MediaMTX memory and in the browser

**What goes wrong:** Cameras are added to MediaMTX through the Control API (`/v3/config/paths/add`). The NVR has no server-side desired-state store that it reconciles against MediaMTX. After a MediaMTX or Python restart, a reboot, or a power blip, nothing re-registers the paths. Recording stops while the box looks "up".

**Why it happens:** The old VMS does exactly this `[code]`:
- `MediaMTXClient` keeps `registered_cameras` as an in-memory set, and an `atexit` hook deletes every path on exit.
- Camera registration is a UI-driven POST (`/api/vms/camera/register` with `camera_info` from the browser). A grep of `server.py` found no startup reconciliation.
- Per-camera recording mode is saved in `nuraeye_user_data.json`, but nothing replays it into MediaMTX at boot.
- The MediaMTX docs page on the control API does not say whether API-added paths are persisted to the config file `[docs]`. Assume they are not.

**How to avoid:**
- The NVR database is the source of truth: cameras, profile, desired recording mode, and the resolved RTSP source.
- Write a reconciler loop in the NVR. It runs at boot and every ~30 s. It diffs the DB against `GET /v3/config/paths/list` and `GET /v3/paths/list`, then adds, patches or removes paths so MediaMTX matches. It never mutates MediaMTX from request handlers except through this one module.
- Run MediaMTX as its own supervised service, independent of the Python process. Python crashing or restarting must not stop recording.
- Treat HTTP 400 from `paths/add` as "exists, so PATCH". Do not treat it as success blindly, because the old code swallows real validation errors as "already registered" `[code]`.

**Warning signs:**
- A recording gap that begins exactly at a reboot or deploy.
- A camera "added" in the UI but absent from `paths/list`.
- Recording that only works while someone has the web UI open.

**Phase to address:** P1 (supervision, DB as truth) and P3 (reconciler).

---

### Pitfall 2: MediaMTX's own retention silently deletes footage (`recordDeleteAfter: 1d`)

**What goes wrong:** The shipped `mediamtx.yml` has `pathDefaults.recordDeleteAfter: 1d` `[code]`. Per the MediaMTX docs, MediaMTX deletes segments after that timespan unless it is set to `0s` `[docs]`. The old user data advertises `retentionDays: 7`, but no code enforces it (grep for retention, `disk_usage` and `statvfs` found nothing). The UI would promise 7 days while MediaMTX removes footage at 1 day, or, if the file extension doesn't match MediaMTX's cleaner, nothing is ever deleted.

**Why it happens:** Two deleters with different policies, plus a settings screen that is cosmetic (`diskMinThreshold: 90`, `enableOverwrite: true` have no enforcement).

**How to avoid:**
- Set `recordDeleteAfter: 0s` explicitly on every path the NVR creates. Pin it in a config test.
- Own retention in exactly one place, the NVR janitor (see Pitfall 6).
- Add an integration test that records for N minutes with a tiny retention and asserts the janitor, not MediaMTX, deleted the files.

**Warning signs:** Footage older than 24 h is missing while the UI says retention is longer. Files vanish with no NVR log entry.

**Phase to address:** P3.

---

### Pitfall 3: "Live looks fine" while recording is dead (disk full, slow disk, wrong mount)

**What goes wrong:** The relay and live view keep working while the recorder fails. Live view is not evidence of recording. Failure modes:
- **Disk full or write error.** Recording stops. The path stays "ready".
- **Recorder falls behind.** On a slow SD card or USB stick the recorder's write queue overflows and frames are dropped. MediaMTX's `writeQueueSize` is 512 in the old config `[code]`. This one is `[exp]`: confirm the log text and behaviour in a spike.
- **Missing mount.** An external drive is unplugged and the recordings path becomes a plain directory on the root filesystem, which fills the Pi's SD card. The old code even has a `# TODO: detect external hard drive` `[code]`.
- **No pre-flight check.** The old `diskMinThreshold` and `enableOverwrite` have no enforcement.

**Why it happens:** Teams measure "stream up" and not "bytes landing". The success metric is "zero recording gaps", but nothing measures it.

**How to avoid:**
- Recording health is a first-class state per camera, separate from stream health. A camera has two independent states: `stream: ready/not` and `recording: healthy/stalled`.
  - Define `recording: stalled` as no segment completed or grown within `2 × segmentDuration + grace`.
  - Source the signal from the segment index plus filesystem mtime/size checks, not only hook callbacks.
- Volume identity guard: write a `.nvr-volume-id` marker file on the recordings volume. Refuse to record, and raise a loud health error, if the marker is missing or the volume is not the expected mount.
- Free-space watermarks on the recordings volume: `shutil.disk_usage(recordings_root)`, not the system drive. Evaluate free bytes, with a hard reserve of `max(5%, N GB)`. The janitor deletes oldest-first across cameras before the reserve is breached (see Pitfall 6). If it cannot free space (everything is protected or locked), surface "storage full, recording at risk" at the top of the UI.
- Capacity estimator in onboarding and settings, driven by measured bytes/hour per camera, not nominal bitrate. Rough envelope: 16 cameras at 4 Mbps is about 29 GB/hour, about 690 GB/day.
- Raise `writeQueueSize` only after measuring, and parse MediaMTX logs for "too slow" or "queue full" style errors into a health counter `[exp]`.

**Warning signs:** `recording` health lags `stream` health. Segment sizes shrink. Free space reaches 0 with no alert. Files appear on the system disk.

**Phase to address:** P3 (health model, guards, janitor), P9 (per-platform mount detection).

---

### Pitfall 4: Segment index built from webhooks and a rewritten JSON file

**What goes wrong:** Footage exists on disk but is not findable on the timeline, or the index is corrupted or lost. Findable footage is the Core Value.

**Why it happens:** The old design `[code]`:
- `runOnRecordSegmentComplete` fires `curl` to Flask. The `curl` has `--max-time 5`, while the handler runs a blocking `ffmpeg` remux with a 100 MB probesize, so slow remuxes outlive the caller.
- The handler appends to a per-camera `segments.json` by reading the whole file, appending and rewriting it. There is no lock, so concurrent webhooks race. The file grows without bound. A corrupt file is silently reset to `[]` (`except JSONDecodeError: segments = []`), which wipes the index.
- If the NVR is down or restarting when a segment completes, the hook is lost and the segment is never indexed.
- `event` mode records into `clips/`, which the handler deliberately does not index. Event-mode footage is recorded but invisible on the timeline `[code]`.
- After an NVR restart all cameras start together, so segment rotations align and the 100 MB-probesize remux runs for all cameras at the same instant (thundering herd) `[exp]`.

**How to avoid:**
- SQLite (WAL mode, a single writer thread/queue) with schema migrations from day one. The installed base lives on user hardware, so Alembic or an equivalent is needed from the first release.
- The filesystem is the truth and the DB is a rebuildable index:
  - A scanner indexes any `.mp4` file it has not seen. Run it at startup, after each hook, and periodically. Hooks only accelerate; they are never required for correctness.
  - Mark the newest segment as "open" until a later segment exists, or until size has been stable for 2 × part duration.
- Do not remux in the request path. If any post-processing is needed, use a bounded worker queue with one or two workers, low priority, plus a startup sweep for unprocessed leftovers.
- Index spans, not just files: store `(camera_id, start_utc_ms, end_utc_ms, path, size, state)`. Serve coverage "spans" to clients, not a per-segment list. At 16 cameras × 288 segments/day × 30 days the list is about 138k rows.
- Unit-test the scanner with deleted, truncated and zero-byte files.

**Warning signs:** Footage on disk but missing from the timeline. The row count differs from the file count. Index-rebuild is a manual step.

**Phase to address:** P3.

---

### Pitfall 5: Segment corruption on power loss, and the remux-on-complete band-aid

**What goes wrong:** A power cut mid-write leaves a truncated or unplayable newest segment per camera. In the old pipeline the dangerous window is wider: MediaMTX writes MPEG-TS, then ffmpeg remuxes to MP4 and deletes the TS only on success `[code]`. A power cut during remux leaves a partial `.mp4` plus a TS that is never retried, because there is no startup sweep.

**Why it happens:**
- Plain (non-fragmented) MP4 written by a killed process has no `moov` atom and is unreadable `[exp]`. MPEG-TS is more tolerant but is not browser-playable `[exp]`.
- The old code remuxed to MP4 "to resolve blank video issues" and wrong durations, from RTSP timestamp problems `[code]`. This pushes work onto the critical path and doubles disk writes.
- The MediaMTX docs state: with fMP4, when a failure occurs the last *part* is lost, so `recordPartDuration` is effectively the recovery point objective `[docs]`.
- A reported MediaMTX bug (issue #4188, v1.11.1, H.265 segments) showed reported duration growing while actual frames did not `[exp]`. Don't trust segment duration metadata, and measure it.

**How to avoid:**
- Record fMP4 (MediaMTX default, supports H.264 and H.265) with `recordPartDuration: 1s` and **no post-remux**. Use the MediaMTX playback server (`/list`, `/get`, `format=mp4`) or an on-demand remux only for export `[docs]`.
- Startup recovery: for each camera's newest N segments, `ffprobe` them. Truncate or quarantine unreadable tails and set the index row to `damaged` (still shown on the timeline, with a marker).
- Use a journaling filesystem (ext4/NTFS/APFS). Recommend against exFAT/FAT for recordings. A hot-unplugged USB drive is a power loss.
- Do not rely on camera-supplied durations. Compute span end from the last good part.
- Spike early: record 24 h from a real camera, hard-kill the host mid-write 10 times, and assert that at most the last `recordPartDuration` is lost and the file plays.

**Warning signs:** Zero-length or tiny files after reboots. ffprobe errors on the newest segment. Playback that stalls at the end of a segment.

**Phase to address:** P3 (format choice, recovery sweep) and P1 (spike on real hardware).

---

### Pitfall 6: Retention deletion races

**What goes wrong:** The janitor deletes a file that is being played, exported or indexed. Or it leaves index rows pointing at missing files (404 on the timeline). Or it leaves orphan files absent from the index (a slow disk leak). Or event-linked footage is deleted from under an alert.

**Why it happens:** There are several independent deleters: MediaMTX `recordDeleteAfter`, a would-be janitor, and the old `media_item_delete` endpoint `[code]`. Deletion is not coordinated with readers. Windows additionally refuses to delete an open file `[exp]`.

**How to avoid:**
- Exactly one deleter (the NVR janitor). Order of operations: mark row `deleting` → unlink file (treat ENOENT as success; on Windows `PermissionError` leave the row `deleting` and retry next sweep) → delete row.
- Never delete segments newer than `now − (2 × segmentDuration)`, nor the "open" newest segment per camera.
- Grace window: only delete if `age > retention + 10 min`. For exports and playback, take a short-lived lease in the DB (or hardlink exported inputs into a temp dir) so the janitor skips leased segments.
- Protect event-linked footage: events can "lock" their span (pre/post-roll included) from retention for a configurable, longer period, or until exported. This must be reflected in the UI as "kept".
- Delete by index and verify, not by walking mtime. Add a reconcile pass that removes orphan files older than a day.
- Make retention a function of the volume watermarks first and days second, with per-camera quotas so one 4 MP camera cannot evict the others.

**Warning signs:** Intermittent 404s on playback. Export failures near the retention boundary. `Permission denied` or sharing-violation entries in logs on Windows.

**Phase to address:** P3 (janitor), P5 (leases for playback/export), P6 (event locks).

---

### Pitfall 7: Timestamp, clock-drift, timezone and DST errors on the timeline

**What goes wrong:** The timeline shows footage at the wrong time, events don't line up with video, or days have gaps/overlaps at DST changes. "Find footage for an event in under a minute" fails because the event time and the video time disagree by minutes or hours.

**Why it happens (specific to this stack):**
- **Camera clock is unreliable at boot.** The camera has no battery-backed RTC (`FR-CF-114`). Every boot starts "uncertain" until its first NTP sync, and `clock_sync_state` reports `synced`/`uncertain` `[code]`. Camera event timestamps and OSD time can be wrong right after a reboot.
- **Pi and many small hosts have no RTC either.** Recording that starts before NTP sync gets wrong wall-clock filenames `[exp]`. An NTP step during recording can create overlapping or negative spans.
- **Mixed time bases in the old code.** MediaMTX filenames use `%Y-%m-%d_%H-%M-%S-%f` (the MediaMTX docs don't say which timezone these use), `completed_at` is a naive `utcnow()` plus "Z", and the snapshot and clip names use local `now()` `[code][docs]`. Also `utcnow()` is deprecated.
- **MediaMTX timestamps.** The old code sets `useAbsoluteTimestamp: False` because camera RTSP timestamps made a 10 s recording appear as 8 minutes `[code]`. That is correct for an NVR, but it means segment time is the NVR's receive time, not the sensor's capture time. Expect a sub-second to GOP-length offset.
- **DST.** "A day" is 23 or 25 hours twice a year. Phones travel across zones. The browser's timezone is not the site's timezone.

**How to avoid:**
- One time model, decided in P1: **store UTC epoch milliseconds everywhere** (integers, not naive strings). Convert for display only, using an IANA zone name stored as a *site setting* (default from the host, editable). API times are ISO-8601 with an offset or `Z`. Reject naive strings.
- Put the epoch in the recording path to make filenames timezone-free: use `%s` (documented variable) plus `%f` for uniqueness, for example `%path/%s_%f`. Verify in a spike `[docs]`.
- The NVR host clock is the timeline authority. Gate recording start on "clock synced" (`timedatectl show -p NTPSynchronized` on Linux, `w32tm /query /status` on Windows, `sntp`/`systemsetup` on macOS) or, if it cannot be known, start recording but mark the spans `clock_uncertain` and re-time them when sync lands. Detect wall-clock jumps by comparing against a monotonic clock.
- Use the camera clock only as a cross-check. Poll `GetSystemDateAndTime` to record per-camera offset. For camera events: if `clock_sync_state != synced`, or the offset exceeds a threshold, **re-stamp the event with NVR receive time** (minus measured latency) and flag it.
- Timeline queries are UTC ranges. Day navigation is "midnight to midnight in site timezone", computed with a tz library (`zoneinfo`, `Intl`/`date-fns-tz`/Luxon). Never `+ 24h`. Windows needs `tzdata` installed for `zoneinfo`.
- Tests: freeze time and run at spring-forward, fall-back, and a site/phone timezone mismatch.

**Warning signs:** Events 1 h off after a DST change. Footage shifted by minutes after a camera reboot. Two files with the same name or overlapping spans. A Pi that records `1970-01-01` folders after boot.

**Phase to address:** P1 (time model), P3 (indexing/clock gate), P5 (timeline), P6 (event re-stamping).

---

### Pitfall 8: Recording gaps on camera reconnect, and not showing them honestly

**What goes wrong:** When a camera reboots, Wi-Fi drops, its address changes, or its stream half-opens, MediaMTX reconnects with its own backoff. There is a gap of seconds to minutes. Typical NVRs hide gaps or draw them as "no activity". The core metric ("zero gaps on healthy cameras") can't even be measured.

**Why it happens:**
- The cameras are embedded devices (Realtek Ameba Pro2 per the firmware docs) and often on Wi-Fi (`camera_api` has Wi-Fi signal APIs) `[code]`.
- Static RTSP source URLs go stale: DHCP changes the IP, and the camera encoder config can change (resolution/codec) while the session is down `[code]`. `STREAMING_GUIDE` says to re-fetch profiles live before a reconnect, never from cache.
- A camera audio-mic toggle or resolution change stops the camera's stream by design, and the camera does not bring it back `[code]`. RTSP clients must redial.
- A different camera can take over a reused DHCP IP, causing recordings to be filed under the wrong camera (see Pitfall 17).

**How to avoid:**
- Per-camera supervisor state machine: `connecting → streaming → degraded → offline → auth_failed → cert_mismatch`. Distinguish offline, auth-failed and cert-mismatch in the UI and logs. Each demands a different user action.
- Keep `sourceOnDemand: false` for the record path (24/7) `[code]`. Use TCP interleaved transport (`rtspTransport: tcp`), as the old code does and as the camera's RTSPS listener speaks.
- When a path stays not-ready for more than X seconds, re-resolve the stream URI from the camera (ONVIF `GetStreamUri` / profile list), rediscover by serial via WS-Discovery if the IP changed, and PATCH the MediaMTX path source. Don't wait for a human.
- Compute coverage from the index as `expected − recorded`. The timeline draws three distinct things: **recorded**, **gap (should have recorded)** and **not scheduled/off**. Emit a gap record when a camera goes offline.
- Optional differentiator, but design for it: the camera records clips on its own storage and exposes Profile G/Search/Replay APIs `[code]`. After a reconnect, the NVR could backfill the gap. The camera allows only **one concurrent playback session** (HTTP 409 `PlaybackBusy`), so treat 409 as "retry later", and never hold a session open `[code]`.
- A watchdog alert if no segment completes within `2 × segmentDuration` for a camera that is `streaming`.

**Warning signs:** Cameras flapping in logs. Gaps cluster at the same time of day (router reboot, camera scheduled reboot). The "last segment" age in health keeps climbing.

**Phase to address:** P2 (resolution/re-resolution), P3 (supervisor, gap model), P5 (timeline rendering).

---

### Pitfall 9: MediaMTX exposed anonymously, bypassing NVR login and roles

**What goes wrong:** Anyone on the LAN can watch any camera, read recordings and publish into MediaMTX without an NVR account. The NVR's Owner/Operator/Viewer roles are decorative. Camera credentials can leak.

**Why it happens:** The shipped `mediamtx.yml` `[code]`:
- `authInternalUsers` has user `any`, no password, `ips: []` (any IP), with `publish`, `read` and `playback` on every path.
- RTSP, RTMP, HLS, WebRTC and SRT are all enabled and bound to all interfaces.
- `apiAllowOrigins`, `hlsAllowOrigins` and `webrtcAllowOrigins` are `['*']`.
- The Control API is localhost-only by default `[docs]`, but with `*` CORS, any web page in a browser on the NVR host can call it. Reading path configs would expose camera credentials embedded in source URLs.
- The old code also leaves `overridePublisher: true` on the default path `[code]`.

**How to avoid:**
- Switch to `authMethod: http` pointing at an NVR internal endpoint, or JWT with `mediamtx_permissions` claims issued by the NVR `[docs]`. Allow `api` only from 127.0.0.1 and exclude it from HTTP auth. Remove the anonymous `any` user. Remove the `publish` permission for everyone but the loopback ffmpeg helper (if any).
- Disable protocols you don't use: RTMP, SRT, multicast, and RTSP/RTSPS server if not needed by the mobile app. Fewer open ports means fewer firewall prompts.
- Narrow CORS to the NVR's own origin or serve everything through one reverse proxy origin (see Pitfall 11).
- Use short-lived media tokens (query-string JWTs for HLS/WHEP, since `<video>` and `fetch` to WHEP can't always send headers). Keep TTL to minutes, because these appear in access logs `[docs]` (`authJWTInHTTPQuery`).
- Re-verify in a test: an unauthenticated `ffprobe rtsp://nvr:8554/cam1` must fail.

**Warning signs:** `ffplay rtsp://nvr:8554/<cam>` works from a laptop with no credentials. Viewer-role accounts can fetch HLS for cameras they can't see.

**Phase to address:** P3 (config template), P7 (auth bridge between NVR sessions and MediaMTX).

---

### Pitfall 10: Camera and NVR credentials stored in plaintext, or handed to the browser

**What goes wrong:** Camera admin passwords leak from disk, from HTTP, from logs, or from the API.

**Why it happens (all `[code]` in the old VMS):**
- Camera credentials live in `app_data/nuraeye_user_data.json` (plain JSON under `device_info`, passed from the browser on every request).
- `main.py` sets `static_folder = os.getcwd()` and `serve_static` serves any path except `python/` or `*.py`. That includes `GET /app_data/nuraeye_user_data.json`, `mediamtx/mediamtx.yml`, and all recordings, with **no authentication**.
- `media_item_delete` joins a client-supplied URL onto the static folder without validating that it stays inside it (path traversal, arbitrary file delete).
- `app.run(host="0.0.0.0", debug=True)` exposes the Werkzeug debugger (remote code execution) to the whole LAN.
- RTSP URLs with embedded `user:pass` go into MediaMTX path config and may appear in logs/API responses. Special characters (`@ : / #`) in passwords break unencoded URLs.
- `get_tls_fingerprint` builds a `shell=True` openssl pipe with an interpolated host `[code]` (injection, and it fails on Windows).

**How to avoid:**
- Never serve the project directory. The UI is a built static bundle from a dedicated `dist/` directory; recordings are served only through authenticated endpoints that map IDs to files. Resolve and verify the real path is under the root.
- Production uses a real WSGI/ASGI server (no Flask dev server, `debug=False`), bound to the configured interface.
- Encrypt camera credentials at rest. Use the OS keystore where one exists (`keyring`: Keychain/DPAPI-backed Credential Locker/Secret Service). On headless Pi/Jetson there's usually no Secret Service: fall back to a key file (mode 0600) or a machine-bound key, and be honest in docs that this protects backups and copies, not a root compromise. Camera credentials must be recoverable (Digest/WSSE), so they cannot be hashed.
- NVR user passwords: Argon2id (`argon2-cffi`) or bcrypt, tuned so login on a Pi takes about 200-500 ms.
- Never return camera passwords from any API. The browser/mobile sends them once when adding a camera. Redact credentials in all logs and exceptions. Percent-encode credentials when building RTSP URLs.
- Prefer a **dedicated, non-admin camera account** for streaming, if the firmware supports roles. Several camera actions are Administrator-only `[code]`.
- Never build subprocess commands from strings. Use `subprocess.run([...], shell=False)` or a pure-Python TLS fingerprint fetch (the old fallback already exists).

**Warning signs:** `curl http://nvr:5000/app_data/nuraeye_user_data.json` returns data. Passwords show up in log files. A request body contains `device_info.password`.

**Phase to address:** P1 (secrets store, static-serving rules), P7 (API contract), P9 (hardening review).

---

### Pitfall 11: LAN API auth, CORS, CSRF and the mobile token

**What goes wrong:** Any website open in any browser on the LAN can drive the NVR (CSRF or DNS rebinding). The mobile app has no safe way to authenticate. Roles are enforced only in the UI.

**Why it happens:** The old API is unauthenticated, and `add_vms_cors_headers` sets `Access-Control-Allow-Origin: *` `[code]`. "LAN only" feels safe, but a browser on the LAN is a bridge to it.

**How to avoid:**
- Serve the web UI and API from the **same origin** (a reverse proxy or the app itself, also fronting MediaMTX HLS/WHEP/playback). Then no CORS is needed at all. The mobile app is not a browser, so CORS is irrelevant to it. Don't loosen CORS "for mobile".
- Web UI auth: either a bearer token in the `Authorization` header (not auto-sent, so immune to CSRF), or `SameSite=Strict`, `HttpOnly` cookies plus a CSRF token on state-changing requests. Validate the `Host` header against an allowlist (anti-DNS-rebinding).
- Mobile: a pairing flow (QR or short PIN shown in the web UI) that issues a per-device refresh token. Access tokens last ~15 min. Revocable per device in the UI. Stored with Keychain/Keystore (`flutter_secure_storage`).
- Local accounts must work 100% offline. The optional Cognito link must never be on the login, live or recording path. Cache JWKS for offline verification and degrade gracefully.
- Rate-limit and lock out login attempts per IP and per account. Constant-time comparisons.
- Role checks are server-side per endpoint. **Simple/Advanced is a UI mode, not an authorization boundary.** Viewer cannot call delete/export/settings endpoints, tested by API-level tests.
- Audit log for export, delete, settings change and user changes (guards and managers in communities need this).
- TLS decision, made explicitly in P7: plain HTTP is pragmatic on a LAN but exposes tokens. If self-signed HTTPS is offered, the mobile app needs fingerprint pinning (the camera layer already trusts self-signed certs `[code]`), and an HTTPS UI cannot load plain-HTTP media (mixed content), so the media proxy must be on the same TLS origin.

**Warning signs:** `curl -X POST http://nvr/api/...` works with no credentials. Pages from another origin can read responses. The mobile app stores the user password.

**Phase to address:** P7 (design before the UI starts calling the API, otherwise every screen is rewritten), P1 (decide TLS/origin strategy).

---

### Pitfall 12: H.265 does not play in many browsers

**What goes wrong:** Black screen or "unsupported" on some operators' PCs while it works on the developer's Mac. Both live and recorded playback are affected.

**Why it happens:**
- The camera encoder is selectable between H.264 and H.265 `[code]`.
- Browser H.265 depends on the platform and hardware: Chrome supports it only when the platform decoder does, Firefox support is partial/gated, and Linux/Pi Chromium kiosks are often unsupported `[exp]` (caniuse shows only partial support).
- WebRTC is worse. The MediaMTX docs say Chrome reads and publishes H.265 over WebRTC only on Windows with a capable GPU `[docs]`.
- H.264 with B-frames cannot be played over WebRTC at all `[docs]`.
- MediaMTX's HLS does list H.265 `[docs]`, but that still depends on the browser's MSE HEVC support.
- fMP4 H.265 needs the `hvc1` sample entry for Safari. A remux that yields `hev1` can fail there `[exp]`. Force `-tag:v hvc1` on exports.
- In-band VPS: the camera's SDP has no VPS for H.265, so players must wait for the next in-band VPS (up to ~10 s in the Dart live-view code) `[code]`. Expect slow first frame, especially with long GOPs.
- AWS KVS can't carry H.265 (not relevant to a LAN NVR, but it shapes how the mobile team thinks about it) `[code]`.

**How to avoid:**
- Policy: **live and multiview use an H.264 sub-stream; recording may use H.265 main** if the user chooses it for disk savings. Default new cameras to H.264 for both until the capability check says otherwise.
- Feature-detect in the browser: `MediaSource.isTypeSupported('video/mp4; codecs="hvc1.1.6.L93.B0"')` and `navigator.mediaCapabilities.decodingInfo(...)`. Show a clear message and offer "download clip" or "transcode for browser".
- Server-side transcode fallback is expensive. Make it opt-in, one stream at a time, and refuse on weak hosts (Pi) with a clear explanation. Hardware encoders (NVENC on Jetson/PC, VideoToolbox on macOS, VAAPI) vary by platform.
- Store per-camera `codec`, `profile`, B-frame risk, and the playable-in-browser verdict from the capability response. Re-read after any encoder settings change (see Pitfall 17).
- Test matrix: Chrome and Edge on Windows with and without GPU HEVC, Safari on macOS and iOS, Firefox, Chromium on Pi, Android WebView/ExoPlayer, and the iOS player.

**Warning signs:** Support requests of the form "works on one PC, black on another". Playback works in VLC but not in the UI. First frame takes 5-10 s.

**Phase to address:** P2 (capability + codec model), P4 (live), P5 (playback/export).

---

### Pitfall 13: Event recording that has no pre-roll, or hides footage

**What goes wrong:** Event clips start after the interesting moment, are missing the lead-up, never finalize, or are not shown in the timeline.

**Why it happens:**
- The old `preRecordBuffer: 5` and `postRecordBuffer: 15` settings are described as "handled at app layer, not MediaMTX", but nothing implements them `[code]`.
- Starting recording on a trigger can't produce pre-roll. It also adds the latency chain: camera detection → alert delivery to the NVR → recorder start → wait for the next keyframe (GOP).
- Event mode in the old code records *everything* into `clips/` with `24h` segment duration when "off" `[code]`. Nothing is finalized for hours, the webhook doesn't fire, and the index ignores `clips/`.
- Alert storms: `PersonDetected` every second creates thousands of clips.
- The NuraEye LAN alert stream and the ONVIF fallback can both fire for the same occurrence, which produces duplicates. PullPoint subscriptions expire, and half-open sockets stop delivering without error `[exp]`.
- A camera with an uncertain clock stamps events wrongly (Pitfall 7).

**How to avoid:**
- **Events are metadata over continuous footage.** Always record the stream (continuous ring). Store events as `(camera, type, start_utc, end_utc, source, confidence)` and resolve pre/post-roll **at query time** with configurable margins. Pre-roll then equals whatever exists, to the keyframe, and is adjustable after the fact.
- "Event-only" storage mode (for small disks) is implemented as post-hoc retention: keep only segments overlapping events ± margins, and delete the rest after a short rolling buffer (for example 10 minutes). It is a janitor policy, not a different recorder.
- Merge overlapping events into incidents (debounce window, say 10-30 s). Dedupe across sources by `(camera, type, ±N s)`.
- Clip boundaries snap back to the previous keyframe, so accuracy is limited by GOP length (a camera encoder setting). Surface this in docs and the settings UI.
- A clip that spans two segments is served through the playback range API (`/get` with start+duration) rather than a file pointer `[docs]`.
- Subscription watchdog: heartbeat/timeout, resubscribe with backoff, and **backfill** missed events after any reconnect using the camera's event search (`findEvents`) `[code]`.
- Honour camera-side event enable flags (`EventPreferences`): disabling a type is a real device-side change and suppresses it on every delivery path, including ONVIF PullPoint `[code]`, so the "ONVIF fallback" does not recover events a user turned off.
- Event row links to a locked footage span, so retention won't delete it (Pitfall 6).

**Warning signs:** Event thumbnails start mid-action. Clips missing in the timeline but present on disk in `clips/`. Dozens of identical events per minute. Alert delivery stops after a few hours.

**Phase to address:** P6 (design and implementation), with retention locks in P3.

---

### Pitfall 14: Contract drift between the Python camera layer and Dart `camera_api`

**What goes wrong:** The NVR and the mobile app behave differently against the same camera. Features that work from the phone fail from the NVR, or silently misbehave on a firmware update. The project's key decision ("camera_api contracts are source of truth") is only prose.

**Why it happens:**
- The contract is Markdown with dated amendments ("revised 2026-09-11", "superseded", "removed 2026-09-17"). Stale copies exist.
- The old Python layer lacks several newer contract points `[code]`: no `X-VizenLink-Camera-Id` header (grep found none), no bearer-session handling (`sessionLogin`, 401 retry), and the stream resolution comes from ONVIF only.
- Contract details that a naive port gets wrong `[code]`:
  - **SOAP faults before HTTP status.** The firmware does not use consistent HTTP codes for faults. The Dart clients check the `<Fault>` element before the status. A Python `raise_for_status()` pattern is wrong.
  - **Header case is significant.** The camera's embedded server matches header names case-sensitively. There is a Dart test for this (`case_preserving_http_client_test.dart`). Python HTTP stacks differ in whether they preserve case, so test on the wire.
  - **Self-signed TLS.** `verify=False` globally is the lazy answer. Pin per camera instead.
  - **First-contact timeouts.** A cold TLS handshake can take longer than 5 s on a genuine camera (`areYouNuraeyeDeviceWithRetry`: 3 × 8 s). The old Python uses fixed `(5.0, 10.0)` timeouts.
  - **421 on camera-ID mismatch.** The camera answers 421 when the `X-VizenLink-Camera-Id` header does not match its serial. This is exactly how a DHCP-reused IP is detected (see Pitfall 17).
  - **Transport is the camera's decision.** `POST /nuraeye/live-stream-uri` returns `webrtc` or `rtsp` depending on the firmware build flag `WEBRTC_STREAMING`. An NVR that expects RTSP from that call will break on a build that returns WebRTC. The guide says the three profiles are ordinary ONVIF profiles reachable via `GetStreamUri` too, but `Profile_3` is a NuraEye-only, mobile-only token, not an ONVIF profile `[code]`.
  - **Don't use the camera's WebRTC from the NVR.** One peer connection per signalling port, and any new offer evicts the old one `[code]`.
  - **Capability and profile caching rules.** Cache capabilities at onboarding, but **re-fetch profiles live before every reconnect**. Never hardcode "three streams" `[code]`.
  - **Typed results.** Dart returns `CameraResult<T>` with a `CameraFailure` taxonomy (`CameraForbidden`, `PlaybackBusy`, `ActionNotSupported`, ...). Python must mirror this taxonomy (a `Result` type or exception hierarchy) rather than returning `None`/bool like the old `Optional[dict]`.
- The NVR REST API for mobile will drift the same way. The old API uses `{success,data|error}`, the camera uses `{error_code,error_msg,output}`, so there are already two envelopes.

**How to avoid:**
- Create a **contract matrix** in P1: every `camera_api` client method the NVR needs → Python function → test status → firmware-version notes. CI fails on an unmapped "required" row.
- **Golden fixtures**: harvest real request/response exchanges from the Dart tests and `test/fixtures`, plus captures from a real camera (the firmware repo's `testing_utilities/*.py` are existing Python wire-protocol references), and replay them in Python tests. Include fault cases and header-case assertions.
- A hardware-in-the-loop smoke test run against a real camera before each release (identity, login, capabilities, profiles, stream URI, recording search, event preferences).
- Any change to `camera_api` itself needs owner confirmation (PROJECT.md constraint). Record that as an explicit "contract change request" workflow.
- For the NVR's own REST API: write an OpenAPI 3 spec first, version it (`/api/v1`), and generate the TypeScript types and the Dart client from it in CI. Timestamps are ISO-8601 UTC; pagination and range queries are mandatory (spans not lists); errors use one envelope.
- Key cameras by serial/thing name, never by IP.

**Warning signs:** "Works from the phone but not from the NVR." A camera firmware update breaks a feature. Python and Dart disagree on a capability flag. Hand-written API client code in three languages.

**Phase to address:** P1 (matrix, fixtures harness), P2 (camera layer), P7 (OpenAPI first).

---

## Moderate Pitfalls

### Pitfall 15: RTSPS fingerprint pinning is trust-on-first-use with no re-pin path

**What goes wrong:** The camera uses a self-signed certificate. The old client fetches its SHA-256 fingerprint once at registration and injects it as `sourceFingerprint` `[code]`. When the cert changes (factory reset, firmware update, regenerated key), MediaMTX can't connect and recording stops with an opaque TLS error.

**How to avoid:** Store the fingerprint in the DB. Add a `cert_mismatch` camera state with a user-visible "camera's certificate changed - trust the new one?" action (Owner only). Use one TOFU store for REST, ONVIF and RTSPS. Fetch the fingerprint with Python's `ssl` (no shell). The camera's RTSPS port can differ (the old code tries 554 then 322), so take the port from the stream URI.

**Warning signs:** Gaps after a firmware upgrade. TLS errors in MediaMTX logs. Sudden `auth_failed`-looking states that are really certificate problems.

**Phase to address:** P2, P3.

---

### Pitfall 16: Password changes elsewhere break recording

**What goes wrong:** The user changes a camera password from the phone app (via `setUserPassword`) and the NVR keeps the old one. The RTSP source gets 401 and recording stops. Separately, the camera's bearer session cache gets stale (`clearSessionFor` exists for this reason `[code]`).

**How to avoid:** An `auth_failed` camera state, distinct from offline, with a one-tap "update credentials". Notify owners. If the NVR itself changes a camera password, update MediaMTX and the DB atomically and roll back on failure. Cache a bearer session per camera, retry login once on 401.

**Phase to address:** P2, P8.

---

### Pitfall 17: Camera identity tied to IP, and the DHCP address-reuse trap

**What goes wrong:** A camera's DHCP lease changes. The NVR records from the old address, now possibly a *different* camera, and files its footage under the wrong name. Or the stream just dies.

**How to avoid:**
- Camera identity is the serial/thing name from the identity call, not an IP. Send `X-VizenLink-Camera-Id` on every REST call and treat 421 as "wrong device at this address" `[code]`.
- Re-discover with WS-Discovery by serial when the stream fails, then PATCH the source.
- Recommend (and detect/warn on) DHCP reservations in onboarding.
- Use opaque ASCII IDs (UUID or short slug) for MediaMTX path names and folders. Display names live in the DB. The old `sanitize_camera_id` lowercases and replaces non-alphanumerics, which can collide (two cameras with similar names map to one path) and mangles non-Latin names `[code]`.

**Phase to address:** P2.

---

### Pitfall 18: Multiview opens everything at full resolution

**What goes wrong:** A 16-tile grid decoding 16 × 4 MP streams overwhelms the client browser or phone. The Wi-Fi AP and the NVR NIC saturate. On the server, ffmpeg audio transcodes pile up.

**Why it happens:**
- The old VMS registers only the *highest-resolution* stream for live view and recording, with alternates as on-demand paths `[code]`.
- Each camera gets a second `_audio` path running `ffmpeg ... -c:a libopus` on demand (AAC to Opus) `[code]`. WebRTC can't carry AAC, so each viewer that touches audio spawns an ffmpeg process.
- `sourceOnDemand: true` alternates have a startup delay (default `sourceOnDemandStartTimeout: 10s`), so tiles load slowly `[code]`.
- Embedded cameras likely limit simultaneous RTSP sessions. The number is unknown (LOW confidence, check on hardware). Each profile used by a viewer is another upstream connection unless MediaMTX shares it. MediaMTX does share one upstream per path.
- All segment rotations align after a restart (Pitfall 4).

**How to avoid:**
- **Two profiles per camera by design:** main stream for recording and focused view, a low/medium sub-stream for grid tiles. Choose by tile size. Read the profile list, never hardcode three `[code]`.
- Grid rules: more than 4 tiles → sub-stream only. Pause tiles that are off-screen or in a hidden tab (`IntersectionObserver`, `visibilitychange`). Cap concurrent players by host profile. Offer a low-fps JPEG snapshot grid for weak clients and Pi.
- Audio is off in the grid. Use HLS for audio live view (MediaMTX HLS carries AAC `[docs]`) and skip the Opus transcode entirely, or run the transcode only for the single focused camera.
- Keep the NVR from decoding video at all, except thumbnails: generate keyframe-only (`-skip_frame nokey`), at low priority, one worker.
- Use the persistent sub-stream path with `alwaysAvailable`-style warmness only for cameras that appear on the default dashboard. Otherwise accept the on-demand delay and show a skeleton.
- Document the support matrix: Pi 3 and earlier (shared USB/Ethernet bus) are not viable for 16 cameras. Pi 4/5 with an SSD is a floor for 8. Measure instead of guessing.

**Warning signs:** CPU of the browser tab at 100%. Fans on the viewer's laptop. Stutter when many tiles join. ffmpeg processes in `top` on the server.

**Phase to address:** P4 (and P2 for profile selection).

---

### Pitfall 19: WebRTC LAN specifics and hardcoded `localhost` URLs

**What goes wrong:**
- The old `add_camera` returns `video_webrtc_url: http://localhost:8889/...` `[code]`. Any client not on the NVR host gets an unusable URL.
- `get_local_ip()` (UDP-connect trick) can choose the wrong interface on multi-NIC hosts, VPN, Docker, WSL or Tailscale machines `[code]`.
- ICE candidates include every interface (`webrtcIPsFromInterfaces: true`) `[code]`, so clients may try virtual adapters.
- In Docker bridge mode the advertised candidate is the container IP.
- UDP blocked by guest Wi-Fi/AP isolation/VLAN or by the Windows firewall (a first-run prompt for inbound UDP 8189) makes WebRTC fail where HLS works `[docs]`.

**How to avoid:**
- Never return absolute media URLs with a host baked in. Return relative paths served through the same-origin proxy, or build URLs from the request's Host header. The mobile app builds the base URL from the NVR address it paired with.
- Configure `webrtcAdditionalHosts` and `webrtcIPsFromInterfacesList` deliberately. Enable the TCP fallback (`webrtcLocalTCPAddress: :8189`) so clients that can't use UDP still connect `[docs]`.
- No STUN/TURN in v1 (LAN only). Leave `webrtcICEServers2` empty.
- Use host networking or explicit port publishing for containers. Document it.
- Provide HLS (low-latency) as the always-works fallback and let the UI auto-fallback when the WebRTC handshake exceeds `webrtcHandshakeTimeout`.
- Don't use the camera's own WebRTC endpoint at all (Pitfall 14).

**Warning signs:** Live works on the NVR host but not on other PCs. Works on Wi-Fi A, fails on Wi-Fi B.

**Phase to address:** P4, P9.

---

### Pitfall 20: MediaMTX version drift and config churn

**What goes wrong:** An auto-updated or differently-pinned MediaMTX changes config keys, auth format or hook env names, and the generated config silently stops working. Different platforms ship different binaries.

**Why it happens:** MediaMTX is fast-moving. The old repo vendors a binary and `get_mediamtx_file()` picks by platform `[code]`. Config examples have renamed keys across 1.x (for example `authInternalUsers` shape and `webrtcICEServers2`) `[exp]`.

**How to avoid:** Pin an exact MediaMTX version and checksum per OS/arch (Linux amd64, arm64, armv7 where relevant; Windows; macOS arm64/amd64). Generate the YAML from a template with a version marker and validate it on startup (`mediamtx --check` if available, else a dry run in CI). Contract-test the Control API calls the NVR uses against the pinned binary in CI. Treat upgrades as a deliberate PR with a recorded-footage smoke test. Always set explicit values for every recording key (`recordFormat`, `recordPartDuration`, `recordSegmentDuration`, `recordDeleteAfter`, `recordMaxPartSize`) rather than inheriting defaults.

**Phase to address:** P1, P3, P9.

---

### Pitfall 21: Cross-platform process and path assumptions

**What goes wrong:** It works on the developer's Mac and fails on Windows or Pi. Recordings stop when the machine sleeps or when the user logs out.

**Why it happens / specifics:**
- **Shell hooks.** `runOnRecordSegmentComplete` uses `curl -X POST ... -H 'Content-Type: application/json' -d '{...$MTX_SEGMENT_PATH...}'` `[code]`. Single quotes are not string delimiters in `cmd.exe`, and `$VAR` expansion is a Unix-shell feature `[exp]`. The hook can break outright on Windows. Verify in a P9 spike. Safer: the hook launches a tiny cross-platform helper (the Python interpreter or a frozen executable) that reads `MTX_SEGMENT_PATH` from the environment, or skip hooks and rely on the filesystem scanner (Pitfall 4).
- **Shell pipelines** (`openssl ... | cut | tr`, `</dev/null`) don't exist on Windows `[code]`.
- **Signals.** `SIGTERM` doesn't behave on Windows. `proc.stdin.write(b'q')` to stop ffmpeg is the portable way, but orphaned children survive a Python crash. Use Job Objects on Windows, `PR_SET_PDEATHSIG` or a process group on Linux, and a supervisor/launchd on macOS. The old `active_clip_processes` dict is in memory, so a restart orphans ffmpeg `[code]`.
- **Paths.** `os.path.relpath` raises `ValueError` across Windows drives (recordings on `D:`, app on `C:`) `[exp]`. The old settings store an absolute macOS path in JSON `[code]`. Use `pathlib`, store paths relative to a configured root, always `encoding="utf-8"` (Windows defaults differ, and camera names may be non-Latin), avoid names reserved on Windows, and watch the 260-character limit (use short, shallow `root/<cam>/<yyyy>/<mm>/<dd>/` trees).
- **File locking.** Windows refuses to delete or rename open files (Pitfall 6). Antivirus real-time scanning of the recordings directory causes I/O stalls. Document an exclusion.
- **Sleep and sessions.** Windows and macOS sleep or hibernate kills recording. Use `SetThreadExecutionState`/`caffeinate`/`pmset`, or require a "recorder mode" power plan. The NVR must run as a boot-time service: systemd (Linux), a Windows Service (NSSM/pywin32), a `LaunchDaemon` (macOS). Note that Windows services run in session 0 and cannot see mapped network drives.
- **Dependencies.** `netifaces` (old requirements) is unmaintained and needs a compiler on Windows/ARM `[exp]`. Prefer `ifaddr` or `psutil`. Pin Python (3.11/3.12) because the old repo ran 3.14 bytecode `[code]` and Pi wheels lag.
- **ffmpeg.** Don't assume it's on PATH. Bundle or locate static ffmpeg/ffprobe per platform, and check version and codec capabilities at startup.
- **Discovery.** WS-Discovery multicast needs per-interface binding on multi-NIC machines and may need firewall rules.

**How to avoid:** CI matrix on Linux amd64, Linux arm64 (Pi/Jetson), Windows and macOS covering unit tests, a MediaMTX start/stop, and a 10-minute record/index/play smoke test. A "platform support matrix" document that states what is guaranteed per OS.

**Phase to address:** P1 (supervision abstractions, path layer), P9 (services, packaging, CI matrix).

---

### Pitfall 22: SD-card wear on Raspberry Pi

**What goes wrong:** The SD card dies in months because the OS, SQLite, logs and (worst) recordings are all on it. The recorder dies with it.

**How to avoid:**
- Recordings on USB SSD only. Refuse the SD card as a recording target on Pi unless the user explicitly overrides.
- Minimise SD writes: SQLite WAL with `synchronous=NORMAL`, batched index writes, no per-segment JSON rewrites (the old design rewrote a growing file every 5 minutes per camera `[code]`), MediaMTX `logDestinations: [stdout]` into journald with `Storage=volatile` or `log2ram`, thumbnails on the SSD.
- Health page shows disk SMART/wear where available. Warn on SD root usage.
- Power: use the official supply. Pi undervoltage and USB-SSD power sag cause corruption. Detect throttling (`vcgencmd get_throttled`) and surface it `[exp]`.

**Phase to address:** P3, P9.

---

### Pitfall 23: Manual clip and export implemented as ad-hoc ffmpeg processes

**What goes wrong:** A separate ffmpeg subprocess re-reads the live RTSP relay for manual clips, produces non-fragmented MP4 killed mid-write when stopped uncleanly, and orphans on restart `[code]`. Exports read segments that the janitor may delete. Multi-segment exports with `concat` and `-c copy` have timestamp discontinuities, producing frozen frames, A/V desync or wrong duration `[exp]`.

**How to avoid:** Derive clips from the recorded index (start/end in UTC), not a second live capture. Build exports through an export job queue: lease segments, trim at keyframes, remux with `-c copy`, `-movflags +faststart`, `-tag:v hvc1` for H.265, and run one export at a time on low-end hosts. Validate output with ffprobe before presenting it. Cap export range and size. Write to a temp file, then rename. Expire exports.

**Phase to address:** P5.

---

## Minor Pitfalls

### Pitfall 24: Segment duration is a minimum, not a boundary

`recordSegmentDuration` is the *minimum* segment length and rotation happens on a keyframe `[docs]`. Don't assume files are exactly 5 minutes or aligned to wall-clock minutes. Index actual start/end. A long GOP (camera setting) lengthens segments and pre-roll granularity.

**Phase to address:** P3.

### Pitfall 25: Tiny "drift-reset" segments

The old webhook silently deletes TS files under 10 KB, described as artifacts when the stream timestamp jumps `[code]`. That is silent data loss with no gap record. Record these in a counter and log, mark a gap, and alert if they recur, since they indicate camera clock or RTP timestamp problems.

**Phase to address:** P3.

### Pitfall 26: Audio track composition changes mid-stream

Toggling the camera mic (`SetAudioRecording`) forces the camera to stop its cloud stream, and track composition changes across a reconnect `[code]`. The NVR's RTSP session will reconnect with a different track set, so a segment boundary appears and the playback UI must not assume a constant track layout. Consider recording video-only plus an audio-presence flag if the camera setting changes frequently.

**Phase to address:** P3, P8.

### Pitfall 27: Settings UI built from assumptions instead of capability flags

The contract is "build UI from the Options/capability response, never hardcode bounds" (for example clip duration min/max, loitering min/max, `supportsCbr` per encoding) `[code]`. A static Python/React settings form drifts as firmware changes. Generate forms from the capability response and cache it with a TTL, as the Dart app does.

**Phase to address:** P8.

### Pitfall 28: Clip-duration semantics on the camera

When the camera's clip duration changes, it applies only at the next rotation, and every clip's reported `end` is computed from the *current* setting, not the one in effect when recorded `[code]`. Backfill and event correlation against camera-side clips are approximate. Don't use camera `end` times as exact.

**Phase to address:** P6 (if camera-clip backfill is built).

### Pitfall 29: Simple mode hides failures

A Simple view that hides health and gap information for home users makes failures invisible. Keep one red/amber status banner visible in both modes ("Camera X not recording since 14:03").

**Phase to address:** P3 health model, P4/P5 UI.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep `segments.json` per camera | Port from the old VMS in an hour | Race conditions, unbounded growth, silent index wipe, no range queries, mobile gets a 138k-row list | Never |
| Keep MPEG-TS + post-hoc ffmpeg remux | Known to "work" with the old player | Doubled disk writes, thundering herd, half-converted files, CPU load on Pi | Never; record fMP4 |
| Flask dev server with `debug=True` | Zero setup | Remote code execution on LAN, no concurrency | Never in anything shipped. Local dev only, bound to 127.0.0.1 |
| `Access-Control-Allow-Origin: *` | Frontend dev ergonomics | Drive-by CSRF from any LAN browser | Dev proxy only |
| Serve project root as static files | Trivial frontend hosting | Leaks credentials and recordings | Never |
| Hard-code `localhost` in returned media URLs | Works on the dev machine | Breaks every other client | Never |
| Hook-driven indexing only | Simple event flow | Lost hooks = lost footage | Only alongside a filesystem scanner |
| `verify=False` for all camera TLS | Fast onboarding | No identity guarantee, no cert-change detection | Only as the first step of a TOFU pin flow |
| Camera IP as identity | Easy to code | Misfiled footage after DHCP change | Never |
| Naive local timestamps in DB/API | Quick UI | DST bugs, mobile disagreement | Never |
| Hand-write the mobile API client | Fewer tools | Drift between Python, TS and Dart | Only if OpenAPI generation is postponed to P7 start |
| Skip DB migrations | Faster early phases | Cannot upgrade installed boxes | Never; add before first install |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| MediaMTX Control API | Treat HTTP 400 as "already exists"; no reconcile; paths lost on restart | Idempotent add-or-patch, reconciler, MediaMTX as a separate supervised service |
| MediaMTX recording | Inherit `recordDeleteAfter: 1d`, default format, local-time filenames | Set every record key explicitly, `recordDeleteAfter: 0s`, fMP4, epoch in filename |
| MediaMTX auth | Leave anonymous `any` user, `*` CORS | `authMethod: http`/JWT bridged to NVR sessions, API on loopback only |
| MediaMTX hooks | Shell strings with `curl`, `$VAR` | Helper executable or scanner-first design, tested on Windows |
| MediaMTX playback server | Use it without `/list`, assume contiguous recording | Query `/list` for spans, then `/get` per span; encode RFC3339 params; expect gaps `[docs]` |
| Camera REST/ONVIF | `raise_for_status()`, fixed short timeouts, lowercase headers, `verify=False` | SOAP fault first, generous first-contact retry, case-preserving client, pinned certs, camera-ID header |
| Camera live-stream URI | Expect RTSP from `/nuraeye/live-stream-uri` | Use ONVIF `GetStreamUri` for NVR streams; branch on the returned transport if used |
| Camera WebRTC | Open a second connection to the same signalling port | NVR does not use the camera's WebRTC. Never open two peer connections per port |
| Camera playback/replay | Hold a playback session | One session camera-wide; 409 `PlaybackBusy` is retryable; keep sessions short |
| Camera alerts | Assume a push stream never drops; trust camera timestamps | Watchdog + resubscribe + `findEvents` backfill; re-stamp on uncertain clock |
| ffmpeg | Assume on PATH; unbounded concurrency; `shell=True` | Bundled/located binary, bounded worker pool, argument arrays |
| Cognito (optional) | Put it on the login/recording path | Local accounts first; offline JWKS cache; link is additive |
| Flutter app | Hand-written client; CORS tweaks for mobile | OpenAPI-generated client; pairing token; no CORS involvement |
| OS service managers | Run as the logged-in user in a terminal | systemd / Windows Service / LaunchDaemon with restart-on-failure |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-res streams in the grid | Browser CPU 100%, stutter, saturated Wi-Fi | Sub-stream for tiles, pause off-screen tiles, snapshot-grid mode | ~4-6 tiles of 4 MP on a laptop; 16 on anything |
| Per-viewer audio transcode (AAC to Opus) | ffmpeg processes pile up, Pi at 100% | Mute in grid; HLS for audio; transcode focused camera only | 3+ viewers with audio |
| Remux or thumbnail ffmpeg on every segment completion | CPU spike every N minutes, I/O burst | Drop remux (fMP4); bounded low-priority queue; stagger | After restart, when 16 cameras align |
| Per-segment list APIs | Slow timeline and mobile browse | Coverage spans, range queries, pagination, indexed SQL | ~10k segments (about 1 week × 4 cameras) |
| JSON file index | O(n) rewrite per segment | SQLite | Immediately at 16 cameras |
| SD-card recording or logs | Write queue overflows, dropped frames, card dies | USB SSD, volatile logs, WAL | Any bitrate on Pi 3-class; months of life on SD |
| Thumbnail strip generation for scrubbing | CPU load on open | Keyframe-only, lazy, cached, one worker | First time a 24 h timeline is opened |
| Many WebRTC readers | Server CPU rises (SRTP per reader per stream) | WebRTC for the focused tile only, HLS for the rest | ~10+ concurrent readers on a Pi |
| Upstream RTSP sessions per camera | Camera refuses sessions or drops | One upstream per profile via MediaMTX; limit active sub-stream paths; confirm the camera's cap on hardware (LOW confidence) | Unknown. Test with 1..N viewers |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Debug server on `0.0.0.0` | Remote code execution from the LAN | Production WSGI/ASGI server, `debug=False` |
| Static serving of the project directory | Credential file and recordings downloadable unauthenticated | Serve only `dist/`; authenticated, ID-based media endpoints |
| Path traversal in delete/download endpoints | Arbitrary file delete/read | Resolve against a root, reject outside; use IDs not paths |
| Anonymous MediaMTX read/publish/playback | Viewing and stream injection by any LAN host | HTTP/JWT auth, no anonymous `any`, no `publish` permission |
| CORS `*` + unauthenticated POST | Drive-by actions from any website on the LAN | Same-origin serving, token auth, Host-header allowlist |
| Plaintext camera credentials in JSON/logs/URLs | Camera takeover | Encrypted store, redaction, never returned by API, non-admin streaming account |
| Passwords echoed into RTSP URLs with special chars | Broken URLs, leaked in logs | Percent-encode, redact |
| Long-lived mobile token with no revocation | Lost phone = permanent access | Pairing, short access tokens, rotating refresh, per-device revoke |
| Roles enforced only in the UI | Viewer calls privileged endpoints | Server-side checks plus API-level role tests |
| Tokens in media URL query strings | Leak through logs/history | Minute-scale TTL, scope per path/action, no reuse across cameras |
| Default or weak initial admin | Takeover on first boot | First-run wizard forces owner creation; no default password |
| `shell=True` with interpolated hosts | Command injection | Argument arrays; pure-Python TLS probe |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Timeline draws gaps as "nothing happened" | Users trust footage that was never recorded | Distinct styles: recorded / gap (expected, missing) / not scheduled / camera offline |
| Live fine, recording dead, no indication | Discovery of loss only when footage is needed | Per-camera recording-health badge visible in both Simple and Advanced |
| Time in browser's timezone | Event shown at the wrong hour for travellers and mobile | Display site timezone, show tz label, option to show local |
| H.265 black screen with no explanation | "NVR is broken" | Capability message and a download/transcode action |
| Event list entries that 404 | Core value broken | Locked spans, "footage no longer available" with reason |
| Alert storms | Notification fatigue, huge lists | Incident merging, per-type debounce |
| Storage settings in unrelated units | Users can't size a disk | Show "about N days at current bitrate" and the effect of settings |
| Silent retention deletion | Surprise data loss | Explain what will be deleted next and when; warn at watermark |
| Camera password errors shown as "offline" | Wrong troubleshooting | Separate `auth_failed` and `cert_mismatch` copy with an action |
| Slow first frame (10 s on-demand + VPS wait) | Looks hung | Skeleton + progress, warm paths for default dashboard |

## "Looks Done But Isn't" Checklist

- [ ] **24/7 recording:** often missing survival across NVR restart, MediaMTX restart, camera reboot, IP change. Verify by killing each process and rebooting the host mid-recording, then assert gap length is bounded and the index is consistent.
- [ ] **Retention:** often missing real enforcement and `recordDeleteAfter: 0s`. Verify with tiny retention that the janitor, and only the janitor, deletes, with no orphans and no dangling rows.
- [ ] **Disk full:** often untested. Verify by filling a small loop volume; oldest footage is evicted, recording continues, an alert appears, and nothing outside the recordings root is written.
- [ ] **Unplugged drive:** verify recording refuses to write to the root disk when the marker file is missing.
- [ ] **Power loss:** verify with 10 hard kills that the newest segment is playable or marked damaged, and that at most `recordPartDuration` is lost.
- [ ] **Timeline across DST:** verify spring-forward and fall-back days, and a phone in a different timezone.
- [ ] **Clock-uncertain camera:** verify an event from a just-rebooted camera lands on the right footage.
- [ ] **Event pre-roll:** verify a clip includes the seconds before the trigger, and that adjacent-segment events play seamlessly.
- [ ] **H.265:** verify on at least one browser without HEVC support; the UI explains and offers an alternative.
- [ ] **WebRTC from another device:** verify from a phone and a second PC (not localhost), with UDP blocked (TCP fallback or HLS fallback).
- [ ] **Auth:** verify unauthenticated RTSP/HLS/WHEP/playback are rejected; Viewer cannot call privileged endpoints; `/app_data/...` is not retrievable; cross-origin POST is blocked.
- [ ] **Credential hygiene:** grep logs, API responses and the DB for plaintext passwords.
- [ ] **Windows:** verify the segment hook/helper works, paths with spaces and non-ASCII names work, recordings on a second drive work, and the service starts without a login.
- [ ] **Pi:** verify the SD card has no recordings, and SD write rate is low (use `iostat`).
- [ ] **Contract:** verify the Python camera layer passes golden fixtures and a real-camera smoke test; every required `camera_api` method has a matrix row.
- [ ] **16 cameras:** verify CPU, memory and network at 16 recording cameras plus 2 viewers on the target hardware.
- [ ] **Password change from the phone:** verify the NVR shows `auth_failed` and recovers after a credential update.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Index lost or corrupt | LOW (if scanner exists) | Run full rescan; ffprobe each file; rebuild spans; flag damaged |
| MediaMTX paths lost after restart | LOW | Reconciler re-adds from DB |
| Truncated newest segments after power loss | LOW | Startup sweep quarantines/trims; mark gap |
| Wrong timestamps after a clock jump | MEDIUM | Re-time spans using stored monotonic offsets and `clock_uncertain` flags; otherwise manual correction tool |
| Retention deleted needed footage | HIGH (unrecoverable) | None; prevent with event locks and warnings, plus an "export before delete" prompt |
| Credentials leaked | HIGH | Rotate camera passwords through `setUserPassword`, rotate NVR tokens, reissue pairing; audit log review |
| Camera cert changed | LOW | Owner approves re-pin |
| DHCP address reuse misfiled footage | MEDIUM | Use serial-keyed identity going forward; move misfiled spans by time range |
| Disk filled by an unmounted drive | MEDIUM | Delete files under the mount point, remount, rescan |
| Contract drift discovered late | MEDIUM-HIGH | Add fixtures reproducing the discrepancy; fix Python; document in the matrix; coordinate any Dart change with the owner |
| MediaMTX upgrade broke config | LOW-MEDIUM | Roll back pinned binary; fix template; add CI check |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. State only in MediaMTX/browser | P1, P3 | Kill/restart test passes; reconciler logs show convergence |
| 2. MediaMTX `recordDeleteAfter` | P3 | Config test asserts `0s`; retention integration test |
| 3. Live OK / recording dead | P3 (+P9) | Disk-full, slow-disk and missing-mount tests; health badge |
| 4. Webhook + JSON index | P3 | Scanner rebuilds index from disk; load test with 16 cameras |
| 5. Power-loss corruption | P1 spike, P3 | 10 hard-kill test; ffprobe sweep |
| 6. Retention races | P3, P5, P6 | Concurrent play/export during janitor run; no 404s, no orphans |
| 7. Timestamps/timezone/DST | P1, P3, P5, P6 | DST fixtures; camera-reboot event alignment test |
| 8. Reconnect gaps | P2, P3, P5 | Chaos test (camera power-cycle, IP change); timeline shows gap |
| 9. MediaMTX anonymous exposure | P3, P7 | Unauthenticated RTSP/HLS/WHEP fail |
| 10. Credentials and static serving | P1, P7, P9 | Pen-test checklist; secrets grep |
| 11. LAN API auth/CORS/CSRF/mobile token | P1, P7 | Cross-origin and role tests; pairing and revoke tests |
| 12. H.265 in browsers | P2, P4, P5 | Browser matrix; feature-detect message |
| 13. Event pre-roll | P6 (+P3 locks) | Pre-roll clip test; alert-storm merge test; subscription-drop backfill test |
| 14. Contract drift | P1, P2, P7 | Contract matrix in CI; golden fixtures; real-camera smoke; OpenAPI codegen |
| 15. Cert pinning | P2, P3 | Regenerate camera cert; UI prompts and recovers |
| 16. Password changed elsewhere | P2, P8 | Change on phone; NVR shows `auth_failed` then recovers |
| 17. IP-as-identity | P2 | Swap two cameras' IPs; 421 detected, footage not misfiled |
| 18. Multiview load | P4 | 16-tile grid CPU/network budget on target hardware |
| 19. WebRTC LAN/localhost URLs | P4, P9 | Test from a second device; UDP blocked fallback |
| 20. MediaMTX version drift | P1, P3, P9 | CI against pinned binary; explicit config keys |
| 21. Cross-platform process/path | P1, P9 | CI matrix; Windows hook/service test |
| 22. Pi SD wear | P3, P9 | `iostat` on SD during 1 h recording |
| 23. Clip/export via ad-hoc ffmpeg | P5 | Export across segment boundary plays with correct duration; kill-during-export leaves no partial file |
| 24-29. Minor items | as noted | Covered by the checklist above |

## Research Flags for Phases (needs hands-on spike before planning)

| Phase | Why | Spike |
|-------|-----|-------|
| P1 / P3 | Power-loss behaviour, `%s` in `recordPath`, API-path persistence, MediaMTX recorder behaviour on slow disk, `recordPartDuration` trade-offs | 24 h record from a real camera, 10 hard kills, slow USB stick, MediaMTX restart with API-added paths |
| P2 | Camera session limits, RTSP availability when `WEBRTC_STREAMING` is on, whether `Profile_3` is reachable by RTSP for NVR, WSSE timestamp tolerance (NVR vs camera clock skew), non-admin streaming account | Real-camera test script |
| P4 | Browser/H.265 matrix, HLS-LL vs WebRTC latency/CPU on Pi | Browser lab + Pi benchmark |
| P6 | Which alert transport (LAN alerts API vs ONVIF PullPoint) delivers, its timestamp semantics, reconnect behaviour | Capture alerts for 24 h, power-cycle camera |
| P9 | Windows hook quoting, firewall prompts, services, sleep | Windows VM + physical test |

## Sources

**Verified in local code and docs (HIGH):**
- Old VMS `vms/python/mediamtx_client.py` (recording config, hook, audio transcode path, localhost URLs, fingerprint fetch)
- Old VMS `vms/python/server.py` (segment webhook, `segments.json`, clip ffmpeg, media delete, CORS)
- Old VMS `vms/main.py` (`static_folder = os.getcwd()`, `debug=True`, `host="0.0.0.0"`, MediaMTX subprocess)
- Old VMS `vms/mediamtx/mediamtx.yml` (`authInternalUsers`, `recordDeleteAfter: 1d`, CORS `*`)
- Old VMS `vms/app_data/nuraeye_user_data.json` (retention and pre/post settings with no enforcing code)
- `/Users/gokul/Desktop/vizenlinkvms/nuraeye-rt/mobile_app/packages/camera_api/STREAMING_GUIDE.md` (transport selection, one-peer-per-port, reconnect rules, H.265 limits)
- `camera_api/SETTINGS_API_GUIDE.md` (clock sync state, no RTC, event preferences, clip duration semantics) and `API_REFERENCE.md` (SOAP fault order, header case, camera-ID header/421, PlaybackBusy, bearer sessions, first-contact retry)
- `camera_api/test/` (`case_preserving_http_client_test.dart`, `camera_id_header_test.dart`, `fixtures/`)

**MediaMTX documentation (HIGH for stated facts):**
- https://mediamtx.org/docs/features/record (fMP4 default; last part lost on failure; `recordDeleteAfter`; path variables including `%s`)
- https://mediamtx.org/docs/features/playback (`/list`, `/get`, RFC3339, `fmp4`/`mp4`)
- https://mediamtx.org/docs/features/authentication (internal, HTTP and JWT auth; default `any` user)
- https://mediamtx.org/docs/features/control-api (localhost-only by default)
- https://mediamtx.org/docs/features/webrtc-specific-features (H.265 in Chrome WebRTC limited to Windows + capable GPU; no B-frames; connectivity ladder: UDP 8189, TCP, STUN, TURN)
- https://mediamtx.org/docs/read/hls and https://mediamtx.org/docs/read/webrtc (codec lists)

**Web search results (MEDIUM/LOW):**
- caniuse HEVC page (Chrome and Firefox partial support). Not independently verified per platform.
- MediaMTX issue #4188 (reported duration growth with H.265 segments, v1.11.1). One report, so treat as a hint.
- General fMP4 versus MP4 power-loss behaviour (vendor and FFmpeg mailing-list discussions). Consistent with common knowledge, but not MediaMTX-specific.

**Experience-based `[exp]` items** (Windows hook quoting, Pi throttling, recorder backpressure log text, `hvc1` tag, DHCP reuse, PullPoint expiry) are flagged inline and listed in "Research Flags" for validation.

---
*Pitfalls research for: LAN NVR/VMS for VizenLink/NuraEye cameras*
*Researched: 2026-10-26*
