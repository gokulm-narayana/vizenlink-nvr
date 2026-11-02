# Plan 02-05 Summary: Two-Source Segment Indexing & Scanner

## Status: COMPLETE

### Overview
Plan 02-05 implemented the two-source segment indexing architecture per decisions D-35, D-40, and requirement REC-09:
1. Real-time segment completion hook: `nvr recording hook-segment-complete` reads `MTX_PATH`, `MTX_SEGMENT_PATH`, and `MTX_SEGMENT_DURATION` directly from `os.environ` without command arguments or shell interpolation, indexing completed 60s fMP4 video segments immediately into SQLite with millisecond accuracy.
2. Two-source disk reconciliation scanner: `nvr storage scan` recursively walks storage volumes to adopt unindexed video files, mark missing database rows for files deleted out-of-band, and flag truncated segments (< 1024 bytes).

### Tasks Completed:

1. **Task 1: Real-time segment hook entrypoint and SegmentIndexerService**
   - Implemented `src/vizenlink_nvr/services/indexer.py`:
     - `parse_mtx_path`: Extracts camera serial and stream type (`cam/<serial>/<stream>`).
     - `parse_start_time_from_path`: Uses regular expressions to extract UTC start timestamp from ISO-8601 (`YYYY-MM-DDTHH-MM-SSZ`) and MediaMTX timestamp formats, falling back to filesystem modification time.
     - `parse_segment_metadata`: Computes start/end times, reads file size, sets duration, and evaluates validity (>= 1024 bytes -> `active`, < 1024 bytes -> `truncated`).
     - `record_segment_from_hook`: Upserts segment records in the SQLite `segments` table bound to registered cameras with case-insensitive serial matching.
   - Added `hook-segment-complete` subcommand to `src/vizenlink_nvr/cli/recording.py`:
     - Reads environment variables directly with zero CLI arguments (D-35).
     - Handles errors gracefully without returning non-zero exit codes to ensure MediaMTX operation is never interrupted.
   - Created unit tests `tests/unit/test_hook_parser.py`:
     - Verified path extraction, filename timestamp parsing, mtime fallback, and truncated segment classification.
   - Created integration tests `tests/integration/test_segment_indexing.py`:
     - Tested `nvr recording hook-segment-complete` execution and database row persistence.

2. **Task 2: Two-source disk reconciliation scanner and storage scan CLI**
   - Implemented `scan_and_reconcile` in `src/vizenlink_nvr/services/indexer.py`:
     - Traverses SQLite `segments` table: verifies existence of indexed files on disk, transitions deleted files to `status="missing"`, and flags corrupted files < 1024 bytes as `truncated`.
     - Walks storage filesystem: identifies unindexed `.mp4` files, maps path hierarchy to registered camera serials, and inserts new active segments into SQLite (adoption).
   - Added `scan` subcommand to `src/vizenlink_nvr/cli/storage.py`:
     - Options: `--serial` (optional filter), `--json` (JsonOpt), `--data-dir` (DataDirOpt).
     - Outputs detailed summary metrics (adopted, marked missing, marked truncated, total valid).
   - Created integration tests `tests/integration/test_reconciliation_scanner.py`:
     - Verified adoption of 3 unindexed files written during simulated core downtime.
     - Verified idempotent re-scan.
     - Verified out-of-band file deletion transitions row to `status="missing"`.
     - Verified out-of-band truncation (< 1024 bytes) transitions row to `status="truncated"`.
     - Verified camera serial filtering and human/JSON output modes.

### Verification Results:
- `uv run pytest tests/unit/test_hook_parser.py tests/integration/test_segment_indexing.py tests/integration/test_reconciliation_scanner.py -x -q`: 6 passed in 0.35s.
- `uv run pytest tests/unit/test_cli_password_options.py`: 2 passed (All CLI commands use TyperOption, no prohibited password options).
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 76 source files.
