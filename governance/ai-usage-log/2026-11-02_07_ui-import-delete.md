# 2026-11-02 · 07 · UI: folder import, delete run, accuracy re-check

**Tool:** Claude Code (Opus 5.5). **Human:** Devansh.

## Asked
1. Remove the "System ready" indicator from the sidebar.
2. Import a whole batch (folder / many documents), not one file at a time.
3. Delete a batch's results with a formal warning; confirm Batch 01, its rerun and Batch 02 are accurate.

## Done
- Import: folder picker and folder drag-and-drop (recursive), many files, `.zip` unpacked server-side; flattened into one
  inbox, name clashes suffixed, OS junk and `../` zip entries dropped, unreadable types flagged before upload.
- Delete run (ADR-0013): latest recorded run or any preview; impact dialog with typed `DELETE`; ledger rows undone in one
  transaction (incl. supersede flags), `before-delete-<run>` snapshot, output archived to `state/deleted_runs/`,
  `state/audit_log.jsonl`. CLI `ap delete-run`. Tests: ledger identical to pre-run state after delete; rerun gives the same
  decisions; older run refused; confirmation required.
- Accuracy: the three submitted runs match `SOURCE_ANALYSIS.md` document by document (6 entered = 152,562.56; rerun 7 already
  processed; Batch 02 2 entered / 3 DUP).
- Found: a live `holdout_B` run done without `holdout_A` first differs from the guide's table. That is expected (B depends on
  what A entered). Verified in a sandbox with the real model, A then B from `submitted`: A 20/20, B 4/4. Guide now says so.

## Human decisions
- Delete must warn formally; chosen design (latest-only + typed confirmation + snapshot/archive/audit) by the AI, open to change.

## Follow-up: confidence display, interview drill pack
- UI: removed the High/Medium/Low chips (the user found "High" on every card noise). Kept a single amber "Check reading" tag
  on Medium/Low documents so the system still shows where it is unsure (the brief rewards this). Exports keep the column.
- Built `tests/synthetic/interview_drill.zip`: 33 blind documents on top of the submitted state. The hand-label run found two
  real gaps, now fixed: (1) a PDF holding two invoices was entered as one bill → now held OTHER (A-24), checked
  deterministically against the text layer, with no false positives across all 20 package and 57 synthetic documents;
  (2) a damaged PDF was sent to the model → now held at intake (A-25). Future-dated bills now carry a WARN (A-23, question 6
  for the controller).
- Live run with Claude Opus 5.5 (sandbox ledger, separate cache): 33/33 correct, 39 s, $1.05.
