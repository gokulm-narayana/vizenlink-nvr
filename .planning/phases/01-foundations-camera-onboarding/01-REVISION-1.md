# Phase 1 — Plan-checker findings, round 1 (to be fixed before execution)

Checker result: ISSUES FOUND (7 blockers, 7 warnings, 6 info). Requirement coverage, decision coverage (D-01..D-30), dependency graph and CLAUDE.md compliance all PASSED. Blocker 1 is already fixed (commit c455eac).

Contract: the required property binds; the fix_hint is one example. A different mechanism that reaches the same property is fine. If a fix would contradict a locked decision in 01-CONTEXT.md, stop and report the conflict instead of working around it.

## Blockers
1. [DONE] 01-RESEARCH.md "Open Questions" now marked RESOLVED (c455eac).
2-7. **Scope sanity: each plan must touch fewer than 15 files, or be split.**
   - 01-01 (36 files): split e.g. bootstrap/supply chain | time model | CLI skeleton
   - 01-02 (27): split camera core | sim/fake_camera
   - 01-06 (23): split sessions/REST | capabilities/live-stream-uri + sim routes
   - 01-07 (19): split SOAP/faults | device ops + Media2
   - 01-04 (16): split config/binary/pins | live probe harness
   - 01-09 (16): split schema/registry/streams | onboarding service + CLI
   After splitting: renumber, fix depends_on and waves, keep same-wave plans free of shared file writes, update every cross-reference (01-03's "01-09" mentions, the Plan/Task column in 01-VALIDATION.md, the ROADMAP plan list). This also clears the context-budget warning on 01-02 and 01-09.

## Warnings (fix in the same revision)
1. **Security (D-11), plans 01-09/01-10:** no credential-bearing request may be sent before the target's serial is bound. Today the order is identity probe, fetch pin, factory login (`admin`/`password`), owner-credential verify, and only then the serial read. Fix e.g.: read the serial with blank credentials right after the identity probe; then send credentialed calls with `X-VizenLink-Camera-Id`. Add a test asserting no credentialed request precedes serial binding.
2. **D-09, plans 01-07/01-12:** a SOAP authentication failure (HTTP 401, or `ter:NotAuthorized`) must map to UNAUTHORIZED, so a rename after a password change sets `auth_failed`. Today SOAP paths only yield GENERIC. Add a test.
3. **Prohibitions, all plans:** do not declare a prohibition `resolved` before its test exists. Set them `pending`, or name the automated check. Turn the six `verification: judgment` items into tests where feasible (reference repos unchanged: `git status` before/after; no GetDeviceInformation used as a credential check; no token persisted; pin wording never says "authentication"; no listener in the bootstrap plan).
4. **Plan 01-14 / success criterion 5:** the repo has no git remote, so three-OS CI cannot run yet. Keep it as an explicit PENDING gate. `tools/phase_gate.py` is local evidence only.
5. **D-29, plan 01-03:** for an existing vault, the key source recorded in the canary is authoritative; CLI and service must resolve that same source. A mismatch stays a reported status.
6. **Plan 01-04:** every listen address in the generated MediaMTX config must be an explicit 127.0.0.1 value (including `rtpAddress`/`rtcpAddress`, or restrict `rtspTransports` to tcp), asserted in `test_mediamtx_config.py`, not only from log lines.

## Info (include if cheap)
- 01-08: discovery reply socket uses an ephemeral bind closed in `finally`; test that no listener persists after a scan.
- 01-01: add a midnight-DST zone (`America/Santiago`) to the DST test cases.
- Align "RESEARCH Code Example N" citations to the "### Example N" headings.
- Confirm `type="tracer"` tasks are valid for `/gsd-execute-phase`; otherwise use `auto` with a tracer marker.
