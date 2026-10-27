# Deliberate Architectural Divergences from `camera_api`

This document records deliberate, approved differences between the VizenLink NVR Python camera/services implementation and the upstream Dart `camera_api` package.

| ID | `camera_api` Behaviour | NVR Behaviour | Reason | Decision |
|---|---|---|---|---|
| DIV-01 | Assumes RTSP URL returned from `POST /nuraeye/live-stream-uri` | If `live-stream-uri` returns `transport: "webrtc"`, falls back to ONVIF Media2 `GetStreamUri` (Profile_3 excluded) | NVR records via MediaMTX RTSP ingestion; cameras set to WebRTC mode still need RTSP streams for recording | D-23 |
| DIV-02 | Sealed via `CameraSecureStorage` wrapping account passwords | Credentials sealed with AES-GCM and NVR data key (canary protected) in SQLite vault | NVR operates headless without mobile OS keychain; manages multi-tenant camera credentials at rest | D-14 |
| DIV-03 | Connect failures lumped into general failure | `FailureKind.UNREACHABLE` distinct from `GENERIC`, and `TLS_CHANGED` for certificate pin mismatch | Enables discrete recovery loops and alert notifications without false authentication re-prompts | D-02, D-25 |
| DIV-04 | Capabilities parser discards unmodeled fields | Keeps raw JSON `output` plus typed superset (`camera_id_check`, `night_vision_*_capable`) | Preserves forward capability compatibility and hardware feature flags | CAP-05 |
| DIV-05 | Regex matches `retry in (\d+) s` only | Parses `retry_after_seconds` integer field before evaluating regex | Firmware returns structured JSON field in newer revisions; regex serves as fallback | F8 |
| DIV-06 | Username in WSSE UsernameToken not XML-escaped | WSSE username XML-escaped | Prevents XML injection when camera usernames contain special characters (`&`, `<`, `"`) | WSSE-03 |
| DIV-07 | Single socket multicast probe | Multicast probe bound and sent per network interface (`IP_MULTICAST_IF`) | Multi-homed NVR hosts (e.g. eth0 recording LAN, eth1 uplink) must discover cameras across all interfaces | Pitfall 9 |
| DIV-08 | Discovery host parsed from XAddrs URL only | Discovery host extracted from UDP datagram source address | Cameras behind NAT or with misconfigured internal XAddrs URLs broadcast unreachable self-reports | Pitfall 10 |
| DIV-09 | Full subnet unicast sweep | Unicast sweep bounded to `max(prefix, 24)` and one identity retry for WS-Discovery responders | Prevents denial-of-service / socket exhaustion on large enterprise subnets (/16 or /8) | D-27 |
| DIV-10 | Documentation mentions 15 s cap / 5 s straggler | Unicast defaults: 30 s cap, 10 s straggler wait, 50 ms pacing matching actual code | Adheres to verified wire timing in production firmware rather than stale documentation | D-26, F9 |
| DIV-11 | Firmware session table assumed size 6 | NVR bounds active session cache to max 10 concurrent sessions | Accommodates multi-stream multi-camera NVR load while respecting embedded camera limits | D-26, F1 |
| DIV-12 | MAC address format preserved as returned | MAC address strictly normalized to `AA:BB:CC:DD:EE:FF` uppercase colon-separated | Consistent database indexing and UI formatting across diverse ONVIF firmware outputs | DEV-03 |
| DIV-13 | Process-wide global session cache | Scoped session manager per camera connection instance | Prevents cross-tenant connection pollution and memory leaks in long-running services | Pitfall 15 |
