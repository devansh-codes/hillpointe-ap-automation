# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
