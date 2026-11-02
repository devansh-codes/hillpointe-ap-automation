# Session 02 — Plan gap review against domain walkthrough

- **Date:** 2026-11-02
- **Tool:** Claude Code (VS Code extension), Claude Opus 5.5
- **Goal:** Check that the plan covers everything in a plain-English AP domain walkthrough (vocabulary + the four tasks) that the operator pasted in.

## Prompt (verbatim)

> [pasted: AP domain walkthrough — vocabulary, entities, systems, coding, job costing, PO/SC/SA matching, vendor master, Tasks 1–4 in detail]
> are we making sure all of this is incorporated in our plan? if not go ahead and make the necassary changes

## Gaps found and fixed

| Gap | Fix |
|---|---|
| No unit-price check ("is the price right?") | Rule 9 price variance, warn by default (A-17) |
| Service period not used in dup logic | Added to extraction schema; dup layer L3 |
| "Close dates" soft dup check missing | Dup layer L4 with configurable window |
| Revision suffixes (`-R1`) and "original + revision in same batch" not handled | §4.2 revision table, A-21 |
| Returned held docs not explicitly linked | §4.3 with `returns_document_id` |
| Standalone lien waiver followed by the returning pay app | §4.4 `waivers_on_file`, A-16 |
| Credit memo "same coding as the original" not looked up | Rule 15, A-20 |
| Previous certificates only checked against history | Rule 14 now checks history ∪ ledger |
| Registry schema not spelled out (key, decision, run date, file name) | §4.6 table schema |
| Confidence not defined | §3.5 rubric with reason text |
| Rule change "Net 45 for this vendor", open-month override, routing table in config | §8 drills + `policy.yaml` contents |
| README audience not explicit | Phase 7: written for a non-programmer on the AP team |
| Entrata split-row case not tested (Sterling held in package) | Synthetic test + SOURCE_ANALYSIS trap 18 |
| No traceability from requirement to test | New `REQUIREMENTS_TRACEABILITY.md` (51 requirements) |

## Already covered (no change)

Entities and routing, bill-to correction vs non-entity hold, job cost dimensions, cost type → GL, multi-line PO, tax pro-rating,
retainage lines, lien/COI/UNAPPCO, BANKCHG with call-back, approval matrix, idempotent rerun, LLM-reads/code-decides split,
audit trail, prompts and usage log, one-page summary.
