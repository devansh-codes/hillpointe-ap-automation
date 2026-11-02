# Source Analysis — Expected Outcome per Document

> Status: **verified**: the engine reproduces every row below (tests/test_golden_batches.py). Originally a
> hypothesis / answer key for regression tests, produced during planning (2026-11-02) by reading every
> file in the package by hand with AI assistance. The pipeline must *derive* these results from the rules; this file
> exists so tests can assert against it and so reviewers can see our reasoning. Where we made a judgment call it
> is tagged **[ASSUMPTION A-n]** → see `ASSUMPTIONS_AND_QUESTIONS.md`.

## 0. Inventory read

| Folder | Files | Notes |
|---|---|---|
| 00_READ_ME_FIRST | Candidate_Brief.docx | Task, deliverables, live-session format |
| 01_Invoice_Batch_01 | APINBOX_0001–0015.pdf | All have a text layer (no OCR needed). 0003 is 2 pages (pay app + lien waiver) |
| 02_Reference_Data | Hillpointe_Master_Data.xlsx | Tabs: README, Entities, Projects, Departments, GL_Intacct, GL_Entrata, Cost_Codes, Cost_Types, Vendors, Allocation_Table, Periods |
| 03_Purchase_Orders_and_Subcontracts | 7 POs, 3 SC excerpts, 2 service agreements | SC excerpts carry Change Order logs (status matters) |
| 04_AP_Policy | AP_Coding_Rules_and_Approval_Matrix.docx | §1–13: routing, dimensions, job cost, pay apps, PO match, dates, vendor master, credits, dups, holds, codes, approvals |
| 05_ERP_Import_Template | AP_Bill_Import_Template.xlsx | Field_Guide, Import_Template (19 cols), Example_Completed, Entrata_Handoff (14 cols) |
| 06_ERP_History | Previously_Entered_Bills.xlsx | 25 bills (21 Intacct, 4 Entrata), header-level |
| 07_Invoice_Batch_02_Rerun | APINBOX_0016–0020.pdf | **Visual watermarks**: 0017 "REPRINT", 0020 "PAST DUE" — only partially visible in the text layer (scattered letters). 0018 header says "REVISED INVOICE". |

Key reference facts used below:
- Open period: **October 2026** (Sept closed, Nov future).
- Projects: 2410315 Columbia (HPC, active construction), 241088 Kingsland East (HPC, active construction), 310522 Athens / 3206040 Simpsonville / 231138 Statesboro (stabilized → Entrata).
- COI: Tri County Drywall (V1010) expired **2026-09-15**. All others valid through 2026-12 or later.
- Lien waiver required: V1001, V1005, V1006, V1010.
- V1092 Ridgeway Equipment Rentals is **Inactive** (merged into V1002).
- SC2410315-06 (Summit) CO2 $18,400 is **Pending, not executed**.

## 1. Batch 01 — expected decisions

### Entered in Sage Intacct (6 bills)

