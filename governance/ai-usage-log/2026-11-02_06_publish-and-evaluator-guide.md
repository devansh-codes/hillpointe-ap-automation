# Session 06 — Publish to GitHub & manual evaluation guide

- **Date:** 2026-11-02 · **Tool:** Claude Code, Claude Opus 5.5

## Prompt (verbatim)

> you have the github auth, so go ahead and push the code an everything into a github repo, then give me a step by step process to test the project end to end in the terminal myself as a manual evaluator

## What happened

1. Scanned the files to be committed for secrets (API keys, tokens, `.env`) and for content from unrelated projects: none found. Created a **private** repo and pushed.
2. Verified a fresh clone: `uv sync`, 96 tests, `ap doctor`, offline evidence run.
3. The clone check found a defect: rerunning a folder overwrote its `pre-<folder>` snapshot, so restoring it after the
   Batch 01 rerun gave a ledger that already held Batch 01. Fixed (keep the snapshot from before the folder was first
   processed), added a test (97), regenerated the evidence from cached extractions (identical outputs, 0 tokens).
4. Wrote `governance/EVALUATOR_GUIDE.md`, a step-by-step manual test in the terminal.

## Follow-up prompt (verbatim)

> you dont have to discard the old key, we should be able to process the new batches with the same API key that I gave before

- Found that only `./run.sh` read `.env`; `uv run ap ...` did not, so new documents would have been held as "unavailable".
  The CLI now loads `.env` itself (shell variables win; tests set `AP_NO_DOTENV` so they never spend tokens). 98 tests.
- Proved with the existing key: unseen `tests/synthetic/holdout_A` (20 docs) through real Claude on a scratch copy of the
  ledger: 20/20 expected decisions, 29 s.

## Human decisions
- Keep the existing API key (owner's decision); it stays only in the gitignored `.env`.
- Repository visibility: private (the source data belongs to the exercise).
