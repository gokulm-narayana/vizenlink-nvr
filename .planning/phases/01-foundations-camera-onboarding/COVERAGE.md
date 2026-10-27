# API Coverage — VizenLink/NuraEye camera LAN API (NuraEye REST, ONVIF, WS-Discovery)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Surface enumerated from `nuraeye-rt/docs/external-api/camera-rest-api.openapi.yaml` (published 2026-10-21) and the ONVIF operations used by `camera_api/lib/src/lan/onvif/*.dart`. Phase 1 integrates what onboarding, identity and re-IP need; every other capability belongs to a later roadmap phase or is out of v1 scope.

| capability | decision | reason |
|---|---|---|
| ws-discovery-probe (UDP 3702 multicast + unicast) | INTEGRATE | |
| rest:POST /nuraeye/identity | INTEGRATE | |
| rest:POST /nuraeye/session/login | INTEGRATE | |
| rest:POST /nuraeye/session/logout | OPT-OUT | not needed yet: sessions expire on the camera; NVR session lifecycle revisited with the Phase 2 daemon |
| rest:GET /nuraeye/capabilities | INTEGRATE | |
| rest:POST /nuraeye/live-stream-uri | INTEGRATE | |
| rest:GET /nuraeye/health | OPT-OUT | not needed yet: camera health view is SET-07 in Phase 6 |
| rest:GET,POST /nuraeye/wifi; GET /nuraeye/wifi/signal | OPT-OUT | explicitly out of scope: camera Wi-Fi provisioning is owned by the mobile app (REQUIREMENTS Out of Scope) |
| rest:GET /nuraeye/timezones | OPT-OUT | not needed yet: camera time zone editing is SET-01 in Phase 6 |
| rest:GET /nuraeye/cloud/parameters; GET,POST /nuraeye/cloud/streaming | OPT-OUT | explicitly out of scope: cloud/WAN paths are not used by the LAN-only v1 NVR |
| rest:POST /nuraeye/alert-rules/query; POST /nuraeye/alert-rules | OPT-OUT | explicitly out of scope: NVR-side rule authoring is a v1 non-goal |
| rest:GET,POST /nuraeye/events/preferences, /events/response-actions | OPT-OUT | not needed yet: deferred to v1.x (SET-X1) |
| rest:GET,POST /nuraeye/events/loitering-duration, /events/bbox-overlay | OPT-OUT | not needed yet: event tuning belongs to Phase 6 / v1.x |
| rest:GET,POST /nuraeye/audio/recording, /audio/settings, /audio/test-sound | OPT-OUT | not needed yet: audio recording toggle is REC-11 in Phase 2; other audio settings Phase 6 |
| rest:GET,POST /nuraeye/local-storage | OPT-OUT | not needed yet: camera SD settings deferred to v1.x (SET-X1) |
| rest:/nuraeye/recordings (list, dates, delete, clip-duration) | OPT-OUT | not needed yet: SD back-fill is v2 (REC-X1); the NVR records via MediaMTX in Phase 2 |
| rest:GET,POST /nuraeye/recordings/mode | OPT-OUT | not needed yet: camera-side recording mode is Phase 6 settings; NVR recording mode is REC-02 in Phase 2 |
| rest:GET,POST /nuraeye/privacy-mode | OPT-OUT | not needed yet: privacy settings deferred to v1.x (SET-X1) |
| rest:/nuraeye/buzzer and /nuraeye/deterrence (durations, options) | OPT-OUT | not needed yet: manual deterrence is v2 (SET-X2) |
| rest:/nuraeye/video/* (mode, defaults, night-vision, mirror-flip, anti-flicker) | OPT-OUT | not needed yet: imaging settings are SET-03 in Phase 6 |
| rest:GET /nuraeye/preview-key | OPT-OUT | not needed yet: snapshots/gallery are Phase 4/5 |
| rest:POST /nuraeye/talk-uri | OPT-OUT | explicitly out of scope: two-way talk from the NVR is a v1 non-goal |
| onvif:tds:GetDeviceInformation | INTEGRATE | |
| onvif:tds:GetScopes | INTEGRATE | |
| onvif:tds:SetScopes (name, location) | INTEGRATE | |
| onvif:tds:GetNetworkInterfaces | INTEGRATE | |
| onvif:tds:GetServices | INTEGRATE | |
| onvif:tds:SetUser (admin password change) | INTEGRATE | |
| onvif:tds:GetUsers, CreateUsers, DeleteUsers | OPT-OUT | not needed yet: the NVR uses admin and creates no account (D-08); CreateUsers/DeleteUsers appear only in the opt-in hardware test HW-08 as test helpers |
| onvif:tds:GetSystemDateAndTime, SetSystemDateAndTime | OPT-OUT | not needed yet: camera clock sync status is HLTH-09 in Phase 4; camera time settings Phase 6 |
| onvif:tds:SystemReboot | OPT-OUT | not needed yet: camera reboot is SET-05 in Phase 6 |
| onvif:tds:SetSystemFactoryDefault | OPT-OUT | not needed yet: factory reset is SET-06 in Phase 6; used only by the opt-in hardware test HW-04 (Soft) as a test helper |
| onvif:tr2:GetProfiles | INTEGRATE | |
| onvif:tr2:GetStreamUri | INTEGRATE | |
| onvif:tr2 video encoder configs (get, options, set), GetServiceCapabilities | OPT-OUT | not needed yet: encoder settings are SET-02 in Phase 6 |
| onvif:tr2:GetOSDs, GetOSDOptions, CreateOSD, SetOSD, DeleteOSD | OPT-OUT | not needed yet: OSD settings are SET-04 in Phase 6 |
| onvif:tr2:GetMasks, GetMaskOptions, CreateMask, SetMask, DeleteMask | OPT-OUT | not needed yet: privacy masks deferred to v1.x (SET-X1) |
| onvif:tr2 audio source/output configurations (get, set) | OPT-OUT | not needed yet: audio is REC-11 (Phase 2) and Phase 6 settings |
| onvif:timg:GetImagingSettings, GetOptions, SetImagingSettings | OPT-OUT | not needed yet: imaging settings are SET-03 in Phase 6 |
| onvif:trc/tse/trp (recording, search, replay services) | OPT-OUT | not needed yet: camera SD playback/back-fill is v2 (REC-X1) |
| onvif:events PullPoint (create subscription, pull, renew, unsubscribe) | OPT-OUT | not needed yet: event ingestion is EVT-01 in Phase 4 |
| rtsps live streams (port 554/555 DESCRIBE/SETUP/PLAY) | OPT-OUT | not needed yet: recording ingest is Phase 2 via MediaMTX; Phase 1 only selects and stores stream port/path, and the opt-in hardware tests HW-08/09/11 probe RTSPS |

## Revised execution ownership

- 01-01: Dependency review, package lock, configuration and clock primitives; 9 files; wave 1.
- 01-02: Migrated SQLite, runtime and shared status service; 12 files; wave 2.
- 01-03: CLI status tracer, reusable command seams and listener guard; 12 files; wave 3.
- 01-04: UTC storage, site timezone and DST transitions; 7 files; wave 4.
- 01-05: Typed camera core, HTTP transport, WSSE and identity client; 13 files; wave 5.
- 01-06: Loopback TLS simulator and identity tracer; 9 files; wave 6.
- 01-07: HTTP faults, simulator authority, discovery responder and architecture guards; 13 files; wave 7.
- 01-08: Encrypted credential vault and authoritative canary key source; 10 files; wave 5.
- 01-09: Pinned MediaMTX binary and explicit loopback default-deny config; 11 files; wave 8.
- 01-10: Live MediaMTX rejection probes and process cleanup; 7 files; wave 9.
- 01-11: Read-only vendoring and drift tools with bounded batch mode; 4 files; wave 5.
- 01-12: Vendor immutable contract batch 1 of 5; 11 files; wave 6.
- 01-13: Vendor immutable contract batch 2 of 5; 11 files; wave 7.
- 01-14: Vendor immutable contract batch 3 of 5; 11 files; wave 8.
- 01-15: Vendor immutable contract batch 4 of 5; 11 files; wave 9.
- 01-16: Vendor immutable contract batch 5 of 5; 10 files; wave 10.
- 01-17: Finalize full contract lock, behavior catalogue and fixture provenance; 8 files; wave 11.
- 01-18: REST login and authenticated capabilities tracer; 10 files; wave 12.
- 01-19: REST sessions, failure taxonomy and identity retry; 10 files; wave 13.
- 01-20: Capabilities and live-stream URI contracts; 9 files; wave 14.
- 01-21: ONVIF serial tracer and fault-first SOAP mapping; 11 files; wave 12.
- 01-22: ONVIF device operations and Media2 streams; 11 files; wave 13.
- 01-23: Blank-credential discovery, bounded unicast and scan CLI; 10 files; wave 15.
- 01-24: D-11 confirmation, serial registry schema and stream selection; 6 files; wave 15.
- 01-25: Serial-bound configured-camera onboarding and local CLI; 6 files; wave 16.
- 01-26: Stream fallback, capability cache and registry display; 10 files; wave 17.
- 01-27: One-shot factory flow, error taxonomy and atomic add; 8 files; wave 18.
- 01-28: Silent serial-based re-IP recovery; 5 files; wave 18.
- 01-29: Rename, reprobe, credentials and certificate recovery; 11 files; wave 19.
- 01-30: Opt-in real-camera suite and blocking hardware checkpoint; 9 files; wave 20.
- 01-31: Local phase gate, pending OS matrix, leaks and packaging guards; 8 files; wave 20.

All 12 Phase 1 requirements and D-01..D-30 remain binding; tests and external gates remain pending until run.
