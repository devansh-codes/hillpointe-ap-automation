# Architecture Decision Records

Format: lightweight [MADR](https://adr.github.io/madr/). New decisions are appended; superseded ones are marked, never deleted.

---

## ADR-0001 — Hybrid architecture: LLM extracts facts, deterministic engine decides
- **Status:** Accepted · 2026-11-02
- **Context:** Must be correct, auditable, rerunnable, and survive unseen invoices plus a live rule change.
- **Options:** single LLM prompt; deterministic parsing; commercial IDP + rules; agentic tool loop; hybrid. Scored in `PLAN.md` §2.
- **Decision:** Hybrid (score 4.70 vs next best 3.35). Claude reads PDFs into a strict schema; Python applies policy.
- **Consequences:** Every accounting decision is reproducible code with a policy reference. Needs an API key only for
  documents not in the extraction cache.

## ADR-0002 — Claude Opus 5.5 with native PDF input + structured outputs
- **Status:** Accepted · 2026-11-02
- **Decision:** `claude-opus-5-5`, PDF passed as a base64 `document` block (model gets text + page images, so it sees
  "REPRINT"/"PAST DUE" watermarks), `client.messages.parse()` with a Pydantic model, effort configurable (default `high`),
  server-side refusal fallback enabled. Model ID and prompt version live in `config/settings.yaml`.
- **Rejected:** OCR-then-LLM (loses watermarks/layout); Textract/Azure DI (no pay-app/CO/lien semantics; extra cloud setup).
- **Note:** The Citations API can't be combined with structured outputs, so evidence grounding is done against the PDF text layer in code.
- **Input formats:** PDF → native `document` block. PNG/JPG → `image` block. DOCX → converted locally with `python-docx`
  (paragraphs + tables, in order) to plain text and sent as a text `document` block, since the API doesn't take .docx
  directly. XLSX reference data is read with `openpyxl`, never by the LLM. The policy .docx isn't extracted at runtime;
  its rules are encoded in `policy.yaml` + rule code (ADR-0005).
- **Alternatives kept configurable:** `claude-sonnet-5-5` (about half the cost, faster) can be benchmarked on the golden set.
  We switch only if it matches Opus field-for-field.

## ADR-0003 — Extraction cache keyed by file hash + prompt version + model, committed to git
- **Status:** Accepted · 2026-11-02
- **Decision:** `state/extractions/<sha256>.<prompt_ver>.<model>.json`. `--offline` runs only from cache.
- **Why:** Byte-identical reruns, reviewers without API keys can reproduce, and a prompt change visibly invalidates the cache.

## ADR-0004 — SQLite ledger with DB-enforced uniqueness + CSV export
- **Status:** Accepted · 2026-11-02
- **Options:** append-only JSONL; CSV; SQLite.
- **Decision:** SQLite (`state/ap_ledger.db`), one transaction per run, `UNIQUE(vendor_id, bill_no_norm)` on entered bills.
  Export `state/processed_register.csv` every run for human review and git diffs.
- **Why:** ACID commit-after-emit prevents half-recorded runs; the unique constraint is a last-line control even if
  application logic regresses.

## ADR-0005 — Policy as configuration, rules as a registry of small functions
- **Status:** Accepted · 2026-11-02
- **Decision:** Thresholds, routes, precedence and toggles in `config/policy.yaml`. Master-data tabs (periods, allocation,
  vendors, projects) are read live from the xlsx and never copied. Each rule is one function `(ctx) -> list[Finding]`
  registered in order.
- **Why:** The live rule change should take minutes and be easy to review as a diff.

## ADR-0006 — Run all rules; report every finding; pick primary code by precedence
- **Status:** Accepted · 2026-11-02
- **Decision:** No short-circuit. Exception log shows primary code + all secondary codes. Default precedence:
  BANKCHG > DUP > NEWVEND > NOPO > UNAPPCO > OVERPO > LIEN > COI > OTHER (configurable).
- **Why:** A held document that comes back must clear *every* issue (§11); the AP team should see them all up front.
  Fraud risk (BANKCHG) is routed first.

## ADR-0007 — Governance context lives in-repo (`governance/` + root `AGENTS.md`), not a git submodule
- **Status:** Accepted · 2026-11-02
- **Options:** git submodule; separate repo; in-repo folder.
- **Decision:** In-repo folder. `AGENTS.md` (the cross-tool agent-instructions convention) at the root, `CLAUDE.md` imports it.
- **Why:** A teammate who checks out the branch gets the context automatically. Submodules need `--recurse-submodules`
  and can silently fall out of step with the code.

## ADR-0009 — Live-session-first CLI: what-if runs, ledger snapshots, diff, explain, doctor, fault isolation
- **Status:** Accepted · 2026-11-02
- **Context:** The live session carries most of the weight. We must run unseen invoices unedited, then apply a rule change
  and show its effect, on a shared screen, in 45 minutes. An idempotent ledger alone means a post-change rerun would just
  report "already processed".
- **Decision:** The CLI gets `doctor`, `run --what-if` (no ledger commit), automatic `pre-<inbox>` snapshots plus
  `snapshot save/restore`, `diff`, `explain`, `policy validate`, concurrent extraction, and per-document fault isolation
  (a failed extraction becomes an OTHER hold, never a crashed run). Submitted ledger = post-Batch-02 snapshot `submitted`.
- **Consequences:** About 1.25 h more build time, deliberately prioritised over polish. Idempotency is preserved because
  what-if runs never write the ledger and restores are explicit and logged.

## ADR-0008 — Python 3.12 + uv toolchain
- **Status:** Accepted · 2026-11-02
- **Decision:** Python 3.12, `uv` for env/lock, `pydantic` v2, `anthropic` SDK, `pdfplumber`, `pypdfium2`, `openpyxl`,
  `pyyaml`, `typer`, `rich`, `rapidfuzz`, `pytest`, `reportlab` (synthetic test PDFs only). `Decimal` for all money.
- **Why:** Best PDF/Excel ecosystem; `uv sync` gives a one-command, lock-file-reproducible setup.

## ADR-0010 — Repeatability without temperature; label fixtures as the extraction answer key
- **Status:** Accepted · 2026-11-02
- **Context:** The planned control "temperature = 0" isn't available on Claude Opus 5.5 / API 2026-10-21. No API key was
  available while building.
- **Decision:** (1) Repeatability = hash-keyed extraction cache + schema + grounding + arithmetic; any failed check holds the
  document at Low confidence. (2) Hand-labelled `ExtractedDocument` JSON for every package document is used both as test
  fixtures (LabelExtractor) and as the scoring key for `ap eval-extraction`.
- **Consequences:** The decision engine is fully verified independently of the model. Model accuracy is measured separately
  and explicitly rather than assumed.

## ADR-0012 — Web UI as a thin layer over the CLI engine
- **Status:** Accepted · 2026-11-02
- **Context:** The terminal is hard to follow for an AP audience and in a live demo. The brief scores how clearly the system
  can be explained to an AP team.
- **Decision:** `ap ui` serves a local web app (FastAPI + one static HTML/JS page, no build step, 127.0.0.1 only). It calls the
  same `engine.run`, ledger, snapshots and policy validation as the CLI and reads run folders back from `output/`; it adds no
  business logic. Shared helpers (`runs.py`, `health.py`) back both the CLI and the UI so `diff`/`doctor` give identical answers.
  Rule changes are previewed in a throw-away copy of the ledger restored from `pre-<batch>`, so a preview never records anything.
  Policy edits keep the file's comments and layout, are validated before saving, and the previous version is kept for undo.
- **Consequences:** Everything the CLI does is visible and clickable (run, exceptions by route, document beside its decision,
  ledger, snapshots, rule preview/apply/undo). The CLI stays the source of truth and keeps working unchanged.

## ADR-0011 — Output enforcement per document role; token-efficiency practices
- **Status:** Accepted · 2026-11-02
- **Context:** First real API calls: structured outputs rejected the invoice schema (optional-field limit, then union limit, then
  grammar size). Prompt v1 caused over-use of `extraction_warnings`, so confidence was miscalibrated.
- **Decision:** (1) Bills use validated JSON (schema in the system prompt, strict Pydantic validation, one repair turn); references
  use API-enforced JSON schema; automatic fallback when a schema is too large. (2) Union-free API schema encoding (`""`, digit
  strings, single-item lists) converted back by `from_api`. (3) Prompt v2 separates uncertainty from observations. (4) Effort
  medium, chosen by measurement. (5) Prompt caching on the role-specific system prompt, warmed by the first request.
- **Consequences:** 32/32 extraction accuracy, 24/24 on unseen synthetic documents, ≈ $0.03/document. Any future prompt or
  schema change bumps `prompt_version` and is re-scored with `make eval` before use.
