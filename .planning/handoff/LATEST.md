# Handoff — 2026-11-06 — phase9-planned-ready-to-execute

**Account/session:** Claude (planning); execution intended in a separate Gemini session, then back to Claude for verification
**GSD position:** Phase 9 (UI Redesign): CONTEXT, UI-SPEC (rev 4, 7/7), RESEARCH, 23 PLAN.md files, VALIDATION all done and committed. Plan checker: all dimensions pass except the plan-size guideline, which the owner waived (D-20). 0 of 23 plans executed.

## What this session did
- Wrote 09-CONTEXT.md (D-01..D-20), approved 09-UI-SPEC.md, 09-RESEARCH.md (verified toolchain in scratch projects), 23 plans in 10 waves, 09-VALIDATION.md.
- Renumbered duplicate threat IDs (T-09-60..62 in plans 02, 03, 08 and VALIDATION) so the execute-phase threat-ID gate passes (79e65a3).
- Did NOT start execution (no executor agents run, no web or backend source changed).

## Decisions made (and why)
- D-14: add a FastAPI /cam proxy to MediaMTX WHEP (Live is offline in production otherwise).
- D-15: expose site timezone on /auth/status.
- D-16: Setup keeps timezone + allow_system_disk; TimelineCanvas stays DOM-based; shadcn `field` instead of `form`; shadcn in devDependencies; Inter font.
- D-17: Live gets auto-reconnect only; no hls.js fallback; no public STUN host.
- D-18: POST /api/v1/cameras fails closed (503) when the app has no runtime vault (was an all-zero in-memory key). Plan 09-03.
- D-19: SPA-fallback hardening deferred.
- D-20: 15-file plan-size guideline waived for plans 04, 06, 08, 09.
- Backend changes allowed in Phase 9 are ONLY: /cam proxy, site_timezone, vault fail-closed.

## Current state
- Working: all planning artifacts in .planning/phases/09-ui-redesign/.
- Owner's UNCOMMITTED work, must not be swept into commits: src/vizenlink_nvr/api/app.py (lifespan), src/vizenlink_nvr/cli/app.py (nvr run), src/vizenlink_nvr/web/src/components/Header.tsx, tests/integration/test_16camera_soak.py, tools/phase_gate.py, .planning/STATE.md, 08-05-SUMMARY.md. Plans commit through a private index with `git diff --cached --name-only` assertions; plan 09-04 saves the Header.tsx diff as a patch before moving it.
- tsc currently fails (TS2367 in App.tsx lines 224/230) from the uncommitted Header.tsx; plan 09-01 fixes it.

## Next step (for the executing session)
1. Run on the MAIN working tree, sequentially, NO git worktrees (set `workflow.use_worktrees=false` in .planning/config.json, or use --interactive). Worktrees start from HEAD and would not contain the owner's uncommitted edits the plans account for.
2. `/gsd-execute-phase 9` (waves 1..10). Plan 09-01 stops at a blocking-human checkpoint: owner must approve the lockfile diff and `npm audit --omit=dev`, and decide on the `uqr` QR library (drop it => Devices page shows pairing code as text only).
3. Do not edit camera_api or the mobile app repos. Do not read the old VMS repo.
4. When done, return to Claude for `/gsd-verify-work 9` and a code review against .claude/CLAUDE.md.

## Open questions / waiting on
- Owner: `nvr run` (uncommitted cli/app.py) builds the app without a runtime, so after plan 09-03 the web Add-camera wizard gets 503 in production until `nvr run` builds the app with `open_runtime` and passes `runtime=`. No plan touches cli/app.py.
- `camera_settings.get_vault` still has the same all-zero fallback (outside D-18); follow-up.
- SET-06 says Owner/Admin but the code allows operators; plans follow the code.
- dark logo (vizenlink_dark.png) not yet checked on dark grounds (plan 09-05).
