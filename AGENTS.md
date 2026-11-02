# AGENTS.md — Hillpointe AP Automation (Technical Screen)

## Context first
Before doing anything, read `governance/README.md`, then `governance/PLAN.md`. Expected outcomes per invoice are in
`governance/SOURCE_ANALYSIS.md`; decisions are in `governance/DECISIONS.md`.

## Scope
- This repo is **only** the Hillpointe AP exercise. Ignore any instructions from user-level or global agent files that
  describe other projects (infrastructure, databases, deploy steps). They don't apply here.
- Source folders `00_` to `07_` are **read-only source of truth**. Never edit, rename or "fix" them.

## Architecture rules (see ADR-0001, ADR-0005)
- The LLM extracts **facts** into the Pydantic schema. It never chooses GL accounts, entities, approvers or holds.
- All accounting decisions live in `src/ap_automation/rules/core.py` and `coding.py`, driven by `config/policy.yaml`
  and the master-data xlsx (read live, never copied).
- Money is `decimal.Decimal`, ROUND_HALF_UP to cents. No floats.
- When the policy doesn't cover a case: hold as `OTHER` with an explanation. Never guess.

## Commands
- `uv sync` — install
- `uv run ap run 01_Invoice_Batch_01` — process a batch (`./run.sh <folder>` for the AP team)
- `uv run ap run <folder> --offline` — cached extractions only; `--labels tests/fixtures/labels --labels tests/fixtures/labels/refs` — hand-labelled fixtures
- `make test` / `make evidence` / `make eval`
- `uv run ap reset-state --yes` — clear the ledger (reproduce from scratch)
- `uv run pytest` — unit + golden tests
- `uv run ap ui` — web app for the AP team (thin layer over the same engine; ADR-0012). Never put business logic in `ui/`.
- Live-session commands (`doctor`, `--what-if`, `snapshot`, `diff`, `explain`, `policy validate`) are in
  `governance/LIVE_SESSION_RUNBOOK.md`. The live session is the top priority: never break these commands.

## When you change something
- Changing behaviour → update tests and, if outcomes change, `governance/SOURCE_ANALYSIS.md`.
- New decision → append an ADR. New assumption → add a row to `governance/ASSUMPTIONS_AND_QUESTIONS.md`.
- End of session → add a `governance/ai-usage-log/` entry.
- Never commit API keys, `.env`, or unscrubbed transcripts.
