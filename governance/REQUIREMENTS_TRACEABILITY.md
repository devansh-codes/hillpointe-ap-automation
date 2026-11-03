# Requirements Traceability Matrix

Every requirement from the Candidate Brief (B), the AP Policy (P §n), the Import Field Guide (FG), and the domain
walkthrough reviewed in session 02 (W) maps to where the plan handles it and the test that proves it. Test names are
the real pytest ids as of 2026-11-02, checked against `uv run pytest --collect-only`. Rows with no test say
"not automated" and how the requirement is shown instead.

## Intake, extraction, routing

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R01 | Read vendor, invoice no, date, lines, reference, remit/bank details from each PDF | W Task 1-A | §3.1 #2, §3.2 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_golden_batches.py::test_batch02_after_batch01`, `tests/test_live_tooling.py::test_claude_request_shape_and_cache` (golden tests run on hand labels; model-vs-label accuracy is `make eval`, not pytest) |
| R02 | Verify AI output against the source document | W Task 1-A | §3.1 #2b grounding | `tests/test_live_tooling.py::test_grounding_catches_a_misread_number` |
| R03 | Detect watermarks/markings (REVISED, REPRINT, PAST DUE) | inferred from batch 02 | ADR-0002 | `tests/test_golden_batches.py::test_batch02_after_batch01` (asserts REPRINT and PAST DUE in the DUP messages) |
| R04 | Active vendor IDs only; never Inactive merged records | P §8, W 1-B | rule 3 | `tests/test_synthetic_holdout.py::test_inactive_vendor_resolves_to_surviving_record` |
| R05 | Vendor not in master → NEWVEND, never create an ID | P §8 | rule 3 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0112]` |
| R06 | Status → system/entity routing (Active Construction → Intacct/HPC; Stabilized → Entrata/owner; none → Intacct/HCM) | P §2, W Part 1 | rule 7, `policy.yaml: routing` | `tests/test_golden_batches.py::test_0008_entrata`, `tests/test_golden_batches.py::test_0002_allocation_and_one_time_service`, `tests/test_golden_batches.py::test_0003_pay_app_retainage_closed_period` |
| R07 | Construction → HPC regardless of bill-to | P §2 | §3.4 | `tests/test_golden_batches.py::test_0014_billto_correction_and_not_a_cross_vendor_dup`, `tests/test_units.py::test_bill_to_entity_outside_intacct_and_entrata` |
| R08 | Bill-to not a Hillpointe entity → hold | P §2 | rule 5 | `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A02_non_entity_billto]`, `tests/test_units.py::test_bill_to_entity_outside_intacct_and_entrata`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0121]` |

