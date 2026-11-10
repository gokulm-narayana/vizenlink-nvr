# VizenLink Camera — REST API Reference

Version 1.0 · 2026-10-21 · describes camera firmware build 20261019 and later.

This is the camera's own HTTP API, served on the same HTTPS port as ONVIF. It is the way the VizenLink app configures a camera on the local network, and it is available to any client. It covers settings and actions that ONVIF does not: recording schedules and clip management, alert and event preferences, deterrence outputs (siren, spotlight, warning), audio gain and speaker volume, privacy mode, health and diagnostics, and discovery of the live-video and two-way-talk endpoints. For NVR/VMS interoperability use the ONVIF API ([camera-onvif-api.md](camera-onvif-api.md)); the machine-readable description of this API is [camera-rest-api.openapi.yaml](camera-rest-api.openapi.yaml).

Every request and response below is a literal example with the real field names. Example values (addresses, tokens, digests) are illustrative.

## Conventions

* **Base URL.** `https://<camera-ip>/nuraeye/...`, port 443, self-signed certificate (your client must accept it; very strict TLS stacks may need a lower minimum security level).
* **JSON everywhere.** Every response, success or failure, has a JSON body. Success: `{"error_code": 0, "error_msg": "Success", "output": {...}}`. Failure: `error_code` equals the HTTP status code and `error_msg` explains it.
* **Authentication.** Sign in once (`POST /nuraeye/session/login`, below) and send `Authorization: Bearer <token>` on every other request. Only `POST /nuraeye/identity` and the login call need no token.
* **Methods.** `GET` and `POST` only. Reads that need input are `POST` with a JSON body, like writes; the exceptions are the range filters on `GET /nuraeye/recordings` and `GET /nuraeye/recordings/dates`.
* **Roles.** The camera has one `Administrator` and up to four `Operator` / `User` accounts. Each route has a minimum role; a lower role gets `403`.
* **Capabilities first.** Read `GET /nuraeye/capabilities` once and build your UI from it. Features differ between models, and ranges (clip duration, schedule windows, loitering duration) are reported there, not fixed.
* **Camera identity check.** You may send `X-VizenLink-Camera-Id: <serial number>` on any request; a different serial is answered `421` before anything runs (see "Camera-ID check").
* **Not covered here.** ONVIF SOAP ([camera-onvif-api.md](camera-onvif-api.md)) and the remote (internet) control channel ([camera-wan-mqtt-api.md](camera-wan-mqtt-api.md)).

---

## Auth: bearer-token sessions

**POST `/nuraeye/session/login`** — trades the same one-time WSSE-style SHA-1 digest that ONVIF uses for a bearer token, so later requests do not recompute a digest per call.

