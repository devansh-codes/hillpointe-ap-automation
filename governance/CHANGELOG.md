# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-11-02
### Added
- Web UI (`uv run ap ui` / `make ui`, ADR-0012): run a batch or import files, run feed, per-run tabs (documents, Intacct
  import, Entrata handoff, exceptions, approvals, downloads), document page with the source beside the decision, exceptions
  queue by route, ledger and snapshots with restore, rule editor with sandboxed impact preview, save/apply and undo,
  ⌘K search, system check, AI-usage card, guided "Get started" checklist.
- `run_meta.json` in every run folder (inbox path, what-if, extractor, policy hash).
- `tests/test_ui.py` (policy edits keep comments; API answers match the engine; preview never records; path traversal refused).
### Changed
- `ap doctor` and `ap diff`/`explain` now use shared modules (`health.py`, `runs.py`) that the UI also uses.
### Fixed
- `governance/EVALUATOR_GUIDE.md` Batch 01 table: 0007 and 0015 are DUP; 0009 is UNAPPCO + LIEN; 0013 is LIEN + COI.

## [0.2.1] - 2026-11-02
### Fixed
- Rerunning a folder no longer overwrites its automatic `pre-<folder>` snapshot, so `snapshot restore pre-01_Invoice_Batch_01`
  returns to the state before Batch 01 was first processed (found while verifying a fresh clone). New test; evidence
  regenerated from the cached extractions with outputs identical apart from run ids.
- Bills addressed to an entity outside Intacct/Entrata (OZF1, Juniper Square) with no project are held OTHER instead of silently posting to HCM (A-22; uses the Entities tab's AP System column).
- `uv run ap ...` now reads the API key from `.env` (previously only `./run.sh` did).
### Added
- Published to a private GitHub repo; manual end-to-end evaluation steps in `governance/EVALUATOR_GUIDE.md`.

## [0.2.0] - 2026-11-02
### Added
- Real-model extraction verified: 32/32 package documents, 24/24 unseen synthetic documents.
- Prompt caching, cache warm-up, per-document token/cost metering, role-specific schemas, one-turn validation repair.
- Prompt v2 (`observations` separate from `extraction_warnings`).
### Changed
- Bills use validated JSON; references use API-enforced schema (ADR-0011). Effort `medium` by measurement.
- Evidence in `output/` regenerated with Claude Opus 5.5.

## [0.1.0] - 2026-11-02
### Added
- Hybrid pipeline: Claude Opus 5.5 extraction (`messages.parse` + Pydantic schema, PDF/image/DOCX) → deterministic rules → coding → Field Guide validator → outputs → SQLite ledger.
- 16 policy rules (`src/ap_automation/rules/core.py`), all driven by `config/policy.yaml`.
- Outputs: Intacct CSV + XLSX on the provided template, Entrata handoff, exception log, approvals, run report (MD/HTML), decision trace (JSONL).
- Ledger with UNIQUE(vendor, normalised bill no), snapshots, what-if runs, CSV register.
- CLI: `run`, `doctor`, `explain`, `diff`, `snapshot save|restore|list`, `policy validate`, `reset-state`, `eval-extraction`.
- Hand-labelled ground truth for all 32 package documents; synthetic hold-out generator (24 scenarios, 2 layouts, PNG, DOCX).
- 92 tests; Makefile (`test`, `evidence`, `demo`, `eval`), `run.sh`, README for the AP team.
### Changed
- Plan deviations C-1 to C-10 recorded in `PLAN.md` §11 (notably: no temperature parameter; A-13 → NOPO).
### Fixed
- YAML reads bare `NO` as boolean: quoted, plus a validator guard.
- Run ids now unique to the millisecond.
- A resent bill is no longer counted against its own PO balance.
