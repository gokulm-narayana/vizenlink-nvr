# Request: add `buzzer_capable` to camera capabilities

**To:** camera firmware / `camera_api` owner
**From:** VizenLink NVR team
**Date:** 2026-11-11
**Status:** proposed — no changes made to `camera_api` or the mobile app

## Problem
Apps cannot tell whether a camera has a buzzer before using it.

- `GET /nuraeye/capabilities` reports `siren_capable`, `spotlight_capable` and `warning_capable`, but nothing for the buzzer.
- `GET /nuraeye/buzzer` and `POST /nuraeye/buzzer` define only 200 and auth errors (400/401/403/428). There is no defined "not supported" answer.

So the NVR (and the mobile app) must show a buzzer control on every camera. On a model without a buzzer, the user only finds out when the camera returns an undefined error after pressing it.

## Proposed change
Add one boolean to the capabilities output, next to the other deterrence flags.

`contracts/camera_api/design/Camera-REST-API.openapi.yaml`, under `GET /nuraeye/capabilities` → `output.properties` (beside `siren_capable`, around line 1147):

```yaml
                          buzzer_capable:
                            type: boolean
                            description: >-
                              Whether this SKU has a buzzer that GET/POST /nuraeye/buzzer and
                              alert-rule buzzer_activation can drive. Absent on older firmware:
                              clients must treat absent as "unknown" and keep the control.
```

Matching Dart model field in `lib/src/lan/nuraeye/capabilities_client.dart` and `rest_capabilities_client.dart` (nullable `bool? buzzerCapable`, parsed from `buzzer_capable`). The WAN capabilities shape in `iot_command_client.dart` should get the same field if WAN exposes buzzer control.

Firmware: report the value from the same hardware/SKU table that drives `siren_capable`.

Optional, for consistency: when a camera without a buzzer receives `POST /nuraeye/buzzer` or `setAlertRule` with `buzzer_activation: true`, return a defined error (for example 400 with a stable `error_code` meaning "not supported on this hardware").

## Semantics we rely on
| `buzzer_capable` | NVR behaviour |
|---|---|
| `true` | Show buzzer controls |
| `false` | Hide them and say "Not available on this camera: Buzzer"; refuse buzzer commands |
| absent (current firmware) | Show controls as today |

## Compatibility
Additive and optional. Existing clients ignore the new field, and older firmware simply doesn't send it.

## NVR status
The NVR already honours `buzzer_capable: false` (frontend `CameraControlPanels.tsx`, backend `services/camera_features.py`), so no further NVR release is needed once firmware reports it.
