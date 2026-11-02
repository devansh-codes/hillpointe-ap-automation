# Requirements Traceability Matrix

Every requirement from the Candidate Brief (B), the AP Policy (P §n), the Import Field Guide (FG), and the domain
walkthrough reviewed in session 02 (W) maps to where the plan handles it and the test that proves it. Test names are
targets for Phase 3–6. **A requirement isn't done until its test is green.**

## Intake, extraction, routing

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R01 | Read vendor, invoice no, date, lines, reference, remit/bank details from each PDF | W Task 1-A | §3.1 #2, §3.2 | `test_extraction_golden[*]` |
| R02 | Verify AI output against the source document | W Task 1-A | §3.1 #2b grounding | `test_grounding_rejects_unfound_amount` |
| R03 | Detect watermarks/markings (REVISED, REPRINT, PAST DUE) | inferred from batch 02 | ADR-0002 | `test_markings_0017_0020` |
| R04 | Active vendor IDs only; never Inactive merged records | P §8, W 1-B | rule 3 | `test_inactive_v1092_never_used` |
| R05 | Vendor not in master → NEWVEND, never create an ID | P §8 | rule 3 | `test_0004_newvend` |
| R06 | Status → system/entity routing (Active Construction → Intacct/HPC; Stabilized → Entrata/owner; none → Intacct/HCM) | P §2, W Part 1 | rule 7, `policy.yaml: routing` | `test_routing_table` |
| R07 | Construction → HPC regardless of bill-to | P §2 | §3.4 | `test_0014_billto_correction_info` |
| R08 | Bill-to not a Hillpointe entity → hold | P §2 | rule 5 | `test_non_entity_billto_holds` |

## Matching

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R09 | Construction must reference PO/SC → else NOPO, note the likely match, don't code to it | P §6 | rule 8 | `test_0012_nopo_with_likely_match` |
| R10 | Remaining PO balance = PO − history − credits − this run's entries | P §6, W 1-D | rule 10, §4.5 | `test_po_balance_includes_run_entries` |
| R11 | Over PO by > $500 → OVERPO | P §6 | rule 10 | `test_0001_overpo`, `test_overpo_499_vs_501` |
| R12 | Price is right (two-way match) | W Part 1 | rule 9 | `test_price_variance_warns` |
| R13 | Stabilized service amount = SA monthly fee | P §6 | rule 16 | `test_0008_sa_fee_match` |

## Coding

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R14 | Cost code/type from PO line; cost type → COGS GL | P §3–4 | §3.4 | `test_costtype_to_gl` |
| R15 | Multi-line PO → one bill line per PO line | P §4.2 | §3.4 | `test_0010_two_po_lines` |
| R16 | Tax/freight/delivery follow their line; single tax total pro-rated, remainder to largest line | P §4.3 | §3.4 | `test_tax_prorate_penny_to_largest` |
| R17 | Pay app: gross line + negative retainage line to 20500, same dims; total = current due | P §5.1, FG | §3.4 | `test_0003_payapp_lines` |
| R18 | Pay app math + previous certificates agree to history (+ ledger) | P §5.2 | rule 14 | `test_prev_certs_match_history` |
| R19 | Lien waiver required & missing → LIEN | P §5.3 | rule 12, §4.4 | `test_0013_lien`, `test_0009_lien_secondary` |
| R20 | COI expired before bill date → COI | P §5.4 | rule 13 | `test_0013_coi` |
| R21 | Pending CO billed → hold whole app, UNAPPCO | P §5.5 | rule 11 | `test_0009_unappco` |
| R22 | Credit memo: Adjustment, negative, original's coding, original no. in description, due = bill date | P §9, P §7 | rule 15, §3.4 | `test_0011_credit_adjustment` |
| R23 | Shared software allocation, cent rounding to HCM; one-time services 100% HCM 65010 | P §2 | §3.4 | `test_0002_allocation` |
| R24 | Entrata handoff, split rows per Entrata GL | P §3, template | §3.4 | `test_sterling_clean_splits_two_rows` |
| R25 | BILL_DATE as printed; GL posting in open period else first day of open period | P §7 | §3.4 | `test_0003_posting_date_oct1` |
| R26 | Terms from vendor master, not the invoice; due = bill date + days | P §7 | §3.4 | `test_0005_net15_overrides_due_on_receipt` |
| R27 | Import file valid (required fields, no 20000/25xxx, 80-char limits, lines sum to total) | FG | §3.1 #5b | `test_validator_*`, CI gate |