**Request:**
```json
{
  "auth_credentials": {
    "username": "admin",
    "password_digest": "Z8n1c8b3s7fLp9k1x2y3zA4B5c6=",
    "nonce": "MTIzNDU2Nzg5MGFiY2RlZg==",
    "created": "2026-07-31T10:15:00.000Z"
  },
  "client_label": "Mom's iPhone"
}
```
(`client_label` is optional and for display and audit only; it is never a security boundary.) Digest formula: `password_digest = Base64( SHA1(
Base64Decode(nonce) + created + <device password> ) )`. Wrong username/digest → `401`.

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "token": "3f9a2b7c1e4d4a6b9c0d8f21a4b5c6d7",
    "expires_in_sec": 1800,
    "username": "admin",
    "role": "Administrator",
    "password_change_required": false
  }
}
```
`username`/`role`: the camera account the session belongs to and its role (`Administrator`, `Operator` or `User`); the camera holds up to 5
accounts (see "Roles and `403`" below), so the `username` in the request may be any of them. `token` is 32 lowercase hex chars (16 random bytes). The camera keeps a
fixed-size array of **10 slots** — a login
past the 10th evicts the least-recently-used live session rather than being rejected; household-scale, not enterprise. Idle timeout **30 minutes**
refreshed on every validated request.

**POST `/nuraeye/session/logout`** — revokes the session named by the request's own
`Authorization: Bearer <token>` header. Idempotent — revoking an already-unknown/expired token
is not an error. No request body.

**Response:** shared success body,
`{ "error_code": 0, "error_msg": "Success", "output": { "status": true } }`.

**Every other endpoint below requires an `Authorization: Bearer <token>` header from a live
session** — checked once centrally before
dispatch, so it applies uniformly to all of them even though it isn't re-derived per handler in
source. Missing/invalid/expired token → `401`, body
`{ "error_code": 401, "error_msg": "Missing or invalid session token", "output": {} }`. Every
example below shows the header explicitly (`<token>` = a value obtained from `POST
nuraeye/session/login` above) so it isn't easy to miss.

## Error shape

Every failure (authentication, validation or internal error) returns a JSON body in which **`error_code` equals the HTTP status code**.

**Example error response:**
```json
{
  "error_code": 400,
  "error_msg": "Missing or malformed enabled",
  "output": {}
}
```
An unrecognized `/nuraeye/*` path → `404` `"Unknown REST resource"`. A recognized resource with
the wrong HTTP method → `405` `"Method not allowed on this resource"`.

## First-password gate

In a build that forces the first password change (always in production), a camera whose Administrator still has the factory-default password (`password`) serves only the basics: the no-login ONVIF actions
(`GetDeviceInformation`, `GetCapabilities`,...), `POST /nuraeye/identity`, `POST /nuraeye/session/login`, `GET /nuraeye/capabilities`, and the Administrator's own password change (ONVIF `SetUser`, WAN `SetUserPassword`).
Every other request answers **HTTP `428 Precondition Required`** until that change succeeds:
```json
{
  "error_code": 428,
  "error_msg": "Set a new Administrator password first",
  "reason": "password_change_required",
  "output": {}
}
```
`POST /nuraeye/session/login` still succeeds and says so in its `output`: `"password_change_required": true`. `GET /nuraeye/capabilities` carries `default_password_in_use`. `/snapshot` and the recording clip route answer 428 with no body;
RTSP/RTSPS never authenticates (no stream); WAN commands answer `error_code` 428. The new password may not be `password` (`reason: password_not_allowed`). After the change everything works normally.

## Roles and `403`

The camera holds up to **5 accounts**: exactly one Administrator (the owner; a third-party NVR/VMS
uses this account too) and up to four Operator/User accounts. The session created by `POST /nuraeye/session/login` remembers which account logged in, and every route
below requires a minimum role:

| Role | May |
|---|---|
| `User` | read settings and status, watch live video (`live-stream-uri`, `cloud/streaming`, `preview-key`), list and download recordings, `GET /snapshot` |
| `Operator` | + change runtime behaviour: privacy mode, video image settings, audio settings/recording/test sound, buzzer/deterrence and their durations, event preferences/response actions, loitering duration, bounding-box overlay, alert rules, two-way talk (`talk-uri`) |
| `Administrator` | + Wi-Fi (`/nuraeye/wifi`, which also exposes the passphrase), local storage, recording mode/clip duration/delete, cloud parameters, debug logs, movement-protection sensitivity and calibrate (`/nuraeye/movement-protection`, not yet classified so Administrator-only by default), firmware upgrade, accounts |

A route that is not classified is Administrator-only. When an account's role is below the route's, the answer is **HTTP `403`** — never `401`, which means "log in again":

**Too many failed sign-ins.** After 5 consecutive failed digests for one account from one address (the Administrator: shorter blocks) `POST /nuraeye/session/login`
answers **HTTP 429** — even for the correct password — until the block ends; other accounts are unaffected:
```json
{
  "error_code": 429,
  "error_msg": "Too many failed sign-in attempts",
  "reason": "too_many_attempts",
  "retry_after_seconds": 60,
  "output": {}
}
```
Blocks are 60 s, doubling to 15 minutes; the Administrator's are 15 s, at most 30 s. A success or 15 quiet minutes clears the count. `/snapshot` answers 429 the same way (no body).

**Example error response:**
```json
{
  "error_code": 403,
  "error_msg": "Not permitted for this user role",
  "reason": "role_not_permitted",
  "output": {}
}
```
The session stays valid. Accounts are managed over ONVIF (`CreateUsers`/`DeleteUsers`/`SetUser`/`GetUsers`, see [Camera-ONVIF-API.md](camera-onvif-api.md)) and, over WAN, by the
`ListUsers`/`CreateUser`/`DeleteUser`/`SetUserLevel`/`SetUserPassword` commands (below); there is no REST endpoint for them. `GET /nuraeye/capabilities` reports `multi_user`,
`max_users` and `user_roles`. Changing an account's password or level, or deleting it, ends only that account's sessions; changing the Administrator's password ends all of them.
`GET /snapshot` and the dev-only NN endpoints use the same digest `Authorization` header and answer `401`/`403` the same way.

## Camera-ID check (`421`)

A NuraEye client may add the HTTP request header
`X-VizenLink-Camera-Id: <serial number>` (the value `GetDeviceInformation` reports as `SerialNumber`) to any request on the main HTTPS server — REST, `/snapshot` and every ONVIF endpoint. The camera compares it with its own serial **before routing and before authentication**:

- header **absent or empty** -> no comparison, handled exactly as before (generic third-party ONVIF NVR/VMS clients are unaffected);
- header equal (exact, case-sensitive, surrounding whitespace ignored) -> handled as before;
- header **different** -> **HTTP `421 Misdirected Request`**, nothing executed, no authentication attempted, so a wrong camera with a different password
 also answers `421`, not `401`. The camera's own serial is never in the reply. A camera with an empty (unprovisioned) serial never refuses.

**Example error response:**
```json
{
  "error_code": 421,
  "error_msg": "Camera ID mismatch"
}
```
ONVIF paths get the same status with a SOAP 1.2 `Receiver` fault, reason "Camera ID mismatch" (see [Camera-ONVIF-API.md](camera-onvif-api.md)).
RTSP/RTSPS requests are **not** checked. The id is not a secret — this prevents a request reaching the wrong camera by accident (a router handing one
camera's IP to another), not an attack.

## Firmware upgrade in progress (`503`)

From the moment a firmware upload really starts (`POST /onvif/firmware_upload` with a valid token) until the camera reboots,
**every other HTTP request is refused**: `/nuraeye/*`, `/snapshot` and every other non-ONVIF path get **HTTP `503`** with:

**Example error response:**
```json
{
  "error_code": 503,
  "error_msg": "Firmware upgrade in progress"
}
```
(`error_code` equals the HTTP status, as for every other error.) While this state lasts the camera also stops local recording (the open MP4
is finalized), pauses NN inference and stops cloud streaming. It ends only by a reboot — the upload completing (normal firmware-upgrade
reboot) or failing/aborting (reboot with `reboot_reason` `"OTA Aborted"`; also if no upload data arrives for 60 s). Clients should treat `503`
with this message as "try again after the camera has rebooted (~45 s)".

## Endpoints

- **[Identity & Discovery](#identity--discovery)**
 - [`POST /nuraeye/identity` — unauthenticated](#post-nuraeyeidentity--unauthenticated)
- **[Network & Connectivity](#network--connectivity)**
 - [`/nuraeye/wifi`, `/nuraeye/wifi/signal`](#nuraeyewifi-nuraeyewifisignal)
 - [`GET /nuraeye/timezones`](#get-nuraeyetimezones)
 - [`GET /nuraeye/cloud/parameters`](#get-nuraeyecloudparameters)
 - [`GET /nuraeye/capabilities`](#get-nuraeyecapabilities)
- **[Alerts](#alerts)**
 - [`POST /nuraeye/alert-rules/query`](#post-nuraeyealert-rulesquery)
 - [`POST /nuraeye/alert-rules`](#post-nuraeyealert-rules)
 - [`/nuraeye/events/preferences`](#nuraeyeeventspreferences)
 - [`/nuraeye/events/response-actions`](#nuraeyeeventsresponse-actions)
 - [`/nuraeye/events/loitering-duration`](#nuraeyeeventsloitering-duration)
 - [`/nuraeye/events/bbox-overlay`](#nuraeyeeventsbbox-overlay)
- **[Audio](#audio)**
 - [`/nuraeye/audio/recording`](#nuraeyeaudiorecording)
 - [`/nuraeye/audio/settings`](#nuraeyeaudiosettings)
 - [`/nuraeye/audio/test-sound`](#nuraeyeaudiotest-sound)
- **[Storage](#storage)**
 - [`/nuraeye/local-storage`](#nuraeyelocal-storage)
 - [`/nuraeye/recordings`](#nuraeyerecordings)
 - [`/nuraeye/recordings/{id}/clip`](#nuraeyerecordingsidclip)
 - [`/nuraeye/recordings/clip-duration`](#nuraeyerecordingsclip-duration)
 - [`/nuraeye/recordings/delete`](#nuraeyerecordingsdelete)
 - [`/nuraeye/recordings/mode`](#nuraeyerecordingsmode)
 - [`GET /nuraeye/recordings/dates`](#get-nuraeyerecordingsdates)
- **[Privacy](#privacy)**
 - [`/nuraeye/privacy-mode`](#nuraeyeprivacy-mode)
- **[Video & Image](#video--image)**
 - [`GET /nuraeye/video/mode`](#get-nuraeyevideomode)
 - [`/nuraeye/video/night-vision-type`](#nuraeyevideonight-vision-type)
 - [`/nuraeye/video/mirror-flip`](#nuraeyevideomirror-flip)
 - [`/nuraeye/video/anti-flicker`](#nuraeyevideoanti-flicker)
 - [`GET /nuraeye/video/image-defaults`](#get-nuraeyevideoimage-defaults)
- **[Streaming](#streaming)**
 - [`GET /nuraeye/preview-key`](#get-nuraeyepreview-key)
 - [`POST /nuraeye/live-stream-uri`](#post-nuraeyelive-stream-uri)
 - [`POST /nuraeye/talk-uri`](#post-nuraeyetalk-uri)
 - [`/nuraeye/cloud/streaming`](#nuraeyecloudstreaming)
- **[Deterrence & Alarms](#deterrence--alarms)**
 - [`/nuraeye/buzzer`](#nuraeyebuzzer)
 - [`/nuraeye/deterrence`](#nuraeyedeterrence)
 - [`/nuraeye/deterrence/durations`](#nuraeyedeterrencedurations)
 - [`/nuraeye/deterrence/durations/options`](#nuraeyedeterrencedurationsoptions)
- **[Health](#health)**
 - [`GET /nuraeye/health`](#get-nuraeyehealth)
 - [`/nuraeye/movement-protection`](#nuraeyemovement-protection)
 - [`POST /nuraeye/movement-protection/calibrate`](#post-nuraeyemovement-protectioncalibrate)

## Identity & Discovery

### `POST /nuraeye/identity` — unauthenticated

Lets a client tell a genuine VizenLink camera apart from an arbitrary web server during WS-Discovery, using a fixed challenge string rather than the device's real password. **POST + JSON body, not
GET + query params** — an earlier version of this endpoint used query params (since GET requests
don't carry a body on this HTTP stack), moved to POST so the challenge fields never end up in a
URL that could be logged/cached, and so this endpoint's input plumbing matches every other REST
endpoint in this API instead of being a one-off exception.

**Request:**
```
POST /nuraeye/identity HTTP/1.1
Content-Type: application/json

{
  "nonce": "MTIzNDU2Nzg5MGFiY2RlZg==",
  "created": "2026-07-31T10:15:00.000Z",
  "digest": "<digest of fixed literal \"are-you-onchip-nuraeye\">"
}
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "reply": "<digest of fixed literal \"yes-i-am-onchip-nuraeye\", same nonce/created>"
  }
}
```
Missing `nonce`/`created`/`digest` → `400`. Digest mismatch → `401`.

## Network & Connectivity

### `/nuraeye/wifi`, `/nuraeye/wifi/signal`

**GET `/nuraeye/wifi`**:

**Request:**
```
GET /nuraeye/wifi HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "ssid": "MyHomeWiFi",
    "psk": "SuperSecret123"
  }
}
```
No credentials stored (Ethernet-connected, or never WiFi-provisioned) → same shape with empty
strings, not an error.

**POST `/nuraeye/wifi`** (`verify` is optional, default `true`; if the camera is currently on Ethernet the credentials are only saved and no connection is attempted):

**Request:**
```
POST /nuraeye/wifi HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "ssid": "MyHomeWiFi",
  "psk": "SuperSecret123",
  "verify": true
}
```

**Response:** shared success body. `500` if the save itself fails.

**GET `/nuraeye/wifi/signal`**:

**Request:**
```
GET /nuraeye/wifi/signal HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "rssi": "-52",
    "snr": "38"
  }
}
```

### `GET /nuraeye/timezones`

Curated static catalog,.

**Request:**
```
GET /nuraeye/timezones HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "timezones": [
      {
        "code": "UTC",
        "name": "Coordinated Universal Time (UTC)"
      },
      {
        "code": "IST-5:30",
        "name": "India Standard Time - Kolkata (UTC+05:30)"
      },
      {
        "code": "JST-9",
        "name": "Japan Standard Time - Tokyo (UTC+09:00)"
      },
      {
        "code": "CST-8",
        "name": "China Standard Time - Shanghai (UTC+08:00)"
      },
      {
        "code": "GMT",
        "name": "Greenwich Mean Time - London (UTC+00:00)"
      },
      {
        "code": "EST5",
        "name": "Eastern Time - New York (UTC-05:00)"
      },
      {
        "code": "PST8",
        "name": "Pacific Time - Los Angeles (UTC-08:00)"
      }
    ]
  }
}
```

### `GET /nuraeye/cloud/parameters`

Returns the camera's cloud connection parameters: the AWS IoT broker endpoint and the Kinesis Video Streams stream name. A client uses them when it sets up remote access.

**Request:**
```
GET /nuraeye/cloud/parameters HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "iot_broker_endpoint": "a1b2c3d4e5f6g7-ats.iot.us-east-1.amazonaws.com",
    "kvs_stream_name": "vizenlink-oc2026073100123"
  }
}
```
AWS disabled at build time → `501` `"AWS disabled in this build"`.

### `GET /nuraeye/capabilities`

**Consolidated capability endpoint**: every "is X supported on this unit" flag in the REST API is reported here. A client calls this endpoint once (for example at start-up or when a settings screen opens) to learn which controls to show.

**Request:**
```
GET /nuraeye/capabilities HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "wan_command_capable": true,
    "wan_live_view_capable": true,
    "siren_capable": true,
    "spotlight_capable": true,
    "warning_capable": false,
    "local_storage_capable": true,
    "recording_clip_duration_min_seconds": 10,
    "recording_clip_duration_max_seconds": 300,
    "supported_recording_modes": ["continuous", "scheduled", "event_triggered"],
    "max_recording_schedule_windows": 14,
    "loitering_duration_min_seconds": 5,
    "loitering_duration_max_seconds": 300,
    "bbox_overlay_capable": true,
    "kvs_e2e_encryption": true,
    "accelerometer_capable": true,
    "supported_movement_sensitivities": ["low", "medium", "high"],
    "movement_sensitivity_descriptions": [
      "Alerts only on a big movement: about 35 degrees of tilt or a hard hit. Best outdoors or in wind.",
      "Alerts on a clear movement: about 25 degrees of tilt or a firm knock.",
      "Alerts on a small movement: about 15 degrees of tilt or a light touch. May give false alerts in wind."
    ],
    "night_vision_color_capable": true,
    "night_vision_smart_capable": false,
    "supported_event_types": ["VideoModeChanged", "PrivacyModeChanged", "PersonDetected"],
    "supported_event_deterrence_options": {
      "PersonDetected": ["siren", "spotlight", "mobile_alert"]
    },
    "camera_id_check": true,
    "multi_user": true,
    "max_users": 5,
    "user_roles": ["Operator", "User"],
    "default_password_in_use": true
  }
}
```

`default_password_in_use` is `true` while the Administrator still has the factory-default password (`password`): a client must force a password change when it adds such a camera.
The Administrator is always named `admin` and cannot be renamed; no account — Administrator included — may be set to the default password (refused with `reason: password_not_allowed` /
ONVIF `ter:PasswordNotAllowed`).

`recording_clip_duration_min_seconds`/`max_seconds` is the valid
range for `POST /nuraeye/recordings/clip-duration` below (see that endpoint's own note). `0`/`0` on firmware too old to report it, or with no
local-storage capability at all.

`supported_recording_modes` is this model's recording-mode capability
set, rendered as the same wire-string vocabulary `GET`/`POST /nuraeye/recordings/mode` below use
(`continuous`/`scheduled`/`event_triggered`) — only meaningful when `local_storage_capable` is
true, reported unconditionally anyway matching this endpoint's own "always emit" style.

`camera_id_check` is `true` when this firmware honours the optional `X-VizenLink-Camera-Id`
request header (and the WAN `camera_id` field) — see "Camera-ID check (`421`)" below. Always `true` on firmware that has the field; a client that
does not see the field should assume the firmware predates the check and not rely on it.

`max_recording_schedule_windows` is the maximum total number of entries the `schedule` array in `POST /nuraeye/recordings/mode` (Scheduled mode) may contain. `Set` rejects a longer `schedule`. It is always reported.

`loitering_duration_min_seconds`/`max_seconds` is the valid range for `POST /nuraeye/events/loitering-duration` below. It is always reported, even when detection is not active.

`bbox_overlay_capable` reports whether this firmware
build has a real detection pipeline to draw a box for — gated on the `AI_DETECTIONS` build
config, unlike the loitering bounds. The current on/off *value* is read/
written via `GET`/`POST /nuraeye/events/bbox-overlay` below, not here.

`kvs_e2e_encryption` is `true` when the firmware was built with the option (the default) and every video and audio frame it sends to the cloud for WAN live view and clips is
encrypted on the camera, `false` otherwise. A client reads it once on the local network and caches it: `true` means decrypt every frame with the camera's shared key (`GET /nuraeye/preview-key`) and drop a plain one; `false` means play the stream as plain video.
The short WAN `GetCapabilities` reply (command 29) carries it too, so a phone that was never on the camera's network can read it over the internet.

`accelerometer_capable` is `true` when the accelerometer is built in and enabled
(build option `accelerometer: enabled`, `-DACCELEROMETER`) and `false` otherwise (`7299`, from
). It does **not** say whether the sensor is currently working — that is `sensor` in
`GET /nuraeye/movement-protection`. A client shows the Movement protection settings only when this is `true`.

`supported_movement_sensitivities` is the list of sensitivity level names this camera offers — the camera is the single source of
truth, so a client builds its control from this list and never hardcodes the names. Empty (`[]`) when the accelerometer is not built in.
The current level is `sensitivity` in `GET /nuraeye/movement-protection`; a value for `POST` must be one of these names.

`movement_sensitivity_descriptions` is a one-sentence plain-language hint for each level, in the same order as `supported_movement_sensitivities`
. A client shows the hint of the selected level next to the choice so the user can tell what each level means (a lower level
needs a bigger movement before an alert is sent), and never writes this text itself. Empty (`[]`) when the accelerometer is not built in.

`supported_event_types` is the list of alert event
strings this specific firmware build actually generates — the same identifiers used as this
endpoint's own alert JSON `"event"` field, and as the keys for `/nuraeye/events/preferences`
below. Clients build their alert-settings toggle list from this array only, never a hardcoded
one. A future firmware that generates a new alert type adds a new string here, with no endpoint change required.

`supported_event_deterrence_options` is an object
keyed by **detection-type** event only (a strict subset of `supported_event_types`'s keys —
`VideoModeChanged`/`PrivacyModeChanged` never appear here, since state-change events aren't
eligible for automatic response actions at all), valued with the response actions eligible for
that event type — the intersection of this model's hardware capability (the `siren_capable`/
`spotlight_capable`/`warning_capable` flags above) with a firmware-maintained eligibility table.
`mobile_alert` is always eligible for any listed event type (no hardware gate — it's purely
advisory, see `/nuraeye/events/response-actions` below). `warning` is absent above because
`warning_capable` is `false` on this example camera — the intersection working as designed.

## Alerts

### `POST /nuraeye/alert-rules/query`

Read counterpart to `POST /nuraeye/alert-rules` (write, below). **POST + JSON body, not GET +
query params** — same rationale as `/nuraeye/identity` above; needs a distinct path from
`/nuraeye/alert-rules` since both are now POST and can't share one path the way a GET/POST pair
on the same path would.

**Request:**
```
POST /nuraeye/alert-rules/query HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "rule": "MyPersonDetectorRule"
}
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "mobile_notifications": true,
    "buzzer_activation": false
  }
}
```
Rule not found → `404`.

### `POST /nuraeye/alert-rules`

Write-only — no `GET` counterpart, unchanged in shape.

**Request:**
```
POST /nuraeye/alert-rules HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "rule": "MyPersonDetectorRule",
  "mobile_notifications": true,
  "buzzer_activation": true
}
```

**Response:** shared success body. Rule not found → `404`; save failure → `500`.

### `/nuraeye/events/preferences`

**Not to be confused with `/nuraeye/alert-rules` above** — that controls what *action* a
specific detection *rule* triggers when it fires (`mobile_notifications`/`buzzer_activation`).
This resource controls whether an alert *type* is generated **at all**, device-wide, independent
of any rule. Disabling a type here suppresses it at the source
 — before it reaches either the NuraEye MQTT alert topic or the ONVIF
PullPoint event feed, so a third-party NVR/VMS client stops receiving it too, not just this API.

**GET**:

**Request:**
```
GET /nuraeye/events/preferences HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "VideoModeChanged": true,
    "PrivacyModeChanged": true,
    "PersonDetected": true,
    "Loitering": true,
    "Tamper": true
  }
}
```
(`Tamper` appears only on a camera with the accelerometer.) Keys are exactly the strings `GET /nuraeye/capabilities`'s `supported_event_types` reports —
only alert types this build actually generates appear here.

**POST** — **partial update**, only the keys
present in the request body change:

**Request:**
```
POST /nuraeye/events/preferences HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "VideoModeChanged": false
}
```

**Response:** shared success body. A key not in `supported_event_types` → `400`
`"Unrecognized event type key"` (catches a typo or a client using a stale type name from an
older firmware build, rather than silently ignoring it) — the whole request is rejected, no
partial application. Malformed/non-JSON body → `400` `"Invalid JSON body"`; save failure →
`500`.

### `/nuraeye/events/response-actions`

**Not to be confused with `/nuraeye/events/preferences` above** — that controls whether an
event *type* is generated at all; this controls what happens *in addition* once an
already-enabled **detection-type** event fires.
Also distinct from `/nuraeye/alert-rules` (per-*rule* action toggles) and the manual, on-demand
`/nuraeye/deterrence` action (a human firing an action right now for a chosen duration — this
resource is the camera auto-firing an action because a detection event just happened, with a
firmware-chosen duration).

Only detection-type event types accept a body key here — state-change events
(`VideoModeChanged`/`PrivacyModeChanged`) are never valid keys, matching
`supported_event_deterrence_options`'s key set on `GetCapabilities`.

**GET**:

**Request:**
```
GET /nuraeye/events/response-actions HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "PersonDetected": ["mobile_alert", "warning"]
  }
}
```
Keys are exactly the detection-type strings `GET /nuraeye/capabilities`'s
`supported_event_deterrence_options` reports; each value is the currently-selected subset of
that type's eligible actions.

**POST** — **partial update**, only the
keys present in the request body change, and each key's array **fully replaces** that event
type's action set (not additive):

**Request:**
```
POST /nuraeye/events/response-actions HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "PersonDetected": ["siren", "mobile_alert"]
}
```

**Response:** shared success body. A key that isn't a detection-eligible event type → `400`
`"Unrecognized or non-eligible event type key"`; a non-array value → `400`
`"Expected an array of action strings"`; an action not in that type's eligible set (per
`supported_event_deterrence_options`) → `400` `"Action not eligible for this event type"` — in
every case the whole request is rejected, no partial application. Malformed/non-JSON body →
`400` `"Invalid JSON body"`; save failure → `500`.

`mobile_alert` carries no device-side effect — including/excluding it never changes whether the
camera delivers the event (`/nuraeye/events/preferences` alone governs that). It's read by the
receiving app to decide locally whether to surface a system push notification. `siren`/
`spotlight`/`warning` are real physical device actions the camera auto-triggers when the event
fires, using a firmware-chosen duration (no `duration_seconds` param, unlike the manual
`/nuraeye/deterrence` action).

### `/nuraeye/events/loitering-duration`

mirrors `/nuraeye/recordings/clip-duration`'s exact
simple-integer-preference shape. Valid range is `GET /nuraeye/capabilities`'s
`loitering_duration_min_seconds`/`max_seconds` — never hardcoded client-side.

**GET:**

**Request:**
```
GET /nuraeye/events/loitering-duration HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "loitering_duration_seconds": 30
  }
}
```

**POST:**

**Request:**
```
POST /nuraeye/events/loitering-duration HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "loitering_duration_seconds": 30
}
```

**Response:** shared success body. Missing/malformed `loitering_duration_seconds` → `400`
`"Missing or malformed loitering_duration_seconds"`; out of the `GetCapabilities`-reported
range → `400` `"loitering_duration_seconds out of range"`; save failure → `500`.

### `/nuraeye/events/bbox-overlay`

mirrors `/nuraeye/audio/recording`'s exact simple
boolean-toggle shape. Whether this build has a real detection pipeline to
draw a box for at all lives on `GET /nuraeye/capabilities`'s `bbox_overlay_capable` — this pair
only reads/writes the current on/off value.

**GET:**

**Request:**
```
GET /nuraeye/events/bbox-overlay HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "enabled": true
  }
}
```

**POST:**

**Request:**
```
POST /nuraeye/events/bbox-overlay HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "enabled": true
}
```

**Response:** shared success body. Missing/malformed `enabled` → `400`
`"Missing or malformed enabled"`; save failure → `500`.

## Audio

### `/nuraeye/audio/recording`

**GET**:

**Request:**
```
GET /nuraeye/audio/recording HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "enabled": true
  }
}
```
**POST**:

**Request:**
```
POST /nuraeye/audio/recording HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "enabled": true
}
```

**Response:** shared success body.

### `/nuraeye/audio/settings`

**Consolidated microphone gain + speaker volume endpoint.** Both fields are optional on `POST` — a caller can change just one
without needing to know or resend the other's current value.

**GET**:

**Request:**
```
GET /nuraeye/audio/settings HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "mic_gain": 70,
    "speaker_volume": 60
  }
}
```
**POST** (each of `mic_gain`/`speaker_volume` 0-100, `400` if out of range
or if neither is provided):

**Request:**
```
POST /nuraeye/audio/settings HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "mic_gain": 70,
  "speaker_volume": 60
}
```

**Response:** shared success body.

### `/nuraeye/audio/test-sound`

Speaker volume/output test — not a deterrence mechanism, just plays a known clip so a client can verify audio output.

**GET**:

**Request:**
```
GET /nuraeye/audio/test-sound HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "playing": true
  }
}
```
**POST**:

**Request:**
```
POST /nuraeye/audio/test-sound HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "active": true
}
```
`{ "active": false }` to stop.

**Response:** shared success body.

## Storage

### `/nuraeye/local-storage`

**GET**. Reports live status only; whether storage is supported is `local_storage_capable` in `GET /nuraeye/capabilities`:

**Request:**
```
GET /nuraeye/local-storage HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "enabled": true,
    "card_present": true,
    "capacity_bytes": 32017047552,
    "free_bytes": 18271092736
  }
}
```
**POST**:

**Request:**
```
POST /nuraeye/local-storage HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "enabled": true
}
```

**Response:** shared success body. `500` if capability absent or no card.

### `/nuraeye/recordings`

**GET** — lists recorded clips held on
local SD storage. `storage_available`/`card_present` mirror `/nuraeye/local-storage`'s own
convention rather than a non-200 status — the only two states this endpoint itself can
meaningfully report (a genuinely unreachable camera never returns any HTTP response at all).
Optional `start`/`end` query params (UTC epoch seconds) scope the list to a time range. `trigger`
is present only when a matching event was found in the camera's recent (last ~100 events,
RAM-only) alert history — its absence does not mean nothing happened, just that it's outside
that window. `truncated: true` means more clips exist in range than fit in one response —
narrow with `start`/`end` rather than expecting pagination:

**Request:**
```
GET /nuraeye/recordings?start=1755950000&end=1756000000 HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "storage_available": true,
    "card_present": true,
    "recordings": [
      {
        "id": 1755962400,
        "start": 1755962400,
        "end": 1755962460,
        "size_bytes": 15400000,
        "active": false,
        "trigger": "PersonDetected"
      }
    ],
    "truncated": false
  }
}
```

### `/nuraeye/recordings/{id}/clip`

**GET** — returns the clip as a raw binary MP4 file, not a JSON resource, so it is not described in the OpenAPI file. A clip can be tens of MB. It is authenticated with the same bearer-session
token as every other `/nuraeye/*` endpoint. `{id}` is the `id` field from
`GET /nuraeye/recordings`'s response. Supports standard HTTP `Range: bytes=X-Y` byte-request
headers for seeking within the clip — `206 Partial Content` with `Content-Range`/`Content-Length`
when a `Range` header is present, `200 OK` with the full file otherwise. `404` for an unknown/
stale id (e.g. already deleted by the camera's own storage-retention cleanup).

**Request:**
```
GET /nuraeye/recordings/1755962400/clip HTTP/1.1
Authorization: Bearer <token>
Range: bytes=1048576-2097151
```

**Response:**
```
HTTP/1.1 206 Partial Content
Content-Type: video/mp4
Accept-Ranges: bytes
Content-Range: bytes 1048576-2097151/15400000
Content-Length: 1048576

<binary MP4 data>
```

### `/nuraeye/recordings/clip-duration`

The recorded-clip (segment) duration is configurable. A change applies to the *next* segment rotation; the segment currently being written keeps its original length. The valid range is `recording_clip_duration_min_seconds`/`max_seconds` in `GET /nuraeye/capabilities` (10-300 s by default), so there is no separate options endpoint for this setting.

**GET**:

**Request:**
```
GET /nuraeye/recordings/clip-duration HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": { "clip_duration_seconds": 60 }
}
```

**POST**:

**Request:**
```
POST /nuraeye/recordings/clip-duration HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "clip_duration_seconds": 120
}
```

**Response:** shared success body. `400` if outside the capability-reported min/max range, or if
this build has no local-storage capability at all.

### `/nuraeye/recordings/delete`

"delete all or like select multiple and delete
also." One bulk delete primitive rather than separate endpoints: pass `ids` to delete specific
clips, or `delete_all: true` to delete everything on the card. The clip currently being recorded
is never deleted, even if its id is in `ids` or `delete_all` is set — it is silently skipped,
not treated as an error.

**POST**:

**Request (specific clips):**
```
POST /nuraeye/recordings/delete HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "ids": [1755962400, 1755962460]
}
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": { "deleted": [1755962400, 1755962460], "deleted_count": 2 }
}
```

**Request (delete all):**
```
POST /nuraeye/recordings/delete HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "delete_all": true
}
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": { "deleted_count": 17 }
}
```

`400` if neither `ids` nor `delete_all` is present, or the request body is malformed. An id in
`ids` that no longer exists (already deleted, or never existed) is silently skipped — not
reported as an error, not counted in `deleted`/`deleted_count`.

### `/nuraeye/recordings/mode`

— local SD recording mode: `continuous` (always-on when enabled,
pre-existing default behavior), `scheduled` (a set of weekly day/time windows), or
`event_triggered` (only while a configured detection event is active — see
`event_trigger_source_configured` below). Which modes this model supports is
`GET /nuraeye/capabilities`'s `supported_recording_modes` array — never hardcoded client-side.

**GET**:

**Request:**
```
GET /nuraeye/recordings/mode HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "mode": "scheduled",
    "schedule": [
      { "day_of_week": 1, "start_minute": 480, "end_minute": 1020 }
    ],
    "event_trigger_source_configured": false
  }
}
```
`schedule` is only meaningful for `mode: "scheduled"`, but reported unconditionally (empty array
otherwise) matching this endpoint's own "always emit" style. `day_of_week` is `0`=Sunday..
`6`=Saturday; `start_minute`/`end_minute` are minutes since local midnight, no overnight wrap in
v1 (express an overnight window as two entries instead).
`event_trigger_source_configured` is only meaningful for `mode: "event_triggered"`
— whether at least one detection-event source is actually wired up to trigger recording — also
reported unconditionally.

**POST**:

**Request:**
```
POST /nuraeye/recordings/mode HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "mode": "scheduled",
  "schedule": [
    { "day_of_week": 1, "start_minute": 480, "end_minute": 1020 }
  ]
}
```
`schedule` is required (and parsed) only when `mode` is `"scheduled"` — ignored otherwise.

**Response:** shared success body. Missing/malformed `mode` → `400` `"Missing or malformed
mode"`; unrecognized `mode` string → `400` `"Unrecognized mode"`; `mode` not in this model's
`supported_recording_modes`, or an invalid schedule → `500` `"Mode not supported on this model, or
invalid schedule"`; save failure → `500` `"Failed to save configuration"`.

### `GET /nuraeye/recordings/dates`

for a mobile date-picker: which UTC calendar dates have at least
one recorded clip, and how many, without fetching every date's full clip list from
`GET /nuraeye/recordings` just to find out. Computed from a cheap filename-timestamp directory
scan bucketed by UTC date — deliberately **not** sourced from the
 duration index alone, so a clip whose duration repair is still pending (or failed) still
counts as long as the file itself exists. Same `storage_available`/`card_present` /
`503`-while-indexing convention as `GET /nuraeye/recordings`.

Optional `start`/`end` (UTC epoch seconds, inclusive range) and `tz_offset_minutes` (defaults
`0`/UTC if omitted — pass the client's local UTC offset to bucket dates by local calendar day
instead of UTC calendar day) query parameters (an exception to the POST-with-JSON-body convention, like `GET /nuraeye/recordings`).

**Request:**
```
GET /nuraeye/recordings/dates?start=1755950000&end=1756900000&tz_offset_minutes=330 HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "storage_available": true,
    "card_present": true,
    "dates": [
      { "date": "20250823", "clip_count": 42 },
      { "date": "20250824", "clip_count": 17 }
    ]
  }
}
```
`date` is `YYYYMMDD` as an 8-digit string. `503` (`"Recordings index is still building, please
retry"`, with a `retry_after_seconds` output) while is
false — same as `GET /nuraeye/recordings`.

## Privacy

### `/nuraeye/privacy-mode`

**GET** (`mode` ∈ `None`/`Zone`/`Full`):

**Request:**
```
GET /nuraeye/privacy-mode HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "mode": "None"
  }
}
```
**POST** — `mode: "None"` or `"Full"` also clears all configured privacy
masks:

**Request:**
```
POST /nuraeye/privacy-mode HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "mode": "Zone"
}
```

**Response:** shared success body. Invalid `mode` value → `400`.

## Video & Image

### `GET /nuraeye/video/mode`

(read-only; day/night is set via `/nuraeye/video/night-vision-type` and ONVIF
Imaging `IrCutFilter`, not here):

**Request:**
```
GET /nuraeye/video/mode HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "configured_mode": "AUTO",
    "effective_state": "day"
  }
}
```

### `/nuraeye/video/night-vision-type`

**GET** (`type` ∈ `Grey`/`Color`/`Smart`; `sub_state` only present when
`type=Smart`). **Reports live status only**; the capability flags are `night_vision_color_capable` and `night_vision_smart_capable` in `GET /nuraeye/capabilities`:

**Request:**
```
GET /nuraeye/video/night-vision-type HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "type": "Smart",
    "sub_state": "Grey"
  }
}
```
**POST**:

**Request:**
```
POST /nuraeye/video/night-vision-type HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "type": "Grey"
}
```

**Response:** shared success body. Unsupported `type` → `400`.

### `/nuraeye/video/mirror-flip`

**GET**:

**Request:**
```
GET /nuraeye/video/mirror-flip HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "mode": "Off"
  }
}
```
**POST** (`mode` ∈ `Off`/`Mirror`/`Flip`/`Both`):

**Request:**
```
POST /nuraeye/video/mirror-flip HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "mode": "Mirror"
}
```

**Response:** shared success body. Invalid `mode` value → `400`.

### `/nuraeye/video/anti-flicker`

Power-line frequency / anti-flicker mode, to avoid banding under artificial lighting. ONVIF has no standard element for this setting, so it exists only in this REST API (like `/nuraeye/video/mirror-flip` above).

**GET**:

**Request:**
```
GET /nuraeye/video/anti-flicker HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "mode": "50Hz"
  }
}
```
**POST** (`mode` ∈ `50Hz`/`60Hz`/`Auto`/`None` — `None` is accepted for
forward compatibility but is not offered as a client-facing choice by clients):

**Request:**
```
POST /nuraeye/video/anti-flicker HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "mode": "60Hz"
}
```

**Response:** shared success body. Invalid `mode` value → `400`.

### `GET /nuraeye/video/image-defaults`

Factory-default imaging settings, not current values (numeric fields
formatted `%.0f`).

**Request:**
```
GET /nuraeye/video/image-defaults HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "brightness": 50,
    "contrast": 50,
    "saturation": 50,
    "sharpness": 50,
    "white_balance_mode": "AUTO",
    "wb_red_gain": 0,
    "wb_blue_gain": 0,
    "exposure_mode": "AUTO",
    "exposure_time": 0,
    "exposure_gain": 0
  }
}
```

## Streaming

### `GET /nuraeye/preview-key`

Fetches the camera-generated shared AES-256 key used to encrypt-then-decrypt WAN preview
snapshots end-to-end. LAN-only: a client calls it at onboarding or first WAN setup over an already-authenticated session. Generates the key on first call (a fresh/factory-reset
camera has none yet) and persists it from then on.

The camera generates and owns one shared key, and any number of clients can fetch it with this `GET`. The matching capture, encrypt and publish path is on the WAN MQTT side (`GetPreviewSnapshot`), described in [camera-wan-mqtt-api.md](camera-wan-mqtt-api.md).

**Request:**
```
GET /nuraeye/preview-key HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "key": "eB1w2FhFvE0G8b7c1yqjKz9mQnZ4sVtRfLxU7dCwHqM="
  }
}
```

Key-generation failure or config-save failure → `500`.

### `POST /nuraeye/live-stream-uri`

Resolves where to connect for live video. The response names the transport (`output.transport`), so a client chooses its player from the response. On current firmware the transport is always `"rtsp"` (RTSPS); a client should still read `transport` rather than assume it.

`profile_token` is `Profile_1` (main stream, also an ONVIF profile), `Profile_2` (sub stream, also an ONVIF profile) or `Profile_3` (mobile stream, **not** an ONVIF profile). **POST with a JSON body, not GET with query parameters**, for the same reason as `/nuraeye/identity` above.

**Request:**
```
POST /nuraeye/live-stream-uri HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "profile_token": "Profile_1"
}
```



**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "transport": "rtsp",
    "port": 556,
    "path": "/mobile",
    "url": "rtsps://192.0.2.50:556/mobile"
  }
}
```
`port`/`path` are per-`profile_token`: `Profile_1` → `554`/`/high`, `Profile_2` → `555`/`/medium`,
`Profile_3` → `556`/`/mobile`. `path` is informational: each stream has its own dedicated port, so the camera does not route on it. `url` uses the `rtsps://` scheme. Unknown/missing
`profile_token`, or port/IP resolution failure → `400`.

`Profile_3` has no settings that a client can change; its settings are fixed. `Profile_1`/`Profile_2` are configured
via ONVIF `SetVideoEncoderConfiguration` as usual — this endpoint only resolves *where* to
connect, 

### `POST /nuraeye/talk-uri`

Two-way-talk discovery — the talk counterpart of `live-stream-uri` above. Resolves the
connection info for the camera's **dedicated audio-only two-way-talk RTSPS module**, a single-client TLS RTSP
server carrying two AAC-LC/8000 Hz tracks — `streamid=0` (camera mic → client, `a=sendonly`) and
`streamid=1` (client mic → camera, `a=recvonly`) — driven by `RECORD` rather than `PLAY`. It is
completely independent of live view: its own port, its own connection, one talker at a time.

There is **one** talk resource (audio-only, always-on), so unlike `live-stream-uri` there is no
`profile_token` and no transport choice — the module is TLS-only, so `output.transport` is always
`"rtsps"`. The request body is ignored; send `{}` or nothing.

**Request:**
```
POST /nuraeye/talk-uri HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{}
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "transport": "rtsps",
    "port": 560,
    "path": "/talk",
    "url": "rtsps://192.0.2.50:560/talk"
  }
}
```

`port` is fixed (560 on current firmware) and `path` is informational: the module has one dedicated port and no path routing. The client then opens an RTSPS session to `url` and runs `OPTIONS` → `DESCRIBE` → `SETUP.../streamid=0` (`interleaved=0-1`) → `SETUP.../streamid=1` (`interleaved=2-3`) → `RECORD`, exchanging `$`-framed AAC RTP (payload type 97, RFC 3640 AU-hbr framing) in both directions until `TEARDOWN`. RTSP-level Digest authentication applies (RFC 2617, `realm="ONVIF"`, no `qop`, MD5), the same as every other RTSPS listener on this camera.

Local-IP resolution failure, or a build without `AUDIO_ENABLED` ("Two-way talk unavailable on
this build") → `400`. A second concurrent talk session is rejected by the module at `RECORD`
time, not here.

There is no WAN counterpart for two-way talk.

### `/nuraeye/cloud/streaming`

**GET** (`stream_status` ∈ `active`/`degraded`/`not_compiled`/`idle`):

**Request:**
```
GET /nuraeye/cloud/streaming HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "stream_status": "idle"
  }
}
```
**POST** — stop only; starting cloud streaming is WAN/MQTT-only, so this endpoint
rejects anything but `{ "active": false }` with a `400` explaining why:

**Request:**
```
POST /nuraeye/cloud/streaming HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "active": false
}
```

**Response:** shared success body.

## Deterrence & Alarms

### `/nuraeye/buzzer`

**GET**:

**Request:**
```
GET /nuraeye/buzzer HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "active": true
  }
}
```
**POST** (`duration_seconds` required only when `active: true`):

**Request:**
```
POST /nuraeye/buzzer HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "active": true,
  "duration_seconds": 10
}
```
`{ "active": false }` to stop — `duration_seconds` not required.

**Response:** shared success body.

### `/nuraeye/deterrence`

`siren_capable`/`spotlight_capable`/`warning_capable` moved to `GET /nuraeye/capabilities`
(the standalone `GET /nuraeye/deterrence/capabilities` endpoint was removed).

**GET** — each action reports its own state. Siren, spotlight and warning are separate hardware outputs and can be active at the same time:

**Request:**
```
GET /nuraeye/deterrence HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "siren": true,
    "spotlight": true,
    "warning": false
  }
}
```
**POST** (**no `duration_seconds` field, 2026-08-14** — the
camera applies its own persisted, per-action duration instead, see
[`/nuraeye/deterrence/durations`](#nuraeyedeterrencedurations) below):

**Request:**
```
POST /nuraeye/deterrence HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "action": "siren",
  "active": true
}
```
`400` if that `action` isn't supported on this build, or `action` is unrecognized.
`{ "action": "siren", "active": false }` to stop.

**Response:** shared success body.

### `/nuraeye/deterrence/durations`

The persisted, per-action auto-stop configuration that `ActivateDeterrence` above applies, and that the automatic detection-triggered response (`GET`/`POST /nuraeye/events/response-actions`) applies too. There is one configured value per action, shared by both trigger paths. Only the keys this build's `GetDeterrenceCapabilities` reports as capable are meaningful. **`siren_seconds` and `spotlight_seconds` are whole seconds; `warning_repeat_count` is a repeat count (how many times the clip plays), not seconds.** See [`/nuraeye/deterrence/durations/options`](#nuraeyedeterrencedurationsoptions) below for the valid range of each; it is reported by the camera and must not be assumed.

**GET**:

**Request:**
```
GET /nuraeye/deterrence/durations HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "siren_seconds": 5,
    "spotlight_seconds": 5,
    "warning_repeat_count": 3
  }
}
```
**POST** (partial update, any subset of the three keys):

**Request:**
```
POST /nuraeye/deterrence/durations HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "siren_seconds": 15
}
```
`400` if any key is unrecognized, outside the range
[`/nuraeye/deterrence/durations/options`](#nuraeyedeterrencedurationsoptions) reports for it, or
names an action this build doesn't report as capable — whole request rejected, nothing applied.

**Response:** shared success body.

### `/nuraeye/deterrence/durations/options`

Reports the camera's own valid `min`/`max` for each key that `/nuraeye/deterrence/durations` accepts. Clients should build their UI from this response rather than hard-coding a range.

**GET**:

**Request:**
```
GET /nuraeye/deterrence/durations/options HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "siren_seconds_min": 1,
    "siren_seconds_max": 60,
    "spotlight_seconds_min": 1,
    "spotlight_seconds_max": 60,
    "warning_repeat_count_min": 1,
    "warning_repeat_count_max": 10
  }
}
```

## Health

### `GET /nuraeye/health`

Read-only, with no matching `POST`: every field is derived by the camera. `last_reboot_utc` reads `0` until the first NTP sync of the current boot corrects it (the camera has no battery-backed clock, so every boot starts with an uncertain clock); `0` means "not yet corrected this boot", not "the camera has never booted". `clock_sync_state` has two values, `"synced"` and `"uncertain"`. `firmware_version` repeats the value from `GetDeviceInfo` / ONVIF `GetDeviceInformation`, so one call returns the full vitals.

`reboot_reason` is why the *current* boot happened —
`"Firmware Upgrade"`, `"Factory Reset"`, `"HTTP Server Failure"` (the web server watchdog escalating to a reboot), `"Manual Reboot"`, `"WiFi Provisioning"`, `"Sensor
Capture Mode Change"`, or `"Unknown / Crash"` for a genuine, uncontrolled crash/hard-WDT-timeout.
Free text on the wire, not a closed enum. `"Unknown / Crash"` is also the value after any uncontrolled reset. Empty string on firmware too old to report it.

**GET** (fields built by,
shared with the WAN command below):

**Request:**
```
GET /nuraeye/health HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "reboot_count": 42,
    "last_reboot_utc": 1798329600,
    "reboot_reason": "Firmware Upgrade",
    "uptime_seconds": 86412,
    "clock_sync_state": "synced",
    "uncertain_since": 0,
    "firmware_version": "20260826094500",
    "motion_sensor": "ok",
    "tls_identity": "device",
    "kvs_e2e_dropped": 0
  }
}
```

`tls_identity` says which TLS identity the camera's local TLS servers present: `"device"` = the camera's own key (unique to this camera), `"shared"` = the fixed key every camera has (no own key yet, or it
could not be made), `"fixed"` = a fixed fallback certificate (not even a certificate could be built at boot). A client should treat anything but `"device"` as "this connection does not prove which camera it is".

`kvs_e2e_dropped` counts the frames the camera dropped since boot because they could not be encrypted (a key problem or no buffer room). The camera never sends a frame it could not encrypt in the clear, so a value above 0 means
viewers missed that many frames; `0` is normal. It reads `0` on a build without. Also in the WAN `GetDeviceHealth` reply.

`motion_sensor` is `"none"` when the camera has no accelerometer, `"ok"` when it responds and `"fault"` when it does not. A sensor fault is health
information only: the camera sends no alert for it, so a client shows it where it shows the other health values and in the Movement protection settings.

### `/nuraeye/movement-protection`

`024`/`025`, /`161`, added 2026-10-22. Accelerometer physical-tamper detection:
`GET` reads the state, `POST` sets the sensitivity. Calibration is the separate `POST.../calibrate` below. On a
camera whose `accelerometer_capable` is `false` both answer **`501`** `"Movement protection is not supported on this
camera"`. `GET` is open to every role; `POST` is Administrator-only (the route is not classified as Operator). There is no WAN command for either yet.

**GET**:

**Request:**
```
GET /nuraeye/movement-protection HTTP/1.1
Authorization: Bearer <token>
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "sensor": "ok",
    "calibrated": true,
    "calibrated_at": 1798329600,
    "sensitivity": "medium",
    "moved": false
  }
}
```
`sensor` is `"ok"` or `"fault"` (: the sensor did not answer at start-up or failed several reads in a row; the camera
retries about once a minute and reports `"ok"` again when it answers). `calibrated` is `false` on a camera that has never been
calibrated, and such a camera reports no physical-tamper alerts. `calibrated_at` is the UTC epoch of the last calibration, `0` if the
clock was not valid then or the camera is not calibrated. `sensitivity` is one of the names in `supported_movement_sensitivities` (`"medium"` by default). `moved` is `true`
while a calibrated camera is outside its saved position; it clears after recalibration or after about 10 s back within half the
threshold.

**POST**:

**Request:**
```
POST /nuraeye/movement-protection HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "sensitivity": "high"
}
```

**Response:** shared success body. Missing/malformed `sensitivity` → `400` `"Missing or malformed sensitivity"`; a value that is not one of
`supported_movement_sensitivities` → `400` `"sensitivity is not one of supported_movement_sensitivities"`; save failure → `500` `"Failed to save configuration"`.
Each level sets a tilt threshold and a knock threshold (initial values for the shipped levels: tilt 35° / 25° / 15° for Low / Medium / High and knock 0.6 g / 0.3 g / 0.15 g, to be tuned
on the board; the numbers are not reported over the API, but the descriptions in `GET /nuraeye/capabilities` state them in words).

**Alerts** this feature publishes on the MQTT alert topic (documented in
[Camera-WAN-MQTT-API.md](camera-wan-mqtt-api.md) §8):

**Example alert (physical tamper):**
```json
{
  "event": "Tamper",
  "timestamp": 1798329600,
  "cause": ["tilt", "knock"]
}
```

A sensor fault sends no alert (removed 2026-10-23): it is reported as `motion_sensor` in `GET /nuraeye/health` and in the movement-protection state.

### `POST /nuraeye/movement-protection/calibrate`

Measures the camera's position (about 16 readings over roughly 1.3 s, so the call
**blocks that long**), refuses if the readings are not steady, otherwise saves the averaged position and marks the camera calibrated.
A successful calibration also clears any "moved" state. **Local network only: there is deliberately no WAN command for it**, so a
stolen account token cannot re-accept a tampered camera's new position remotely. Administrator-only. Handler.

**Request:**
```
POST /nuraeye/movement-protection/calibrate HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{}
```

**Response:**
```json
{
  "error_code": 0,
  "error_msg": "Success",
  "output": {
    "calibrated_at": 1798329600
  }
}
```
Failures use the error shape above: `409` `"camera_moving"` (the readings varied by more than about 60 mg on an axis; nothing is saved
and any earlier calibration is unchanged), `409` `"busy"` (the sensor bus is in use), `503` `"sensor_fault"`, `501` (not supported),
`500` `"Failed to save configuration"` (position measured but not persisted).
