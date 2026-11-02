# AP Automation: One-Page Summary

**Approach.** AI reads; policy code decides. Claude Opus 5.5 reads each PDF, scan or Word file (text *and* page image, so
stamps like REPRINT or PAST DUE are seen) into a fixed schema of facts: vendor, numbers, lines, tax, pay-app figures, lien
waiver, bank-change requests. It never chooses a GL, entity, approver or hold. A deterministic engine applies Hillpointe's
AP policy as 16 small rules configured in one file (`config/policy.yaml`), codes the bill (tax pro-rating, retainage,
allocation, credits, dates and terms), validates it against the template's Field Guide, and writes the Intacct import,
Entrata handoff, exception log and approvals. A ledger records every decision so nothing is entered twice.

**Checks that keep it accurate**
- *On the AI's reading:* schema-enforced output; the invoice number and total must appear in the document's own text; lines +
  tax must equal the total and pay-app lines 1–8 must tie; each file is read once and cached by fingerprint, so reruns are
  identical. Any failure means the document is held at Low confidence. Text inside a document that tries to instruct the system is flagged.
- *On the decision:* all 16 rules run on every document (no short-circuit), so every reason is listed; every rule cites
  its policy §. PO balance includes history, credits and this run's entries. Vendor contact and bank details are compared to
  the master (BANKCHG → Treasury call-back). Previous certificates are tied to history.
- *On the output:* template validator (Intacct rejects the whole file on one bad row, so a failing bill is held instead);
  control totals in every run report; database-level uniqueness on vendor + normalised invoice number.
- *Tested:* 97 automated tests: all 20 package documents, Batch 01 rerun, Batch 02, 24 unseen synthetic scenarios (new
  layouts, scan, Word, revisions, returns, fraud signals, PO edges) and 11 rule-change drills.

**Batch results.** Batch 01: 6 bills to Intacct (11 lines, $152,562.56), 1 Entrata row, 8 held (OVERPO, NEWVEND, BANKCHG,
2× DUP, UNAPPCO+LIEN, NOPO with likely PO named, LIEN+COI). Rerun: 0 new rows. Batch 02: 2 entered (incl. revised HPA-31877,
whose original was held), 3 DUP (reprint, resend, past-due).

**What still needs a person**
- Every held document, routed by code (PM, Supply Chain, Compliance, Treasury, Vendor Master, AP Manager), with the reason in plain English.
- Medium-confidence entries (fuzzy vendor match, scanned image, price differs from PO, credit without its original on file).
- Approvals (listed per bill), Treasury's call-back on bank changes, and voiding an original when a revision arrives after it was entered.

**Time comparison (estimate).**

| | By hand | With this system |
|---|---|---|
| Batch 01 (15 docs) | ≈ 3–3.5 h: ~8 min per simple invoice; 20–30 min per pay app (history tie-out, waiver, COI, change orders); allocation, credit and duplicate searches on top | ≈ 2 min run + ≈ 30 min reviewing 8 exceptions and spot-checks |
| Batch 02 (5 docs) | ≈ 45 min, mostly duplicate hunting | ≈ 1 min + 5 min review |

Roughly 80–85% less AP time, and the remaining time is judgment, not keying.

**What I'd build next**
1. Inbox connector (email / AP mailbox) and direct Intacct/Entrata API posting instead of CSV, with approval-workflow hand-off.
2. Live ERP reads for PO balances, vendor master and history instead of extracts; a nightly vendor-master change monitor for BANKCHG.
3. An extraction quality dashboard (`ap eval-extraction` on a growing labelled set, per-field accuracy, drift alerts on new vendors).
4. A review UI where AP clears holds and the decision is written back to the ledger with the reviewer's name.
5. Receiving records for a three-way match, and contract-level billing-to-date for subcontracts.

*Measured with the real model:* extraction 32/32 against hand labels; 24/24 on unseen synthetic documents (new layouts, scan,
Word, injection); ≈ $0.03 and ≈ 1.5 s of wall time per document (8 in parallel), with prompt caching saving ≈ 30%.
