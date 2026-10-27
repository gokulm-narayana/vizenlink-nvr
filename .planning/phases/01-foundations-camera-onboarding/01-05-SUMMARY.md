# Plan 01-05 Summary: Typed camera core, HTTP transport, WSSE and identity client

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Build typed camera core before simulator expansion**
   - Created `src/vizenlink_nvr/camera/result.py` with `FailureKind` enum, frozen dataclasses `Success`, `Failure`, `Timeout`, alias `CameraResult`, and `parse_retry_after` parser. Added source mirror tracking comment.
   - Created `src/vizenlink_nvr/camera/connection.py` with `CameraConnection` frozen dataclass, `DEVICE_SERVICE_PATH`, `base_url` (with IPv6 bracket handling), `with_address`, `with_credentials`, and `blank`.
   - Created `src/vizenlink_nvr/camera/wsse.py` with `created_from` (always ending in `.000Z`), `new_nonce_b64`, `compute_digest`, `WsseToken`, and `make_token` using injected `Clock`. Added source mirror tracking comment.
   - Created `src/vizenlink_nvr/camera/events.py` with `CameraIdMismatchEvent`, `CameraUnreachableEvent`, and `CameraEventBus` with `subscribe` and `publish`. Added source mirror tracking comment.
   - Created `src/vizenlink_nvr/camera/roles.py` with `CameraRole` enum (`USER`, `OPERATOR`, `ADMINISTRATOR`), `from_wire`, and `at_least`. Added source mirror tracking comment.
   - Created `src/vizenlink_nvr/camera/http.py` with `camera_ssl_context` (supporting self-signed certs and peer cert SHA-256 pin verification), `fetch_certificate_sha256`, `HttpResponse`, and `CameraHttp` transport with `send` (verbatim header case preservation, auto-injecting `X-VizenLink-Camera-Id` when serial is known, and event publishing on 421 or unreachable) and `aclose`. Added source mirror tracking comment.
   - Created `src/vizenlink_nvr/camera/layer.py` with `CameraLayer` facade and `create` factory.
   - Created `src/vizenlink_nvr/camera/nuraeye/rest.py` with `RestOk`, `RestError`, `unwrap`, `post_json`, and `get_json`. Added source mirror tracking comments.
   - Created `src/vizenlink_nvr/camera/nuraeye/client.py` with `NuraeyeClient` implementing `are_you_nuraeye_device`. Added source mirror tracking comment.
   - Created `tests/contract/test_results.py` validating frozen immutability, pattern matching, `FailureKind` values, and lockout delay parsing.
   - Created `tests/contract/test_wsse.py` validating known answer test vector (`F3ldVt6HHuN3/vvi4vYtwEH8+w8=`), ISO-8601 formatting, injected clock binding, and random nonce uniqueness.

### Verification Evidence:
- `uv run pytest tests/contract/test_results.py tests/contract/test_wsse.py -x -q`: Exit code 0, 8 passed.
- `uv run pytest -q`: Exit code 0, 31 passed across entire test suite.
- `uv run ruff check src tests` & `uv run ruff format --check src tests`: Exit code 0.
- `uv run mypy src`: Exit code 0, 35 source files checked.
- `git commit`: `6f2f0e5 feat(01-05): typed camera core, HTTP transport, WSSE and identity client`.