## Controls & exceptions

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R28 | Payment/contact detail differences or change request → BANKCHG → Treasury; never use invoice contacts | P §8, W Task 2 | rule 4 | `test_0006_bankchg` |
| R29 | Held docs are not entered at all, even partly | P §11 | rules engine | `test_held_doc_emits_no_rows` |
| R30 | Exception log row: file, vendor, inv no, amount, code, reason, route, confidence | B Deliv. 2 | §3.1 #6 | `test_exception_log_columns` |
| R31 | Approvers for every entered bill per matrix | P §13, B | §3.3 | `test_approvals_0003_vp_construction` |
| R32 | Confidence with a plain-English reason | B, W Task 2 | §3.5 | `test_confidence_reason_present` |
| R33 | Standalone lien waiver → not entered, OTHER | P §11, W | rule 1 | `test_standalone_waiver_other` |

## Duplicates & reruns

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R34 | Check against history **and** prior runs | P §10 | §4.6 | `test_dup_against_ledger` |
| R35 | Normalise inconsistent invoice-number formatting | P §10, W Task 3 | §4.1 | `test_0015_inv_prefix_dup` |
| R36 | Same vendor + same amount isn't a dup by itself; compare service period | P §10, W Task 3 | §4.1 L3 | `test_recurring_not_dup` |
| R37 | Same number, different vendor isn't a dup | P §10 | §4.1 | `test_0014_55388_not_dup` |
| R38 | Revised invoice: only one version ever entered | P §10 | §4.2 | `test_0018_supersedes_0012`, `test_revision_after_entered_holds`, `test_same_batch_latest_only` |
| R39 | Held doc returns → not a dup; re-check every rule | P §11, W Task 3 | §4.3 | `test_returned_held_doc_reevaluated` |
| R40 | Soft "possible duplicate" checks go to a person, not auto-reject | W Task 3 | §4.1 L3–L4 | `test_possible_dup_routes_other` |
| R41 | Rerun Batch 01 → zero new bills | B Task 3 | §4, §7 | `test_rerun_batch01_idempotent` |
| R42 | Batch 02 handled correctly | B Task 3 | SOURCE_ANALYSIS §3 | `test_batch02_golden` |
| R43 | Explain dup logic and where the registry lives; ship the registry | B Deliv. 3 | §4.6, `RERUN_EVIDENCE.md` | review |

## Packaging & live session

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R44 | Rerun without us: README a non-programmer can follow | B Task 4, W Task 4 | §6 phase 7 | dry-run by a non-dev |
| R45 | All rule values in one settings file | W Task 4 | §5 `policy.yaml`, §8 | `test_policy_change_overpo_250` |
| R46 | AI reads; code decides (same input → same output) | W Task 4 | ADR-0001 | `test_offline_runs_byte_identical` |
| R47 | Audit trail per document | B, W Task 4 | §7 | `test_decisions_jsonl_complete` |
| R48 | Runs unchanged on unseen invoices | B ground rules | §6 phase 6 | synthetic hold-out suite |
| R49 | Live rule change (e.g. OVERPO $250, Net 45 for a vendor) | B, W | §8 | `test_policy_change_*` drills |
| R50 | Prompts + AI usage log | B Deliv. 5 | `ai-usage-log/`, `prompts/` | review |
| R51 | One-page summary: approach, checks, what needs a person, time vs manual, what's next | B Deliv. 6 | §10 | review |

## Live session (carries most of the weight)

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R52 | Run on an arbitrary new folder with zero code/config edits | B ground rules + live session | §8.1 | `test_run_arbitrary_inbox_path`, rehearsal |
| R53 | Pre-flight verification before going live | derived | §8.1 `doctor` | `test_doctor_reports_missing_key` |
| R54 | New batch can duplicate Batch 01/02 → ledger shipped in post-Batch-02 state | B Task 3 + live | §8.1, ADR-0009 | `test_submitted_snapshot_catches_resend` |
| R55 | Rule change applied and its effect shown on the same batch | B live session | §8.2 `--what-if`, snapshots, `diff` | `test_whatif_does_not_commit`, `test_diff_shows_overpo_change` |
| R56 | Explain how any decision was made | B live session | §8.1 `explain` | `test_explain_contains_rule_trace` |
| R57 | API failure on one document doesn't fail the run | derived | §8.1, §9 | `test_extraction_failure_isolated` |
| R58 | Run is fast enough for a screen share (< 90 s for ~15 docs) | derived | §8.1 concurrency | timed rehearsal |
| R59 | Accepts unexpected inputs (images, odd file names, non-invoices) | B "invoices you have not seen" | §8.1 | synthetic hold-out suite |
| R60 | Non-parameter rule change in ≤ 10 lines from a template | B live session | §8.1, §8.4 | `test_rule_template_registers` |
| R61 | Two timed dress rehearsals passed from the runbook | derived | §8.3 | rehearsal log in `ai-usage-log/` |
