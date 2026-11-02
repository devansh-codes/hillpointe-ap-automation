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

## Human decisions
- Repository visibility: private (the source data belongs to the exercise).