| File | Vendor | Bill No | Amount | Why it passes | Coding | Approvers |
|---|---|---|---|---|---|---|
| 0002 | V1008 LedgerLoop | LL-2026-1184 | 4,682.25 | Corporate, Order Form OF-2024-0332, remit matches | Subscription 3,632.25 split per Allocation_Table on GL 66025: HCM 1,452.90 / HPC 1,271.29 / HPM 908.06 (rounding diff 0.00 → HCM). Implementation 1,050.00 → HCM GL 65010 (one-time, not allocated). Dept IT (vendor Owner Dept). Due 10/31/2026 | IT department head (< $25k, no CFO) |
| 0003 | V1001 Gulfline | GCP-0303 | 133,650.00 | Pay app 3 math ties: prev certs 183,600 = 86,400 + 97,200 (history); completed-to-date 352,500 = 96,000+108,000+148,500. Conditional waiver attached for 133,650. COI 2027-03-31. No pending COs | L1 51000 gross 148,500.00; L2 20500 retainage −14,850.00; 2410315 / 03300 / S / HPC / OPS. Bill date 09/30/2026 (Sept closed) → **GL posting 10/01/2026**; due 10/30/2026 | PM Pointe Grand Columbia **+ VP Construction** (gross > $100k) |
| 0005 | V1003 Coastal Site | CSS-88502 | 1,240.00 | PO2410315-011 ($18,000; billed 2,480) → remaining 15,520. Recurring same amount ≠ duplicate | 54000 / 01540 / O / 2410315. Terms **Net 15 from vendor master** (invoice says "Due upon receipt") → due 10/16/2026 | PM Pointe Grand Columbia |
| 0010 | V1002 Ridgeway | RER-77310 | 7,068.60 | PO2410315-014 two lines ($25,000; billed 3,240) | L1 telehandler + delivery 5,200 + tax 416.00 = **5,616.00** → 53000 / 06100 / E. L2 scissor lift + delivery 1,345 + tax 107.60 = **1,452.60** → 53000 / 09250 / E. Tax allocated pro-rata. Due 11/04/2026 | PM Pointe Grand Columbia |
| 0011 | V1004 Pinecrest | CM-PBS-604102 | −2,160.00 | Credit memo vs original PBS-603977 (in history) | **DOC_TYPE Adjustment**, 50000 / 06100 / M / 2410315, −2,160.00 (incl. tax). Description references PBS-603977. Due date = bill date 10/02/2026 | AP Manager review |
| 0014 | V1007 Copperline | 55388 | 8,081.71 | PO241088-031 ($20,000; billed 9,697.59) → remaining 10,302.41. **Same invoice no. as Live Oak Electric 55388 in history — different vendor, not a dup.** Bill-to "Hillpointe, LLC" is a Hillpointe entity → post to HPC, **informational** bill-to correction | 50000 / 22000 / M / 241088 / HPC. Due 11/06/2026 | PM Pointe Grand Kingsland East |

### Entrata handoff (1 row)

| File | Property | Owner | Project | Vendor | Inv No | Date | Post Month | Due | Entrata GL | Amount | Approver |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0008 | Pointe Grand Athens | PGATH | 310522 | V1012 Magnolia Pool | MPS-4471 | 10/01/2026 | 10/2026 [A-7] | 10/31/2026 | 6200-0085 Pool & Spa Service | 1,475.00 (= SA monthly fee) | Community Manager, Pointe Grand Athens |

### Not entered (8 exceptions)

| File | Vendor | Inv No | Amount | Code(s) | Reason | Route | Confidence |
|---|---|---|---|---|---|---|---|
| 0001 | V1004 Pinecrest | PBS-604418 | 15,102.07 | **OVERPO** | PO2410315-008 $180,000; billed 168,450 (−2,160 credit 0011 = 166,290) → remaining 13,710.00; invoice exceeds by **1,392.07** (3,552.07 if credit not netted) — > $500 either way [A-1]. Invoice note: "Additional quantities per field request from site super" | PM (Columbia) + Supply Chain | High |
| 0004 | Brightline Landscape Design | BLD-1007 | 6,500.00 | **NEWVEND** (+ notes) | Not in vendor master. Also: bill-to "Hillpointe Development" is not a legal entity; no PO/contract; asks for W9 by email. Likely 65020 Development Consulting once onboarded | Vendor Master team | High |
| 0006 | V1011 Sterling Grounds | SGP-11092 | 3,850.00 | **BANKCHG** | Remit address (Greenville vs Simpsonville), phone (0199 vs 0171), email domain, and an explicit request to change bank account to ending 9930. Amount matches SA. **Possible business-email-compromise pattern.** Treasury verifies by calling (864) 555-0171 on file | Treasury | High |
| 0007 | V1007 Copperline | 55102 | 9,697.59 | **DUP** | Exact match to AP-260922 (same vendor, number, amount, date) | AP Manager | High |
| 0009 | V1005 Summit Framing | SFG-2410-05 | 103,140.00 | **UNAPPCO** (+ LIEN) | Bills CO2 $18,400 which is "Pending, not executed"; contract sum shown 924,900 vs executed 906,500. Hold entire application. Also no conditional lien waiver attached (V1005 requires one). Math otherwise ties (prev certs 460,800 = history) | PM (Columbia); return to subcontractor; Compliance for waiver | High |
| 0012 | V1009 Harbor Point | HPA-31877 | 16,948.80 | **NOPO** | No PO, ship-to "Hillpointe jobsite". **Likely match PO241088-022** (rate $38.40/ton matches Kingsland East PO, Columbia PO is $41.10; 7% tax = GA). Do not code until PM confirms | PM (Kingsland East) | High (hold) / Medium (likely match) |
| 0013 | V1010 Tri County Drywall | TCD-2410-02 | 57,600.00 | **LIEN** + **COI** (primary per precedence, C-5) | COI expired 2026-09-15 < bill date 09/29/2026. Waiver "to follow under separate cover". Math ties (prev 36,900 = TCD-2410-01) | Construction Compliance (Projects & Compliance) | High |
| 0015 | V1002 Ridgeway | INV-20417 | 3,240.00 | **DUP** | History AP-260917 keyed as "20417" — same vendor, amount, date; number differs only by "INV-" prefix | AP Manager | High |