## Matching

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R09 | Construction must reference PO/SC → else NOPO, note the likely match, don't code to it | P §6 | rule 8 | `tests/test_golden_batches.py::test_0012_nopo_names_likely_match`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0115]` |
| R10 | Remaining PO balance = PO − history − credits − this run's entries | P §6, W 1-D | rule 10, §4.5 | `tests/test_golden_batches.py::test_0001_overpo_nets_credit_processed_first`, `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A15_arithmetic_does_not_tie]` (A15: PO exhausted by an earlier doc in the same run) |
| R11 | Over PO by > $500 → OVERPO | P §6 | rule 10 | `tests/test_golden_batches.py::test_0001_overpo_nets_credit_processed_first`, `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A05_over_po_by_499_within_tolerance]`, `tests/test_synthetic_holdout.py::test_holdout_B[SYN_B04_over_po_by_501]` |
| R12 | Price is right (two-way match) | W Part 1 | rule 9 | `tests/test_synthetic_holdout.py::test_price_variance_warns` |
| R13 | Stabilized service amount = SA monthly fee | P §6 | rule 16 | `tests/test_golden_batches.py::test_0008_entrata`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0105]` (matching-fee path only; a fee mismatch → hold is not automated) |

## Coding

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R14 | Cost code/type from PO line; cost type → COGS GL | P §3–4 | §3.4 | `tests/test_golden_batches.py::test_0003_pay_app_retainage_closed_period`, `tests/test_golden_batches.py::test_0005_vendor_terms_override_invoice_terms`, `tests/test_golden_batches.py::test_0010_two_po_lines_tax_prorated` |
| R15 | Multi-line PO → one bill line per PO line | P §4.2 | §3.4 | `tests/test_golden_batches.py::test_0010_two_po_lines_tax_prorated`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0102]` |
| R16 | Tax/freight/delivery follow their line; single tax total pro-rated, remainder to largest line | P §4.3 | §3.4 | `tests/test_units.py::test_prorate_penny_goes_to_largest_line`, `tests/test_golden_batches.py::test_0010_two_po_lines_tax_prorated` |
| R17 | Pay app: gross line + negative retainage line to 20500, same dims; total = current due | P §5.1, FG | §3.4 | `tests/test_golden_batches.py::test_0003_pay_app_retainage_closed_period`, `tests/test_synthetic_holdout.py::test_revised_payapp_entered_and_supersedes_original` |
| R18 | Pay app math + previous certificates agree to history (+ ledger) | P §5.2 | rule 14 | `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0103]`, `tests/test_synthetic_holdout.py::test_holdout_B[SYN_B02_revised_payapp_without_pending_co]` (agreeing path only; a mismatch → hold is not automated) |
| R19 | Lien waiver required & missing → LIEN | P §5.3 | rule 12, §4.4 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_synthetic_holdout.py::test_waiver_on_file_clears_lien_but_coi_still_holds` |
| R20 | COI expired before bill date → COI | P §5.4 | rule 13 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_policy_changes.py::test_coi_grace_period_releases_coi_only`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0120]` |
| R21 | Pending CO billed → hold whole app, UNAPPCO | P §5.5 | rule 11 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0119]`, `tests/test_synthetic_holdout.py::test_revised_payapp_entered_and_supersedes_original` |
| R22 | Credit memo: Adjustment, negative, original's coding, original no. in description, due = bill date | P §9, P §7 | rule 15, §3.4 | `tests/test_golden_batches.py::test_0011_credit_is_adjustment`, `tests/test_synthetic_holdout.py::test_credit_without_original_is_medium` |
| R23 | Shared software allocation, cent rounding to HCM; one-time services 100% HCM 65010 | P §2 | §3.4 | `tests/test_golden_batches.py::test_0002_allocation_and_one_time_service`, `tests/test_units.py::test_allocation_rounding_to_hcm`, `tests/test_synthetic_holdout.py::test_docx_software_allocation` |
| R24 | Entrata handoff, split rows per Entrata GL | P §3, template | §3.4 | `tests/test_golden_batches.py::test_0008_entrata`, `tests/test_synthetic_holdout.py::test_corrected_sterling_splits_two_entrata_rows` |
| R25 | BILL_DATE as printed; GL posting in open period else first day of open period | P §7 | §3.4 | `tests/test_golden_batches.py::test_0003_pay_app_retainage_closed_period`, `tests/test_policy_changes.py::test_open_period_override_moves_posting_date`, `tests/test_interview_drill.py::test_drill_details` |
| R26 | Terms from vendor master, not the invoice; due = bill date + days | P §7 | §3.4 | `tests/test_golden_batches.py::test_0005_vendor_terms_override_invoice_terms`, `tests/test_policy_changes.py::test_net45_for_one_vendor` |
| R27 | Import file valid (required fields, no 20000/25xxx, 80-char limits, lines sum to total) | FG | §3.1 #5b | `tests/test_golden_batches.py::test_output_files_match_template` (19 columns, no 20000/250xx, lines sum to total); required-field and 80-char checks not automated |

