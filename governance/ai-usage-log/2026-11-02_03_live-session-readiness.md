# Session 03 — Live-session readiness review

- **Date:** 2026-11-02
- **Tool:** Claude Code (VS Code extension), Claude Opus 5.5
- **Goal:** Make sure the plan treats the live session (new unseen batch, run unedited, rule change, explain decisions) as the top requirement.

## Prompt (verbatim)

> [pasted: the two brief quotes about the live session]
> Is our plan incoporating this, its a big requirement, I should be easily able to do it

## Assessment

The plan covered being *able* to handle unseen invoices and rule changes (generic extraction, config-driven policy,
drills). It did not cover the *mechanics* of doing it smoothly on a shared screen.

## Gaps found and fixed

| Gap | Fix |
|---|---|
| A rerun after a rule change would show "already processed" (idempotent ledger) | `--what-if`, auto `pre-<inbox>` snapshots, `snapshot restore`, `diff` (ADR-0009) |
| No pre-flight check | `ap doctor` |
| One API failure could crash the demo | Retries → model fallback → per-document OTHER hold |
| No way to narrate a decision | `ap explain`, `run_report.html` |
| Serial extraction too slow on screen | Concurrent extraction, < 90 s target |
| Submitted ledger state undefined | Snapshot `submitted` = post-Batch-02 |
| Non-parameter rule changes | Rule template + test template |
| No rehearsal or script | Two timed dress rehearsals (Phase 6 exit), `LIVE_SESSION_RUNBOOK.md` |

Plan estimate moved from 6.5 h to 8 h, with an explicit "never cut" list.
