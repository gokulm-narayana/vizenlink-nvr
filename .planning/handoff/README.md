# Session Handoff

Lets any Claude session, on any account or machine, pick up where the last one stopped. Everything lives in the repo, so nothing depends on chat history.

## Files

- **`LATEST.md`** is the current handoff, overwritten at the end of every session. Read it first.
- **`log/YYYY-MM-DD-HHMM-<slug>.md`** holds one file per session. Files are never edited after they're written, so they form the history.

## Session start (every new session, any account)

1. Read `LATEST.md`.
2. Read `.planning/STATE.md`, which has the GSD position (phase and plan).
3. If `.continue-here.md` exists anywhere under `.planning/`, run `/gsd-resume-work`.

## Session end (before switching accounts or stopping)

Say **"write handoff"**, or run `/gsd-pause-work` mid-phase. Claude will:

1. Write `log/<timestamp>-<slug>.md` using the template below.
2. Overwrite `LATEST.md` with the same content.
3. Commit with `docs(handoff): <slug>`.

## Template

```markdown
# Handoff — <date time> — <slug>

**Account/session:** <optional label>
**GSD position:** Phase N, plan X of Y, status

## What this session did
- ...

## Decisions made (and why)
- ...

## Current state
- Working: ...
- Broken / half-done: ...  (file paths)

## Next step
- Exact command or task to run next

## Open questions / waiting on
- ...
```
