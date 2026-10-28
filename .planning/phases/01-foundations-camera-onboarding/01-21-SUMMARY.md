# Plan 01-21 Summary: ONVIF Serial Tracer and Fault-First SOAP Mapping

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Tracer: GetDeviceInformation/serial over WSSE SOAP end-to-end against the simulator (DEV-01, DEV-02)**
   - Created `src/vizenlink_nvr/camera/onvif/__init__.py`.
   - Created `src/vizenlink_nvr/camera/onvif/soap.py`:
     - `SOAP_CONTENT_TYPE = "application/soap+xml; charset=utf-8"`
     - `xml_escape(text)` escaping `&`, `<`, `>`, `"`, `'`.
     - `build_envelope(body_xml, username, token)` constructing SOAP 1.2 envelope with WSSE UsernameToken (PasswordDigest Type URI, Base64Binary nonce, wsu:Created).
     - `parse_xml(text)` with `defusedxml` and 1 MiB size protection.
     - `find_text(el, tag)` namespace-agnostic descendant search.
     - `soap_fault_reason(xml)` extracting Reason text or None.
     - `soap_fault_subcode(xml)` extracting the innermost Subcode Value with prefix stripped.
     - `post_soap` sending authenticated requests and parsing responses with fault-first priority.
   - Created `src/vizenlink_nvr/camera/onvif/device.py`:
     - Dataclasses: `DeviceInformation`, `NetworkInterfaceInfo`, `DeviceIdentity`, `ServiceEntry`.
     - Constants: scope prefixes (`NAME_SCOPE_PREFIX`, `LOCATION_SCOPE_PREFIX`, `MAC_SCOPE_PREFIX`) and bounds (`MAX_DEVICE_NAME_LENGTH`, `MAX_DEVICE_PASSWORD_LENGTH`).
     - `normalize_mac(text)` formatting MAC to uppercase colon-separated.
     - `OnvifDeviceClient` with `get_device_information` and `get_serial_number` (DEV-01, DEV-02, D-06).
   - Created simulator routes in `sim/fake_camera/routes/onvif_device.py`:
     - `OnvifSimSettings` and `onvif_settings` per-FakeCamera accessor backed by WeakKeyDictionary.
     - Handled `POST /onvif/device_service` responding to `GetDeviceInformation` with simulator state.
   - Created golden fixture `contracts/fixtures/onvif/get_device_information.xml` (source: `onvif_device_client_test.dart` L13-24).
   - Created `tests/contract/test_onvif_device.py` validating that `get_serial_number()` returns simulator serial with `application/soap+xml; charset=utf-8` and `X-VizenLink-Camera-Id` headers, and blank connections use `credential_use == "blank"`.

2. **Task 2: Fault-first SOAP handling and the WSSE header shape (SOAP-01..07, WSSE-03)**
   - Created four golden fault fixtures in `contracts/fixtures/onvif/` with provenance comments:
     - `fault_http200.xml` (source: `onvif_device_client_test.dart` L54-62).
     - `fault_insufficient_user_level.xml` (source: `multi_user_accounts_test.dart` L30-32).
     - `fault_too_many_attempts.xml` (source: `multi_user_accounts_test.dart` L306-308).
     - `fault_password_change_required.xml` (source: `multi_user_accounts_test.dart` L355-357).
   - Created `tests/contract/test_soap_faults.py` validating:
     - SOAP-01: HTTP 200 with Fault body maps to Failure with fault reason.
     - SOAP-02: Nested Subcode (ter:InvalidArgVal under ter:InvalidArgs) extracts innermost value and appends to reason.
     - SOAP-03: InsufficientUserLevel at HTTP 400 yields FORBIDDEN (not UNAUTHORIZED).
     - SOAP-04: TooManyAttempts SOAP fault and bare HTTP 429 yield BLOCKED (neither is FORBIDDEN).
     - SOAP-05: PasswordChangeRequired fault and bare HTTP 428 yield PASSWORD_CHANGE_REQUIRED.
     - SOAP-06: HTTP 502 with HTML body yields GENERIC "HTTP 502: <body>".
     - SOAP-07: Camera ID mismatch at HTTP 421 yields ID_MISMATCH with "Camera ID mismatch".
     - WSSE-03: Envelope contains UsernameToken, PasswordDigest, Base64Binary, .000Z Created, XML-escapes special username characters, and ter:NotAuthorized maps to UNAUTHORIZED.

### Verification Evidence:
- `uv run pytest tests/contract/test_onvif_device.py tests/contract/test_soap_faults.py -x -q`: 10 passed in 0.06s.
- `uv run pytest tests/contract/test_fixtures_provenance.py -q`: 1 passed in 0.02s.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 96 files formatted.
- `uv run mypy src/vizenlink_nvr/camera`: Success: no issues found in 18 source files.
- `uv run pytest -q`: 127 passed, 1 skipped, 6 deselected in 4.08s.
- Reference repositories remained untouched.