## Controls & exceptions

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R28 | Payment/contact detail differences or change request → BANKCHG → Treasury; never use invoice contacts | P §8, W Task 2 | rule 4 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0113]` |
| R29 | Held docs are not entered at all, even partly | P §11 | rules engine | `tests/test_golden_batches.py::test_output_files_match_template` (import has exactly the 11 lines of entered bills; 8 held docs add none) |
| R30 | Exception log row: file, vendor, inv no, amount, code, reason, route, confidence | B Deliv. 2 | §3.1 #6 | `tests/test_golden_batches.py::test_output_files_match_template`, `tests/test_policy_changes.py::test_exception_route_change`, `tests/test_ui.py::test_runs_exceptions_and_document_source` (full column set not asserted) |
| R31 | Approvers for every entered bill per matrix | P §13, B | §3.3 | `tests/test_golden_batches.py::test_0003_pay_app_retainage_closed_period`, `tests/test_golden_batches.py::test_0002_allocation_and_one_time_service`, `tests/test_synthetic_holdout.py::test_keystone_entrata_with_rpm` |
| R32 | Confidence with a plain-English reason | B, W Task 2 | §3.5 | `tests/test_synthetic_holdout.py::test_inactive_vendor_resolves_to_surviving_record`, `tests/test_synthetic_holdout.py::test_arithmetic_failure_is_low_confidence`, `tests/test_live_tooling.py::test_explain` |
| R33 | Standalone lien waiver → not entered, OTHER | P §11, W | rule 1 | `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A19_standalone_lien_waiver]`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0131]` |

## Duplicates & reruns

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R34 | Check against history **and** prior runs | P §10 | §4.6 | `tests/test_golden_batches.py::test_batch01_decisions`, `tests/test_synthetic_holdout.py::test_holdout_B[SYN_B03_copy_of_entered_invoice]`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0116]` |
| R35 | Normalise inconsistent invoice-number formatting | P §10, W Task 3 | §4.1 | `tests/test_golden_batches.py::test_0015_formatting_drift_dup`, `tests/test_units.py::test_norm_bill_no`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0117]` |
| R36 | Same vendor + same amount isn't a dup by itself; compare service period | P §10, W Task 3 | §4.1 L3 | `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A08_recurring_same_amount_new_month]` |
| R37 | Same number, different vendor isn't a dup | P §10 | §4.1 | `tests/test_golden_batches.py::test_0014_billto_correction_and_not_a_cross_vendor_dup` |
| R38 | Revised invoice: only one version ever entered | P §10 | §4.2 | `tests/test_golden_batches.py::test_batch02_after_batch01`, `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A06_revision_after_original_entered]`, `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A07a_original_same_batch]` |
| R39 | Held doc returns → not a dup; re-check every rule | P §11, W Task 3 | §4.3 | `tests/test_synthetic_holdout.py::test_waiver_on_file_clears_lien_but_coi_still_holds`, `tests/test_synthetic_holdout.py::test_corrected_sterling_splits_two_entrata_rows`, `tests/test_golden_batches.py::test_rerun_batch01_is_idempotent` |
| R40 | Soft "possible duplicate" checks go to a person, not auto-reject | W Task 3 | §4.1 L3–L4 | not automated: no test triggers the L3/L4 "possible duplicate" → OTHER path; shown by reading `duplicates` in `src/ap_automation/rules/core.py` |
| R41 | Rerun Batch 01 → zero new bills | B Task 3 | §4, §7 | `tests/test_golden_batches.py::test_rerun_batch01_is_idempotent` |
| R42 | Batch 02 handled correctly | B Task 3 | SOURCE_ANALYSIS §3 | `tests/test_golden_batches.py::test_batch02_after_batch01`, `tests/test_golden_batches.py::test_rerun_batch02_again_is_idempotent` |
| R43 | Explain dup logic and where the registry lives; ship the registry | B Deliv. 3 | §4.6, `RERUN_EVIDENCE.md` | not automated: review of `RERUN_EVIDENCE.md` and the shipped `state/` registry (backed by `tests/test_golden_batches.py::test_db_unique_constraint_blocks_double_entry`) |

