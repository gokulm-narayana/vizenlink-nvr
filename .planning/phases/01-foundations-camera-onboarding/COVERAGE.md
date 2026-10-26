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
