# Phase 1 revision applied — planning evidence only

This revises the existing plans; no research or locked decision was changed. All implementation and test status is PENDING.

## Scope mapping

| Historical scope | Revised plans |
|---|---|
| Historical plan 12 | 01-29 |
| Historical plan 02 | 01-05, 01-06, 01-07 |
| Historical plan 03 | 01-08 |
| Historical plan 13 | 01-30 |
| Historical plan 08 | 01-23 |
| Historical plan 11 | 01-28 |
| Historical plan 01 | 01-01, 01-02, 01-03, 01-04 |
| Historical plan 10 | 01-27 |
| Historical plan 09 | 01-24, 01-25, 01-26 |
| Historical plan 05 | 01-11, 01-12, 01-13, 01-14, 01-15, 01-16, 01-17 |
| Historical plan 04 | 01-09, 01-10 |
| Historical plan 14 | 01-31 |
| Historical plan 06 | 01-18, 01-19, 01-20 |
| Historical plan 07 | 01-21, 01-22 |

## Findings addressed

- Research resolution was already committed; preserved. Six oversized plans split with exact file lists; hidden 49-file vendoring additionally split into five copy/hash batches plus tooling and finalize/catalogue. No wildcard or directory stands in for file counts. Each plan writes 4–13 files.
- Pre-credential serial bind: blank serial read follows identity probe; factory/owner requests require bound serial and exact-case header. Missing/swapped targets tested with zero credential disclosure. D-06 post-verification reads are retained and checked against the bound serial.
- SOAP HTTP 401 and ter:NotAuthorized map UNAUTHORIZED before generic errors; rename integration proves auth_failed with no stored-password retry.
- Every prohibition starts pending; automated guards cover bootstrap listeners, unchanged read-only references, no GetDeviceInformation credential check, memory-only session tokens, and pin wording.
- Existing vault canary source/key id is authoritative in CLI and service; no auto fallback or key creation for an existing vault; mismatches remain visible.
- MediaMTX address set is explicit 127.0.0.1, TCP-only RTSP, disabled unused protocols; parsed configuration assertions enumerate every listener.
- Discovery uses bounded outbound UDP client transaction sockets on ephemeral interface ports, with Probe/reply correlation and finally cleanup; no persistent or fixed non-loopback service listener. Real LAN replies remain functional; simulator receive services stay loopback-only.
- Added America/Santiago midnight-DST cases; tracer tasks use executor-supported auto type with tracer marker; research citations use Example N.
- ROADMAP, validation task ownership, coverage and all generated plan references updated. Dependencies include shared-write ordering; same-wave files are disjoint.
- No remote created; three-OS CI explicitly PENDING. Local phase gate never proves cross-platform CI. Hardware passwords use environment/hidden input only; reset requires explicit owner authorization. No phase-verification claim.

## Additional executable guards required

The planned camera architecture rules test must assert session tokens remain memory-only: inspect serialized registry views, SQLite rows/bytes and on-disk settings after login, excluding the encrypted password; a sentinel bearer token never persists. The pin wording test in test_tls_changed.py must assert exact owner-facing message and scan message-producing code/docs for claims that the pin authenticates a camera or protects against MITM. GetDeviceInformation credential verification guard in test_add_manual.py proves authenticated GetCapabilities decides credentials, while a blank serial read is allowed before login. Reference tools tests snapshot git status before/after read-only inventory operations.

## Gate policy

Dependency review in 01-01, D-11 registry confirmation, and real-camera execution are blocking-human, even in yolo mode. Declining serial-pk stops for locked-decision conflict; never silently implement a surrogate key. Owner verification is separate.

## Locked CLI input rule

Existing positional SERIAL and ZONE examples were corrected to required --serial and --zone options per D-16. The CLI parameter-tree guard rejects all positional leaf arguments, and command tests exercise the flags. This preserves the locked decision rather than creating a new choice.

## Checker revision round 2

- 01-23: replaced the nonfunctional loopback-only LAN reply bind with bounded outbound UDP client transactions using ephemeral interface ports, correlated replies and finally cleanup. Service listeners remain loopback-only.
- 01-06: now owns faults.py primitives and server handling before identity tracer tests; 10 total owned files. 01-07 extends the existing mechanism.
- 01-09: made its current config/binary/report/CLI interfaces explicit and isolated successor process/probe imports behind probe=True.
- 01-17: assigned the 70 catalogue rules to actual first-implementing slices and added representative owner assertions.
- All estimates: low confidence, zero calibration samples, factor 1.0.
- 01-30: exactly three tasks: build complete harness with collection only, blocking-human execution approval, authorized real run. Run authorization is separate from host/password and from mutation/reset opt-ins. No preapproval hardware access.
- ROADMAP progress is 0/31. Context and historical findings remain unchanged.
