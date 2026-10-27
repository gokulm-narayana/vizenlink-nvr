# Plan 01-11 Summary: Read-Only Vendoring and Drift Tools with Bounded Batch Mode

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Build vendoring and drift tools without copying inventory yet**
   - Created `.gitattributes` setting `contracts/** -text` to prevent CRLF conversions across platforms.
   - Created `tools/vendor_contracts.py`:
     - Structured 49-file `INVENTORY` split across 5 bounded batches (10 in batch 1, 10 in batch 2, 10 in batch 3, 10 in batch 4, 9 in batch 5).
     - `--batch N` (1..5): Copies only designated files for that batch, records upstream git commit & dirty state, and generates manifest `contracts/batches/NN.json`.
     - `--finalize`: Validates all 5 batch manifests exist, checks exactly 49 files with no duplicates, verifies hashes on disk, and writes `contracts/camera_api.lock.json`.
     - Path traversal protection and symlink escaping refusal.
   - Created `tools/drift_check.py`:
     - `--self`: Computes SHA-256 for all vendored files against `contracts/camera_api.lock.json` (exits 0 clean, 1 on drift/missing).
     - `--batch N`: Validates SHA-256 of batch manifest against disk.
     - `--upstream PATH --mobile PATH`: Compares upstream files against vendored copies with unified diffs.
     - `--root PATH`: Enables running validation against alternate repository roots.
   - Created `tests/contract/test_contract_lock.py`:
     - Isolated tooling tests in `tmp_path` testing all 5 batches, tamper detection, and finalization.
     - Verified reference checkouts (`nuraeye-rt`, `mobilecctvapp`) remain 100% byte-identical and untouched after read-only inspection.

### Verification Evidence:
- `uv run pytest tests/contract/test_contract_lock.py -x -q`: 3 passed in 1.11s.
- `uv run pytest -q`: 79 passed, 1 skipped, 6 deselected in 3.14s.
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run ruff format --check src tests sim tools`: 80 files already formatted.
- `uv run mypy src`: Success: no issues found in 47 source files.
