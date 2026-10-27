# Plan 01-17 Summary: Finalize Full Contract Lock, Behavior Catalogue and Fixture Provenance

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Behaviour catalogue, divergence record and fixture provenance**
   - Ran `tools/vendor_contracts.py --finalize` to compile the unified `contracts/camera_api.lock.json` from all 5 batch manifests.
   - Validated 49 files, their origin repos, upstream commits, and SHA-256 hashes against actual files on disk.
   - Created `contracts/behaviors.yaml` containing the complete 70-rule behaviour catalogue (RES-01..07, HTTP-01..09, WSSE-01..03, IDN-01..03, SES-01..07, SOAP-01..07, DEV-01..07, PRF-01..03, CAP-01..06, LST-01..04, DSC-01..05, HEAL-01..05, ONB-01..04) mapped to specific source files or architectural decisions and assigned implementing plans.
   - Authored `contracts/DIVERGENCES.md` cataloguing all 13 deliberate divergences from `camera_api` (including `GetStreamUri` fallback under D-23 and credential vault sealing under D-14).
   - Documented golden fixture format in `contracts/fixtures/README.md`.
   - Seeded initial golden fixtures with verifiable provenance:
     - `contracts/fixtures/wsse/digest_vector.json` (source: `nuraeye_digest_test.dart` lines 24-33)
     - `contracts/fixtures/rest/login_ok.json` (source: `rest_mock_helpers.dart` lines 21-28)
   - Created `tests/contract/test_fixtures_provenance.py` verifying that every fixture under `contracts/fixtures` references a valid vendored lock file and valid line ranges.
   - Extended `tests/contract/test_contract_lock.py` with `test_behaviors_catalogue_schema` asserting regex ID format, unique rule IDs, valid plan assignments, FND-05 requirement mapping, and representative plan assignments.

### Verification Evidence:
- `uv run pytest tests/contract/test_fixtures_provenance.py tests/contract/test_contract_lock.py -x -q`: 5 passed in 1.08s.
- `uv run python tools/drift_check.py --self`: All vendored contract files match `camera_api.lock.json` (exit 0).
- `uv run pytest -q`: 81 passed, 1 skipped, 6 deselected in 3.20s.
- Reference repositories (`nuraeye-rt` and `mobilecctvapp`) remained 100% read-only and untouched.
