# Phase 2: Headless Recording Core - Research

**Researched:** 2026-10-28
**Domain:** Headless 24/7 fMP4 video recording, MediaMTX path control & reconciler, two-source segment indexing, retention janitor, storage guardrails, gap watchdog, local admin CLI
**Confidence:** HIGH. Wire behavior, MediaMTX v1.21.3 API endpoints, fMP4 segmenting hooks, and environment variable passing were empirically verified on this host. SQLite schema, cross-platform filesystem primitives (`shutil.disk_usage`, `st_dev`), and async background tasks use standard library components.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The user approved the core defaults and architectures established in research. Every decision below locks Phase 2 behavior.

#### Storage Location & Disk Safeguards
- **D-31: Storage directory structure.**
  Recordings are saved to `{storage_root}/{camera_serial}/{YYYY}/{MM}/{DD}/{YYYY-MM-DDTHH-MM-SS}Z.mp4`.
  Timestamps in directory names and filenames are always UTC with trailing `Z`.
  Storage root is configurable via CLI (`nvr storage set-path <PATH>`), defaulting to `<NVR_DATA_DIR>/recordings`.
- **D-32: System drive guard (REC-08, HLTH-05).**
  The NVR inspects mountpoints. If the configured storage path is on the host root mountpoint (`/` on Linux/macOS or `C:\` on Windows), the NVR refuses to start recording unless explicitly overridden with `--allow-system-disk`. If the recording volume is missing, unmounted, or read-only, the recorder halts with a critical storage error (`STORAGE_UNMOUNTED`, `STORAGE_READ_ONLY`) distinct from camera offline status.
- **D-33: Hard free-space reserve & overwrite (REC-07, HLTH-04).**
  The NVR enforces a hard minimum free space buffer: default `10 GB` (or 5% of total disk capacity, whichever is larger). When disk free space drops below this low-water mark, the Janitor proactively deletes the oldest unprotected segments across cameras to prevent write failure.

#### Segment Duration & MediaMTX Configuration
- **D-34: Segment duration & format (REC-01, REC-11).**
  MediaMTX records directly into fragmented MP4 (`fMP4`) segments.
  - `recordSegmentDuration: 60s` (60-second fixed segments).
  - `recordPartDuration: 1s` (enables power-loss safety without file corruption).
  - Audio recording is toggled per camera: if camera capability confirms audio and user enabled audio (`nvr recording set-audio --serial <SERIAL> --enabled`), audio track is recorded; otherwise disabled.
  - No remuxing is required; files are natively playable fMP4.
- **D-35: Two-source segment indexing (REC-09).**
  - *Real-time hook:* MediaMTX `runOnRecordSegmentComplete` executes a CLI hook (`nvr recording hook-segment-complete`) that immediately writes segment start time, duration, size, and path into the SQLite `segments` table.
  - *Reconciliation scanner:* Background loop on startup and periodically (e.g. every 10 minutes) reconciles disk contents with SQLite: indexes unindexed files, clears database records for deleted files, and flags truncated files.

#### Retention Policies & Janitor
- **D-36: Retention enforcement & camera removal (REC-05, REC-06, CAM-09).**
  - Per-camera retention is configurable: max retention days (e.g. 14 days) and max storage gigabytes.
  - The NVR Janitor is the **sole** component that deletes footage (MediaMTX `recordDeleteAfter` is set to `0s`). Oldest unprotected segments are pruned first.
  - Camera removal (`nvr cameras remove --serial <SERIAL>`) requires an explicit choice: `--keep-recordings` (preserves files and keeps segments table or archives them) or `--delete-recordings` (janitor purges segment files and DB records).

#### Recording Modes & Schedules
- **D-37: Recording modes & schedules (REC-02, REC-03).**
  - Supported modes:
    - `Continuous`: 24/7 recording.
    - `Scheduled`: Records only during active windows defined by weekly schedule.
    - `Event`: Records continuous rolling circular buffer ready for event locking (Phase 4).
    - `Off`: Camera stream is not recorded.
  - Weekly schedule represents a 7×24 grid (168 hourly slots or 336 30-min slots) stored in the camera's recording configuration.

#### Watchdog & Independent Process Supervision
- **D-38: Process decoupling & declarative reconciler (FND-01, FND-02).**
  MediaMTX runs as an independent daemon. The NVR Core's Declarative Reconciler reads camera configurations from SQLite and synchronizes paths via MediaMTX's loopback control API (`127.0.0.1:9997`).
  If NVR Core crashes or restarts, MediaMTX continues recording in-flight streams. If MediaMTX restarts, NVR Core reconciles and re-provisions all paths immediately.
- **D-39: Gap watchdog & dual health status (HLTH-01, HLTH-03, HLTH-06, REC-10).**
  - Dual independent badges for each camera:
    1. Connection status: `online` vs `offline`.
    2. Recording status: `recording` vs `not_recording`.
  - Gap watchdog monitors `last_segment_completed_at`. If elapsed time exceeds `2 × segment_duration + 30s` (~150 seconds for 60s segments), status transitions to `not_recording` with a gap alert.
  - Dropped streams reconnect automatically with exponential backoff (1s, 2s, 4s, ..., up to 60s).

#### Admin CLI Commands
- **D-40: CLI recording and storage interface (FND-04, REC-02, REC-06, HLTH-04).**
  - `nvr recording status`: displays per-camera recording state, mode, current segment age, and health badges.
  - `nvr recording set-mode --serial <SERIAL> --mode <MODE>`
  - `nvr recording set-retention --serial <SERIAL> [--days N] [--max-gb GB]`
  - `nvr recording set-schedule --serial <SERIAL> [--schedule-spec ...]`
  - `nvr recording hook-segment-complete`: reads environment variables from MediaMTX and records segment.
  - `nvr storage status`: displays disk space, mountpoint, free space reserve, and retention estimates.
  - `nvr storage set-path <PATH> [--allow-system-disk]`
  - `nvr storage scan`: triggers manual disk/index reconciliation.
  - `nvr cameras remove --serial <SERIAL> (--keep-recordings | --delete-recordings)`

### Claude's Discretion
- Database schema details for migrations (Alembic `0003_recording_core.py`).
- Exact structure of weekly schedule JSON representation.
- In-memory gap watchdog timer mechanics and backoff backoff curve.

### Deferred Ideas (OUT OF SCOPE)
- Web UI & browser playback (Phase 3 & Phase 5).
- LAN HTTP REST API `/api/v1` and JWT auth (Phase 3).
- ONVIF PullPoint camera event parsing (Phase 4).
- Timeline clip slicing & video export (Phase 5).
</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Stream Pulling & fMP4 Segmenting | MediaMTX (C/Go Daemon) | — | Native RTSPS ingestion, packet handling, and fMP4 packaging with 1s parts. Zero Python video transcoding overhead. |
| Declarative Reconciler | Python Core Service | MediaMTX API | Computes desired paths from SQLite and reconciles via MediaMTX loopback API. |
| Two-Source Segment Indexing | Python Core / CLI Hook | SQLite DB | Instant indexing via `runOnRecordSegmentComplete` + startup/periodic disk scanner. |
| Storage & System Drive Guard | Python Core Service | Filesystem OS | Cross-platform mountpoint (`st_dev` / drive letter) and `shutil.disk_usage` checks. |
| Retention Janitor | Python Core Service | SQLite DB / Filesystem | Evaluates retention limits and low-water mark, atomically deleting oldest unprotected files. |
| Gap Watchdog & Dual Health | Python Core Service | In-Memory / CLI Status | Monitors segment completion timestamps; triggers gap warnings and backoff reconnects. |
| Admin CLI | Python Typer CLI | Core Services | Headless local administration for storage, recording modes, schedules, and camera removal. |
</architectural_responsibility_map>

<research_summary>
## Summary

Phase 2 builds the core recording engine of VizenLink NVR headless. It bridges the camera registry built in Phase 1 with MediaMTX's native streaming and fMP4 recording capabilities.

The architectural pattern is **declarative and crash-resilient**:
1. SQLite is the single source of truth for desired recording state (modes, schedules, retention policies, audio settings).
2. The Declarative Reconciler diffs desired paths against MediaMTX's runtime state (`/v3/config/paths/list`) and issues `POST /v3/config/paths/add`, `PATCH /v3/config/paths/patch`, and `DELETE /v3/config/paths/delete` requests over loopback (`127.0.0.1:9997`).
3. If NVR Core crashes or restarts, MediaMTX continues recording in-flight streams. When NVR Core starts up, it immediately reconciles all paths.
4. Two-source indexing combines low latency with absolute correctness: MediaMTX's `runOnRecordSegmentComplete` hook indexes segments in real time without passing shell variables (reading `MTX_PATH`, `MTX_SEGMENT_PATH`, and `MTX_SEGMENT_DURATION` directly from the process environment), while a periodic disk scanner adopts any segments missed during core reboots and cleans up orphaned entries.
5. Strict storage guards protect host system stability: recording to the OS root partition is rejected unless explicitly overridden, and an autonomous Janitor monitors disk free space, deleting the oldest unprotected segments before disk exhaustion occurs.

**Primary recommendation:** Build Phase 2 strictly around decoupled process supervision, Alembic-backed SQLite schemas (`0003_recording_core`), argument-free hook execution via environment variables, and comprehensive mock/simulated integration tests for reconciler, janitor, and watchdog.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library / Component | Version | Purpose | Why Standard |
|---------------------|---------|---------|--------------|
| MediaMTX | v1.21.3 | RTSP pull & fMP4 segmentation | Pinned binary; native C/Go high-performance streaming with 1s fragmented MP4 parts. |
| SQLAlchemy / Alembic | >=2.0 / >=1.13 | SQLite schema & migrations | Existing async ORM and migration tool in codebase. |
| Typer / Rich | >=0.12 / >=13.0 | CLI interface | Existing CLI tooling for `nvr recording` and `nvr storage` commands. |
| shutil / os / pathlib | Python 3.11+ Stdlib | Storage & mountpoint inspection | `shutil.disk_usage` and `os.stat().st_dev` provide reliable cross-platform disk telemetry. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.28.1 | MediaMTX REST control API client | Managing paths (`/v3/config/paths/*`) over loopback with basic auth. |
| pydantic | 2.14+ | Settings & schedule schema validation | Validating weekly schedule bitmasks and retention parameters. |
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Component Architecture Diagram
```
                       +---------------------------------------+
                       |           Camera Registry             |
                       |       (SQLite: cameras table)         |
                       +---------------------------------------+
                                           |
                                           v
+------------------------+     +-----------------------+     +------------------------+
|   CLI: nvr recording   | --> | Declarative           | --> | MediaMTX Control API   |
|   CLI: nvr storage     |     | Reconciler            |     | (127.0.0.1:9997)       |
+------------------------+     +-----------------------+     +------------------------+
                                                                         |
                                                                         v
+------------------------+                                   +------------------------+
| Camera RTSP Streams    | ================================> | MediaMTX Daemon        |
| (Main / Sub)           |       (RTSP over TLS / TCP)       | (Records fMP4 to disk) |
+------------------------+                                   +------------------------+
                                                                         |
                                            runOnRecordSegmentComplete   |
                                            (MTX_PATH, MTX_SEGMENT_PATH) |
                                                                         v
+------------------------+     +-----------------------+     +------------------------+
| Retention Janitor      |     | Two-Source Indexer    | <-- | Hook CLI Entrypoint    |
| (Purges Oldest First)  |     | (Real-time + Scanner) |     | (nvr recording hook)   |
+------------------------+     +-----------------------+     +------------------------+
            |                              |
            v                              v
+------------------------------------------------------+
|                     SQLite DB                        |
|  - recording_settings (mode, schedule, retention)    |
|  - segments (path, start_time, duration, size)       |
|  - storage_config (path, allow_system, reserve)      |
+------------------------------------------------------+
```

### Pattern 1: Declarative MediaMTX Path Reconciler
The reconciler queries desired state from SQLite (camera RTSP URLs, passwords decrypted in memory, recording modes, weekly schedules) and queries current paths from `GET /v3/config/paths/list`.
- If path missing in MediaMTX: `POST /v3/config/paths/add/{name}`
- If path settings differ (e.g. `record` toggled on/off by schedule): `PATCH /v3/config/paths/patch/{name}`
- If camera removed or disabled: `DELETE /v3/config/paths/delete/{name}`
Paths are formatted as `cam/<serial-lowercase>/main` and `cam/<serial-lowercase>/sub`.

### Pattern 2: Argument-Free Segment Completion Hook
To avoid shell escaping bugs across Linux, macOS, and Windows:
MediaMTX configures:
```yaml
runOnRecordSegmentComplete: "nvr recording hook-segment-complete"
```
The CLI command `nvr recording hook-segment-complete` takes zero arguments and parses:
- `os.environ["MTX_PATH"]`: e.g. `cam/vzl-cam-001/main`
- `os.environ["MTX_SEGMENT_PATH"]`: e.g. `/data/recordings/vzl-cam-001/2026/10/28/2026-10-28T16-51-46Z.mp4`
- `os.environ["MTX_SEGMENT_DURATION"]`: float seconds, e.g. `60.05`
The hook validates the file exists, computes/reads its size, and inserts the row into `segments`.

### Pattern 3: Two-Source Reconciliation Scanner
In addition to the real-time hook, a background scanner runs at startup and periodically (every 10 minutes):
1. Walks the configured `{storage_root}/{serial}` directory.
2. Identifies `.mp4` files present on disk that have no row in `segments`, parses timestamps, and inserts them (`status = "active"`).
3. Identifies rows in `segments` whose file no longer exists on disk and marks them `status = "missing"`.
4. Validates file headers/sizes to ensure truncated files are flagged.

### Pattern 4: Cross-Platform System Drive & Space Guard
- **System Drive Guard:**
  - On POSIX: `os.stat(storage_path).st_dev == os.stat("/").st_dev`
  - On Windows: `Path(storage_path).resolve().drive == Path(os.environ.get("SystemDrive", "C:")).drive`
  - If on system disk and `--allow-system-disk` not set, refuse recording and enter `STORAGE_SYSTEM_DISK_REFUSED`.
- **Low-Water Mark Janitor:**
  - `shutil.disk_usage(storage_path).free < reserve_bytes` (10 GB or 5% of drive).
  - Janitor queries oldest unprotected segments across cameras:
    `SELECT * FROM segments WHERE is_protected = 0 ORDER BY start_time ASC LIMIT 50`
  - Deletes files from disk and removes rows from SQLite until free space exceeds reserve + 1 GB hysteresis buffer.

### Pattern 5: Gap Watchdog
- Tracks `last_segment_time` per camera.
- If `now - last_segment_time > 2 * segment_duration + 30s` (150s for 60s segments), camera enters `not_recording` state with gap alarm.
- On stream interruption, camera client initiates reconnect with exponential backoff: `1s, 2s, 4s, 8s, 16s, 32s, max 60s`.
</architecture_patterns>

<common_pitfalls>
## Common Pitfalls & Solutions

### Pitfall 1: Relying solely on webhook / hook execution
- **Risk:** Core crash or restart drops in-flight hooks; segments become unindexed gaps.
- **Solution:** Two-source indexing. The background scanner reconciles disk files with the database on every startup and every 10 minutes.

### Pitfall 2: MediaMTX native deletion races
- **Risk:** MediaMTX `recordDeleteAfter` deletes files without notifying SQLite, creating ghost index rows.
- **Solution:** Set `recordDeleteAfter: 0s` in MediaMTX. The Python Janitor is the **sole** component that deletes recordings.

### Pitfall 3: System drive exhaustion
- **Risk:** Unmonitored recording fills the host OS partition, crashing the machine.
- **Solution:** Strict system drive guard refusing root partition without explicit override, plus 10 GB / 5% hard reserve enforcing proactive oldest-first pruning.

### Pitfall 4: Shell argument interpolation differences across OSes
- **Risk:** Calling hooks with `$MTX_SEGMENT_PATH` fails or behaves differently on Windows `cmd.exe` vs macOS/Linux `sh`.
- **Solution:** Hook command takes zero arguments; python reads environment variables directly.

### Pitfall 5: Segment boundary duration vs GOP size
- **Risk:** Video segments only split on keyframes (IDR frames). A 60-second segment may actually be 60.5s or 61.2s.
- **Solution:** Never assume fixed 60.000s duration. Read `MTX_SEGMENT_DURATION` or inspect container for exact duration.
</common_pitfalls>

<code_examples>
## Verified Code Examples

### 1. MediaMTX Path Management via httpx
```python
async def reconcile_camera_path(
    client: httpx.AsyncClient,
    api_url: str,
    control_auth: tuple[str, str],
    serial: str,
    stream_url: str,
    record: bool,
    record_path_pattern: str,
) -> None:
    path_name = f"cam/{serial.lower()}/main"
    payload = {
        "source": stream_url,
        "sourceOnDemand": False,
        "record": record,
        "recordFormat": "fmp4",
        "recordPartDuration": "1s",
        "recordSegmentDuration": "60s",
        "recordDeleteAfter": "0s",
        "recordPath": record_path_pattern,
        "runOnRecordSegmentComplete": "nvr recording hook-segment-complete",
    }
    
    # Check if path exists
    res = await client.get(f"{api_url}/v3/config/paths/get/{path_name}", auth=control_auth)
    if res.status_code == 200:
        await client.patch(f"{api_url}/v3/config/paths/patch/{path_name}", json=payload, auth=control_auth)
    elif res.status_code == 404:
        await client.post(f"{api_url}/v3/config/paths/add/{path_name}", json=payload, auth=control_auth)
```

### 2. Cross-Platform Disk Space and System Drive Detection
```python
import os
from pathlib import Path
import shutil

def is_system_drive(target_path: Path) -> bool:
    resolved = target_path.resolve()
    if os.name == "nt":
        system_drive = os.environ.get("SystemDrive", "C:").upper()
        return resolved.drive.upper() == system_drive
    else:
        root_stat = os.stat("/")
        target_stat = os.stat(resolved)
        return root_stat.st_dev == target_stat.st_dev

def get_disk_telemetry(target_path: Path) -> dict[str, int]:
    usage = shutil.disk_usage(target_path)
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }
```
</code_examples>

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.1 + pytest-timeout 2.4.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/test_recording_*.py tests/unit/test_storage_*.py -x -q` |
| Full suite command | `uv run python tools/phase_gate.py` |
| Estimated runtime | ~60 seconds for full phase gate |

### Validation Approach
- **Unit Tests:**
  - Schedule evaluator logic (7x24 weekly matrix active window checks).
  - Storage telemetry and system drive guard detection across simulated paths and OSes.
  - Janitor pruning algorithms (order of deletion, protection range overlap prevention).
  - Two-source indexing logic (hook parser + directory scanner reconciliation).
  - Gap watchdog state transitions and backoff curve calculation.
- **Integration Tests:**
  - Alembic migration `0003_recording_core.py` up and down verification.
  - MediaMTX loopback reconciler against running MediaMTX test instance.
  - End-to-end recording with simulated camera / RTSP publisher: segment generation, hook execution, SQLite indexing, and CLI display.
  - Disk full simulation with temporary storage directory: low-water mark pruning and overwriting.
  - Camera removal verification (`--keep-recordings` vs `--delete-recordings`).
- **Regression Guards:**
  - Continued enforcement of D-01 through D-30 (zero secret leaks, strict loopback bindings, no password CLI arguments).

<metadata>
**Research scope:** Headless Recording Core (Phase 2)
**Research completed:** 2026-10-28
**Ready for planning:** yes
</metadata>