## Packaging & live session

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R44 | Rerun without us: README a non-programmer can follow | B Task 4, W Task 4 | §6 phase 7 | not automated: dry-run of `README.md` / `run.sh` by a non-developer |
| R45 | All rule values in one settings file | W Task 4 | §5 `policy.yaml`, §8 | `tests/test_policy_changes.py::test_overpo_tolerance_250_keeps_0001_held`, `tests/test_policy_changes.py::test_validate_rejects_bad_edits`, `tests/test_ui.py::test_every_knob_edits_policy_text_without_losing_comments` |
| R46 | AI reads; code decides (same input → same output) | W Task 4 | ADR-0001 | `tests/test_live_tooling.py::test_delete_latest_run_restores_ledger_and_is_reversible`, `tests/test_live_tooling.py::test_claude_request_shape_and_cache`, `tests/test_synthetic_holdout.py::test_holdout_A[SYN_A14_prompt_injection]` |
| R47 | Audit trail per document | B, W Task 4 | §7 | `tests/test_live_tooling.py::test_explain` (per-document trace; completeness of `decisions.jsonl` not asserted) |
| R48 | Runs unchanged on unseen invoices | B ground rules | §6 phase 6 | `tests/test_synthetic_holdout.py::test_holdout_A`, `tests/test_synthetic_holdout.py::test_holdout_B`, `tests/test_interview_drill.py::test_drill_outcome` |
| R49 | Live rule change (e.g. OVERPO $250, Net 45 for a vendor) | B, W | §8 | `tests/test_policy_changes.py::test_overpo_tolerance_250_keeps_0001_held`, `tests/test_policy_changes.py::test_net45_for_one_vendor`, `tests/test_live_tooling.py::test_rule_change_flow_restore_rerun_diff` |
| R50 | Prompts + AI usage log | B Deliv. 5 | AI usage log (separate deliverable), `prompts/` | not automated: review of `prompts/` and the AI usage log folder (report, sessions, generated prompt ledger and transcript; redaction enforced by `scripts/export_ai_log.py`) |
| R51 | One-page summary: approach, checks, what needs a person, time vs manual, what's next | B Deliv. 6 | §10 | not automated: review of `SUMMARY.md` |

## Live session (carries most of the weight)

| ID | Requirement | Source | Plan section | Test |
|---|---|---|---|---|
| R52 | Run on an arbitrary new folder with zero code/config edits | B ground rules + live session | §8.1 | `tests/test_live_tooling.py::test_cli_runs_a_zip_or_a_folder_of_folders`, `tests/test_live_tooling.py::test_damaged_files_are_held_and_the_batch_continues`; rehearsal not automated (AI usage log, session S05) |
| R53 | Pre-flight verification before going live | derived | §8.1 `doctor` | `tests/test_live_tooling.py::test_doctor_without_key` |
| R54 | New batch can duplicate Batch 01/02 → ledger shipped in post-Batch-02 state | B Task 3 + live | §8.1, ADR-0009 | `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0116]`, `tests/test_interview_drill.py::test_drill_outcome[APINBOX_0117]` (fixture rebuilds the post-Batch-02 state; the shipped `state/` itself is not test-checked) |
| R55 | Rule change applied and its effect shown on the same batch | B live session | §8.2 `--what-if`, snapshots, `diff` | `tests/test_live_tooling.py::test_what_if_does_not_commit`, `tests/test_live_tooling.py::test_rule_change_flow_restore_rerun_diff`, `tests/test_live_tooling.py::test_diff_reports_changes_beyond_the_decision` |
| R56 | Explain how any decision was made | B live session | §8.1 `explain` | `tests/test_live_tooling.py::test_explain` |
| R57 | API failure on one document doesn't fail the run | derived | §8.1, §9 | `tests/test_live_tooling.py::test_offline_mode_holds_uncached_docs_instead_of_crashing`, `tests/test_live_tooling.py::test_refusal_falls_back_then_gives_up`, `tests/test_live_tooling.py::test_damaged_files_are_held_and_the_batch_continues` |
| R58 | Run is fast enough for a screen share (< 90 s for ~15 docs) | derived | §8.1 concurrency | measured, not automated: 33 documents read live in 39 s, 20 in 29 s (AI usage log, session S09, session S07) |
| R59 | Accepts unexpected inputs (images, odd file names, non-invoices) | B "invoices you have not seen" | §8.1 | `tests/test_synthetic_holdout.py::test_unsupported_file_is_held_not_crashed`, `tests/test_synthetic_holdout.py::test_scanned_png_is_medium_confidence_and_coded`, `tests/test_synthetic_holdout.py::test_docx_software_allocation` |
| R60 | Non-parameter rule change in ≤ 10 lines from a template | B live session | §8.1, §8.4 | `tests/test_policy_changes.py::test_new_rule_from_template` |
| R61 | Two timed dress rehearsals passed from the runbook | derived | §8.3 | not automated: one untimed CLI dress rehearsal is logged (AI usage log, session S05); the two timed rehearsals are not yet done |
