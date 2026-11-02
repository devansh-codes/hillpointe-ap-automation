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

## Follow-up prompts (verbatim)

> are we ready here? do we have a system in place to make calls in hard cases? to re-run and audit? [...] my question before we build the ui is, are we thoroughly using the provided documents when generating the outputs?

- Audited every source folder, tab and column against the code. One real gap: the Entities tab's "AP System" column was
  unused, so a bill addressed to OZF1 (Juniper Square) would have posted to HCM. Now held OTHER (A-22), with tests.

> [screenshot of otter.ai] Go ahead and build the UI, get UI reference from the screenshot provided, and its this website otter.ai

- Built `ap ui` (ADR-0012), borrowing Otter's layout patterns (sidebar with channels → routes, search bar, top-right primary
  action, card feed with thumbnail, floating action rail, "Get started" checklist) with Hillpointe's own content and no Otter branding.
- Verified with headless-Chrome screenshots and API tests: rule preview in 2 s with 0 tokens, exactly 1 document changes for
  tolerance $1,500; save → apply → undo restored the policy byte for byte; uploads; path traversal refused. 102 tests.
- While checking the UI against the answer key, found that the evaluator guide's Batch 01 table (and the assistant's
  earlier chat answer) had mixed up 0009/0013/0015. The system was right; the guide was corrected.
