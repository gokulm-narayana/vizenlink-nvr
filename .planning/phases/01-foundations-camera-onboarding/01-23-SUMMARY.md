# Plan 01-23 Summary: Blank-Credential Discovery, Bounded Unicast, and Scan CLI

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Tracer: `nvr cameras scan --json` finds simulated cameras over WS-Discovery with blank credentials**
   - Extended `src/vizenlink_nvr/config.py` with discovery settings: `discovery_port`, `discovery_multicast_group`, `discovery_unicast_hosts`.
   - Created `src/vizenlink_nvr/camera/discovery/__init__.py`.
   - Created `src/vizenlink_nvr/camera/discovery/ws_discovery.py` with `build_probe`, `parse_probe_matches`, `local_ipv4_interfaces` (using `ifaddr`, filtering loopback and 169.254/16), and `sweep_hosts` (bounded to `max(prefix, 24)`).
   - Created `src/vizenlink_nvr/services/scan.py` with `ScannedCamera`, `ScanReport`, `ScanService`, and `run_scan`.
   - Implemented unauthenticated identity probing with 1 retry on Failure/Timeout (no retry on non-genuine), blank metadata resolution, and name fallback hierarchy (scopes name -> model -> `Camera at <host>`).
   - Created `src/vizenlink_nvr/cli/cameras_scan.py` registering `nvr cameras scan` with `--thorough`, `--timeout`, `--json`, and human table output.
   - Created integration tests in `tests/integration/test_scan.py` and `tests/integration/test_cli_scan_json.py` confirming tracer behavior, blank credentials throughout, clean JSON stdout, and stderr hints for zero cameras.

2. **Task 2: Discovery hardening: per-interface multicast, unicast sweep, bounds, retry, and naming fallbacks (DSC-01..05, D-27)**
   - Hardened `WsDiscoveryClient`:
     - Per-interface multicast datagram endpoints with `IP_MULTICAST_IF` and ephemeral source ports.
     - Correlated response filtering by `RelatesTo` with probe `MessageID`.
     - Unicast subnet sweep paced at 50 ms per target, bounded to 30 s total with 10 s straggler window.
     - Handled `ConnectionResetError` / `OSError` in datagram protocol's `error_received` (for Windows ICMP resets).
     - Applied `MAX_DATAGRAM = 65536` and `MAX_CANDIDATES = 512`.
   - Created golden discovery fixtures with line-level provenance comments:
     - `contracts/fixtures/discovery/probe_matches_firmware.xml`
     - `contracts/fixtures/discovery/probe_request.xml`
   - Created `tests/unit/test_ws_discovery.py` verifying DSC-01..DSC-04.
   - Expanded `tests/integration/test_scan.py` verifying DSC-05 (name fallbacks, non-genuine drop, exactly 2 requests on retry, unicast fallback on empty multicast, and thorough mode).

### Verification Evidence:
- `uv run pytest tests/unit/test_ws_discovery.py tests/integration/test_scan.py tests/integration/test_cli_scan_json.py -x -q`: 11 passed in 25.63s.
- `grep -ho 'behavior("DSC-[0-9]*")' tests/unit/*.py tests/integration/*.py | sort -u`: includes DSC-01, DSC-02, DSC-03, DSC-04, DSC-05.
- `uv run pytest tests/contract/test_fixtures_provenance.py -q`: 1 passed in 0.32s.
- `uv run mypy src`: Success: no issues found in 58 source files.
- `uv run ruff check src sim tests && uv run ruff format --check src sim tests`: All checks passed, 105 files formatted.
- `uv run pytest -x -q`: 146 passed, 1 skipped, 6 deselected in 33.99s.
- Reference repositories remained untouched; all listeners explicitly bound loopback.
