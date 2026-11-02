# Rerun Evidence & Duplicate Logic (Deliverable 3)

## Where the record of processed invoices lives

| Path | What |
|---|---|
| `state/ap_ledger.db` | SQLite registry. Tables: `runs`, `documents` (every decision), `entered_bills` (**UNIQUE(vendor_id, bill_no_norm)**), `po_consumption`, `waivers_on_file` |
| `state/processed_register.csv` | Human-readable export of `documents`, refreshed after every committed run |
| `state/extractions/<sha256>.<prompt>.<model>.json` | Cached AI reading of each file, so reruns are identical and free |
| `state/snapshots/submitted.db` | Ledger after Batch 01 → rerun → Batch 02 (the state the live session starts from) |

Every run checks against **two sources**: `06_ERP_History` (read fresh each run) and this registry (all prior runs + earlier
documents in the same run). The ledger is committed in one transaction *after* all outputs are written, so a failed run
never half-records.

## How duplicates are decided (in order)

1. **Same file again** (same SHA-256 and file name) that was already entered → `ALREADY_PROCESSED`, no output rows.
   If it was held, it is re-evaluated under current rules (policy §11).
2. **L1:** vendor ID + normalised invoice number (upper-case; spaces, dashes and punctuation removed; `INV`/`INVOICE`/`BILL`/`NO`
   prefixes removed when followed by digits; leading zeros removed) → **DUP**.
3. **L2:** vendor ID + digits-only number + same amount → **DUP** (catches `INV-20417` vs history `20417`).
4. **Revisions** (REVISED marking, `-R1`/`REV` suffix, or "replaces invoice X"): original already entered → hold for the
   AP Manager; original held/never entered → evaluate the revision and mark the original superseded; original and revision
   in the same batch → only the latest is evaluated.
5. **Returned held document** (same key, previously held) → *not* a duplicate; every rule is re-checked.
6. **L3/L4 soft checks** → OTHER "possible duplicate" for a person: same vendor + amount + service period, or same vendor
   + amount within 7 days (shorter than a monthly cycle, so recurring bills don't trip it).
7. **Never a duplicate on its own:** same number from a different vendor; same vendor and amount in a different month.
8. **Last line of defence:** the database refuses a second `entered_bills` row with the same vendor + normalised number.

A resend is never counted against its own PO balance, so a DUP isn't also reported as OVERPO.

## Results

| Run | Docs | Entered (Intacct) | Entrata | Held | Already processed | New import rows |
|---|---|---|---|---|---|---|
| Batch 01 | 15 | 6 | 1 | 8 | 0 | 11 lines |
| Batch 01 rerun | 15 | 0 | 0 | 8 (same codes) | 7 | **0** |
| Batch 02 | 5 | 2 (0016, 0018) | 0 | 3 DUP (0017 REPRINT, 0019 resend, 0020 PAST DUE) | 0 | 2 lines |

- 0018 (REVISED HPA-31877, now with PO241088-022) is entered because the original 0012 was held for NOPO and never
  entered; 0012 is marked superseded in the ledger.
- After all three runs `entered_bills` holds 9 bills with no vendor + number repeated (asserted in `tests/test_golden_batches.py`).
- Run folders: `output/*_01_Invoice_Batch_01` (two) and `output/*_07_Invoice_Batch_02_Rerun`. Each has `run_report.md/html`.

> **Provenance:** the run folders in `output/` were produced with **real Claude Opus 5.5 extractions** (prompt v2, effort medium),
> served from `state/extractions/` (cached on first read, so the rerun used 0 tokens). Extraction accuracy against the hand labels:
> 32/32 (`make eval`). Every decision is identical to the hand-worked `SOURCE_ANALYSIS.md`, and all 35 decisions are High confidence.
