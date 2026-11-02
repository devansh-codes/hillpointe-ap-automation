# governance/ — Project Context, Decisions & AI Usage Record

This folder is the **single source of context** for this project. Any person or AI coding agent (Claude Code, Codex,
Cursor, Copilot…) that checks out this branch should read it before changing anything. It also serves as the
**AI usage log** deliverable that Hillpointe asked for.

## Reading order

| # | File | What it gives you |
|---|---|---|
| 1 | `../AGENTS.md` | Ground rules for agents working in this repo (short) |
| 2 | `PLAN.md` | Problem → approaches considered → chosen architecture → phases → verification → risks |
| 3 | `SOURCE_ANALYSIS.md` | What every source document contains and the expected outcome for each invoice (test answer key) |
| 4 | `DECISIONS.md` | Architecture Decision Records (ADR-0001…) |
| 5 | `ASSUMPTIONS_AND_QUESTIONS.md` | Every judgment call + questions emailed to Hillpointe |
| 5b | `REQUIREMENTS_TRACEABILITY.md` | Every requirement → plan section → test (61 rows) |
| 5d | `EVALUATOR_GUIDE.md` | Step-by-step manual end-to-end test in the terminal, with expected results |
| 5c | `LIVE_SESSION_RUNBOOK.md` | Minute-by-minute script for the 45-min live session, with failure playbook |
| 6 | `ai-usage-log/` | Session-by-session record of how AI was directed (prompts, outputs, corrections) |
| 7 | `TECH_STACK.md` | Tools, versions, why |
| 8 | `RERUN_EVIDENCE.md` | Duplicate logic + ledger location + rerun outputs |
| 9 | `CHANGELOG.md` | What changed, when, and why ([Keep a Changelog](https://keepachangelog.com) format) |

## Standards this folder follows

| Practice | Standard / convention | Where |
|---|---|---|
| Agent instructions | `AGENTS.md` open convention (read by most coding agents); `CLAUDE.md` imports it | repo root |
| Decision records | Architecture Decision Records, MADR-lite format | `DECISIONS.md` |
| AI risk management | NIST AI RMF 1.0 functions mapped below; human-in-the-loop for every hold | this file |
| Financial controls | AP internal-control basics: PO/contract match, duplicate prevention, vendor-master change verification (call-back), approval matrix, segregation of duties (system proposes, humans approve), immutable audit trail | `PLAN.md` §3, §9 |
| Prompt management | Versioned prompt files; prompt version + model in every cached extraction and decision record | `prompts/`, ADR-0003 |
| Change history | Keep a Changelog + Conventional Commits | `CHANGELOG.md`, git log |
| Data handling | Package data is fictional (brief permits public AI tools). Transcripts are scrubbed before commit | below |

### NIST AI RMF mapping (lightweight)

| Function | How this project addresses it |
|---|---|
| **Govern** | This folder; ADRs; named owner; assumptions logged; AI usage log |
| **Map** | `SOURCE_ANALYSIS.md` (context & failure modes); `PLAN.md` §9 risk register |
| **Measure** | Golden tests, synthetic hold-out set, grounding and arithmetic checks, per-document confidence |
| **Manage** | Hold-and-route on low confidence; humans approve every bill; ledger + rerun idempotency; rule changes via reviewed config diffs |

## AI usage log conventions

- One markdown file per working session: `ai-usage-log/YYYY-MM-DD_NN_<topic>.md` with: goal, the user's prompts (verbatim),
  what the AI did, what was accepted / corrected / rejected and why.
- Raw transcripts (Claude Code `.jsonl` under `~/.claude/projects/…`) can be exported to `ai-usage-log/raw/` **after
  redaction**. ⚠️ Raw transcripts on the author's machine also contain unrelated context from a global `~/CLAUDE.md`
  (other projects' infrastructure details). Always scrub before committing; never commit raw transcripts unreviewed.
- Prompts the *product* uses (e.g. the extraction prompt) are not logged here; they're versioned in `prompts/`.

## For AI agents: how to update this folder

1. Made a design decision? Append an ADR to `DECISIONS.md`. Never rewrite an accepted one; supersede it.
2. Made an assumption? Add a row to `ASSUMPTIONS_AND_QUESTIONS.md`.
3. Finished a working session? Add an `ai-usage-log/` entry.
4. Changed expected outcomes? Update `SOURCE_ANALYSIS.md` **and** the golden tests in the same change.
