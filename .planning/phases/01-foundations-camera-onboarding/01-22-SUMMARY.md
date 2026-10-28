# Plan 01-22 Summary: ONVIF Device Operations and Media2 Streams

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Device operations, Media2 profiles and GetStreamUri (DEV-03..07, PRF-01/02, D-23 client)**
   - Extended `src/vizenlink_nvr/camera/onvif/device.py`:
     - Added `get_network_interface_info` returning `NetworkInterfaceInfo` with normalized MAC and IP (DEV-03).
     - Added `get_device_identity` parsing `ScopeItem` entries with percent-decoding for `name` and `location` (DEV-04).
     - Added `set_device_name` and `set_device_location` with 32-character maximum check, percent-encoding, and single `Scopes` XML payload (DEV-05, D-13, CAM-08).
     - Added `set_user_password` sending `SetUser` payload with XML-escaped credentials and length verification (DEV-06, D-04, CAM-04).
     - Added `get_services` sending `IncludeCapability=false` and returning `ServiceEntry` list (DEV-07).
   - Created `src/vizenlink_nvr/camera/onvif/media2.py`:
     - Defined `MEDIA2_NAMESPACE = "http://www.onvif.org/ver20/media/wsdl"`.
     - Defined `MediaProfile` dataclass (token, name, venc_token, width, height, encoding).
     - Implemented `OnvifMedia2Client` with:
       - `resolve_endpoint`: parses `GetServices` response for Media2 namespace, extracting only path (`/onvif/media2_service`), ignoring XAddr host (PRF-02).
       - `get_profiles`: parses `Profiles` elements, skipping incomplete profiles without `VideoEncoder` or resolution, returning `Failure` when no usable profiles exist (PRF-01, CAM-07).
       - `get_stream_uri`: sends Media2 `GetStreamUri` with `Protocol=RTSP` and `ProfileToken`, returning URI string for D-23 fallback.
   - Extended simulator in `sim/fake_camera/routes/onvif_device.py`:
     - Handled `GetScopes` responding with current `name` and `location` scopes.
     - Handled `SetScopes` with auth check, first-password gate check, and max-2-scopes constraint.
     - Handled `GetNetworkInterfaces` returning formatted MAC (`wlan`) and IPv4.
     - Handled `GetServices` returning Device and Media2 services with dummy host `10.9.9.9`.
     - Handled `SetUser` requiring Administrator WSSE, rejecting `"password"` (case-insensitive) with `ter:PasswordNotAllowed` fault, and updating simulator account password.
   - Created simulator route in `sim/fake_camera/routes/onvif_media2.py`:
     - Handled `POST /onvif/media2_service`.
     - Handled `GetProfiles` returning configurable stream profiles from `OnvifSimSettings`.
     - Handled `GetStreamUri` returning formatted template URI.
   - Added 5 golden ONVIF fixtures with line-level provenance comments:
     - `contracts/fixtures/onvif/get_scopes.xml`
     - `contracts/fixtures/onvif/get_network_interfaces.xml`
     - `contracts/fixtures/onvif/get_services.xml`
     - `contracts/fixtures/onvif/get_profiles_media2.xml`
     - `contracts/fixtures/onvif/get_stream_uri_media2.xml`
   - Added contract tests in `tests/contract/test_onvif_device.py` and `tests/contract/test_media2.py` verifying DEV-03..DEV-07, PRF-01, PRF-02, and D-23 fallback stream URI.

### Verification Evidence:
- `uv run pytest tests/contract/test_onvif_device.py tests/contract/test_media2.py -x -q`: 9 passed in 0.10s.
- `grep -ho 'behavior("[A-Z0-9-]*")' tests/contract/*.py | sort -u`: includes WSSE-03, SOAP-01..SOAP-07, DEV-01..DEV-07, PRF-01, PRF-02.
- `uv run pytest -x -q`: 135 passed, 1 skipped, 6 deselected in 4.47s.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 99 files formatted.
- `uv run mypy src/vizenlink_nvr/camera`: Success: no issues found in 19 source files.
- Reference repositories (`nuraeye-rt`, `mobilecctvapp`) remained untouched.