Totals: 6 Intacct + 1 Entrata + 8 exceptions = 15 ✔

## 2. Rerun of Batch 01 (expected)

Every file hash is already in the ledger. Entered documents → `ALREADY_PROCESSED`, no new import rows. Held documents are
re-evaluated against current rules (policy §11) and stay on hold with the same codes. **Import file: 0 rows.**

## 3. Batch 02 (expected)

| File | Vendor | Inv No | Amount | Outcome | Reason |
|---|---|---|---|---|---|
| 0016 | V1003 Coastal | CSS-88611 | 2,180.00 | **Enter** | PO241088-009 ($8,000; billed 2,180) → remaining 5,820. 54000 / 01560 / O / 241088. Net 15 → due 10/23/2026. Approver PM Kingsland East |
| 0017 | V1002 Ridgeway | RER-77310 | 7,068.60 | **DUP** | "REPRINT" watermark; entered in run 1 (from 0010) |
| 0018 | V1009 Harbor Point | HPA-31877 | 16,948.80 | **Enter** (supersedes 0012) | "REVISED INVOICE … Replaces original HPA-31877", now references PO241088-022. Original was held, never entered → revised version is the only one entered. 50000 / 31230 / M / 241088. PO remaining 27,673.60. Due 11/01/2026. Approver PM Kingsland East |
| 0019 | V1001 Gulfline | GCP-0303 | 133,650.00 | **DUP** | Resend of pay app entered in run 1 (identical content) |
| 0020 | V1003 Coastal | CSS-88502 | 1,240.00 | **DUP** | "PAST DUE" stamp; entered in run 1 (from 0005) |

## 4. Traps the package is deliberately testing (our checklist)

1. Invoice-number formatting drift in history (`INV-20417` vs `20417`).
2. Same invoice number, different vendor (`55388` Copperline vs Live Oak).
3. Same vendor + same amount every month is **not** a dup (Coastal, Sterling, Magnolia).
4. Revised invoice where the original was **held**, not entered.
5. Reprints / past-due stamps visible only as image watermarks.
6. Pending CO hidden inside an otherwise-correct pay app.
7. Lien waiver "attached" vs "to follow".
8. COI expiry vs bill date.
9. Bank change with plausible amount (fraud pattern) on an Entrata invoice.
10. Bill-to correction (informational) vs non-entity bill-to (hold).
11. Closed-period bill date → first day of open period.
12. Vendor-master terms override invoice terms.
13. Multi-line PO + single tax total → pro-rata allocation.
14. Shared software allocation with rounding to HCM; one-time services not allocated.
15. PO balance must include credits and our own earlier entries in the same run (ordering).
16. Inactive merged vendor record (V1092) must never be used.
17. No standalone lien waiver appears in Batch 01 or 02 (0003 and 0019 carry the waiver as page 2 of the pay app). The
    "not a bill → OTHER" path and the "held pay app returns" path are covered by the synthetic hold-out set instead.
18. If Sterling's 0006 were clean, it would split into **two** Entrata rows (6200-0055 Landscaping $3,150; 6200-0075 Pest $700),
    matching the history note. Covered by a synthetic test.
