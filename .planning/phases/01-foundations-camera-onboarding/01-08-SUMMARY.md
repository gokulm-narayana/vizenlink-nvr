# Plan 01-08 Summary: Encrypted Credential Vault and Authoritative Canary Key Source

## Status: COMPLETE

### Tasks Completed:
1. **Task 1: Credentials at rest vault (AES-256-GCM, permissions, key sources, canary lifecycle)**
   - Created `src/vizenlink_nvr/secrets/__init__.py`.
   - Created `src/vizenlink_nvr/secrets/permissions.py`:
     - POSIX directory `0700` and file `0600` permission enforcement (`ensure_private_dir`, `ensure_private_file`).
     - Permission assertions (`assert_private`) checking group/other bits on POSIX.
     - Windows `icacls` user ACL enforcement without shell execution.
   - Created `src/vizenlink_nvr/secrets/keysource.py`:
     - KeySource protocol with `load(create: bool) -> bytes | None`.
     - `FileKeySource` with atomic `O_CREAT | O_EXCL` file generation and 32-byte key validation.
     - `KeyringKeySource` with OS keystore access and 5.0s timeout safeguard.
     - `AutoFallbackKeySource` falling back from keyring to file backend on KeyringError, timeout, or dummy keyring.
     - Deterministic key ID generation: `key_id_for(key, source) -> f"{source}:{sha256(key)[:16]}"`.
   - Created `src/vizenlink_nvr/secrets/vault.py`:
     - `SealedSecret` frozen dataclass (ciphertext, nonce, key_id, enc_version=1).
     - `Vault` class sealing with AES-256-GCM, random 12-byte nonce, and AAD `vizenlink-nvr/cred/v1|<serial>|<username>`.
     - `CredentialsUnreadable` exception on tampering, key mismatch, or AAD mismatch.
     - `CanaryStatus` with lifecycle states: `ok`, `mismatch`, `missing_key`, `insecure_key_file`, `unavailable`, `not_initialised`.
     - `initialise_vault` and `check_canary` recording and verifying canary in `app_setting.secrets_canary` (D-29).
     - Authoritative canary behavior: never overwriting existing canary; rejecting mismatched configured key sources.
   - Integrated into `src/vizenlink_nvr/services/runtime.py` and `src/vizenlink_nvr/services/status.py`:
     - Vault status evaluated during `open_runtime`.
     - `StatusReport` includes `credentials_status`, `key_source`, `key_id`.
   - Created comprehensive tests in `tests/integration/test_status_credentials.py` and `tests/unit/test_credentials_at_rest.py`.

2. **Task 2: Log redaction filter and logging configuration**
   - Created `src/vizenlink_nvr/log.py`:
     - `RedactingFilter` intercepting `logging.LogRecord`.
     - Redaction patterns for Authorization headers, Bearer tokens, passwords, password digests, and JSON password fields.
     - Supports string messages, tuple args, and dict args.
     - `configure_logging(level: str = "INFO")` installing filter on root handlers.
   - Created `tests/unit/test_log_redaction.py`:
     - Tested redaction of Bearer tokens, Authorization values, digest patterns, JSON fields, and dict arguments.

### Verification Evidence:
- `uv run pytest tests/integration/test_status_credentials.py tests/unit/test_credentials_at_rest.py tests/unit/test_log_redaction.py -x -q`: All passed.
- `uv run pytest -q`: 70 passed, 1 skipped in 2.12s.
- `uv run ruff check src tests sim`: All checks passed.
- `uv run ruff format --check src tests sim`: 64 files already formatted.
- `uv run mypy src`: Success: no issues found in 40 source files.
