# Run report: 20261102-163926493_01_Invoice_Batch_01

- Inbox: `/Users/devanshchaudhary/Documents/Hillpointe_AP_Technical_Screen/01_Invoice_Batch_01`
- Extraction: `offline` · model `claude-opus-5-5` · prompt `v2`
- Policy hash: `8fd4bb314b07` · Ledger: **recorded** (committed right after these outputs were written)
- Processing order (credits first, then date, then name): APINBOX_0011.pdf, APINBOX_0015.pdf, APINBOX_0007.pdf, APINBOX_0013.pdf, APINBOX_0003.pdf, APINBOX_0009.pdf, APINBOX_0002.pdf, APINBOX_0005.pdf, APINBOX_0008.pdf, APINBOX_0012.pdf, APINBOX_0006.pdf, APINBOX_0004.pdf, APINBOX_0010.pdf, APINBOX_0001.pdf, APINBOX_0014.pdf

## Control totals

| Decision | Documents | Amount |
|---|---|---|
| ENTERED | 6 | 152,562.56 |
| ENTRATA_HANDOFF | 1 | 1,475.00 |
| HELD | 8 | 216,078.46 |
| NOT_A_BILL | 0 | 0.00 |
| ALREADY_PROCESSED | 0 | 0.00 |
| **Total in** | **15** | **370,116.02** |

Intacct import: 11 line(s) across 6 bill(s), lines total 152,562.56. Entrata handoff: 1 row(s).

## Documents

| File | Decision | Vendor | Invoice | Amount | Code | Route | Confidence |
|---|---|---|---|---|---|---|---|
| APINBOX_0011.pdf | ENTERED | V1004 Pinecrest Building Supply Co | CM-PBS-604102 | -2,160.00 |  | AP Manager review | High |
| APINBOX_0015.pdf | HELD | V1002 Ridgeway Equipment Rental Inc | INV-20417 | 3,240.00 | DUP | AP Manager | High |
| APINBOX_0007.pdf | HELD | V1007 Copperline Plumbing Supply Inc | 55102 | 9,697.59 | DUP | AP Manager | High |
| APINBOX_0013.pdf | HELD | V1010 Tri County Drywall Inc | TCD-2410-02 | 57,600.00 | LIEN, COI | Construction Compliance (Projects & Compliance) | High |
| APINBOX_0003.pdf | ENTERED | V1001 Gulfline Concrete Partners LLC | GCP-0303 | 133,650.00 |  | Project Manager, Pointe Grand Columbia; VP Construction (gross work 148,500.00 > 100,000) | High |
| APINBOX_0009.pdf | HELD | V1005 Summit Framing Group LLC | SFG-2410-05 | 103,140.00 | UNAPPCO, LIEN | Project Manager; return to subcontractor | High |
| APINBOX_0002.pdf | ENTERED | V1008 LedgerLoop Software Inc | LL-2026-1184 | 4,682.25 |  | Department head, Information Technology (IT) | High |
| APINBOX_0005.pdf | ENTERED | V1003 Coastal Site Services LLC | CSS-88502 | 1,240.00 |  | Project Manager, Pointe Grand Columbia | High |
| APINBOX_0008.pdf | ENTRATA_HANDOFF | V1012 Magnolia Pool Services LLC | MPS-4471 | 1,475.00 |  | Community Manager, Pointe Grand Athens | High |
| APINBOX_0012.pdf | HELD | V1009 Harbor Point Aggregates LLC | HPA-31877 | 16,948.80 | NOPO | Project Manager | High |
| APINBOX_0006.pdf | HELD | V1011 Sterling Grounds and Pest LLC | SGP-11092 | 3,850.00 | BANKCHG | Treasury | High |
| APINBOX_0004.pdf | HELD |  Brightline Landscape Design LLC | BLD-1007 | 6,500.00 | NEWVEND, NOPO, OTHER | Vendor Master team | High |
| APINBOX_0010.pdf | ENTERED | V1002 Ridgeway Equipment Rental Inc | RER-77310 | 7,068.60 |  | Project Manager, Pointe Grand Columbia | High |
| APINBOX_0001.pdf | HELD | V1004 Pinecrest Building Supply Co | PBS-604418 | 15,102.07 | OVERPO | Project Manager and Supply Chain | High |
| APINBOX_0014.pdf | ENTERED | V1007 Copperline Plumbing Supply Inc | 55388 | 8,081.71 |  | Project Manager, Pointe Grand Kingsland East | High |

## Why (per document)

### APINBOX_0011.pdf: ENTERED
- Approvers: AP Manager review
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0015.pdf: HELD
- **DUP** (hold): Already entered: V1002 invoice 20417 in Sage Intacct record AP-260917 (same amount). _[§10]_
- Confidence: **High**: Rule outcome is deterministic: DUP — Already entered: V1002 invoice 20417 in Sage Intacct record AP-260917 (same amount).

### APINBOX_0007.pdf: HELD
- **DUP** (hold): Already entered: V1007 invoice 55102 in Sage Intacct record AP-260922 (same amount). _[§10]_
- Confidence: **High**: Rule outcome is deterministic: DUP — Already entered: V1007 invoice 55102 in Sage Intacct record AP-260922 (same amount).

### APINBOX_0013.pdf: HELD
- **LIEN** (hold): Tri County Drywall Inc is marked Lien Waiver Required and no conditional waiver for the current payment (57,600.00) is attached or on file. The application says the waiver will follow under separate cover. _[§5.3]_
- **COI** (hold): Certificate of insurance expired 09/15/2026, before the bill date 09/29/2026. _[§5.4]_
- Confidence: **High**: Rule outcome is deterministic: LIEN — Tri County Drywall Inc is marked Lien Waiver Required and no conditional waiver for the current payment (57,600.00) is a

### APINBOX_0003.pdf: ENTERED
- Approvers: Project Manager, Pointe Grand Columbia; VP Construction (gross work 148,500.00 > 100,000)
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0009.pdf: HELD
- **UNAPPCO** (hold): Application bills change order(s) that are not executed: CO2 'Cabinet and grab bar blocking' 18,400.00 — status 'Pending, not executed'. Hold the entire application and return it to the subcontractor for a revised application. _[§5.5]_
- **LIEN** (hold): Summit Framing Group LLC is marked Lien Waiver Required and no conditional waiver for the current payment (103,140.00) is attached or on file. _[§5.3]_
- Confidence: **High**: Rule outcome is deterministic: UNAPPCO — Application bills change order(s) that are not executed: CO2 'Cabinet and grab bar blocking' 18,400.00 — status 'Pending

### APINBOX_0002.pdf: ENTERED
- Approvers: Department head, Information Technology (IT)
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0005.pdf: ENTERED
- Approvers: Project Manager, Pointe Grand Columbia
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0008.pdf: ENTRATA_HANDOFF
- Approvers: Community Manager, Pointe Grand Athens
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0012.pdf: HELD
- **NOPO** (hold): No PO or subcontract referenced. Likely match: PO241088-022 (Pointe Grand Kingsland East; unit rate matches, GA tax rate). Do not code to it until the project manager confirms. _[§6]_
- Confidence: **High**: Rule outcome is deterministic: NOPO — No PO or subcontract referenced. Likely match: PO241088-022 (Pointe Grand Kingsland East; unit rate matches, GA tax rate

### APINBOX_0006.pdf: HELD
- **BANKCHG** (hold): Payment/contact details differ from the vendor master: asks to change payment instructions ("IMPORTANT: Our banking information has changed effective immediately. Please update your records and remit all future pa"); remit address 'Sterling Grounds & Pest LLC, 9 Commerce Ct, Suite 210, Greenville, SC 29607' ≠ vendor master '1450 Fairview Rd, Simpsonville, SC 29680'; phone (864) 555-0199 ≠ phone of record (864) 555-0171; bank account ending 9930 ≠ account on file ending 2215. Treasury to verify by calling the phone number on file (864) 555-0171; never use contact details from the invoice. _[§8]_
- Confidence: **High**: Rule outcome is deterministic: BANKCHG — Payment/contact details differ from the vendor master: asks to change payment instructions ("IMPORTANT: Our banking info

### APINBOX_0004.pdf: HELD
- **NEWVEND** (hold): 'Brightline Landscape Design LLC' is not in the vendor master; do not create or guess an ID. _[§8]_
- **OTHER** (hold): Addressed to 'Hillpointe Development', which is not a Hillpointe legal entity. _[§2]_
- **NOPO** (hold): No PO or subcontract referenced. _[§6]_
- Confidence: **High**: Rule outcome is deterministic: NEWVEND — 'Brightline Landscape Design LLC' is not in the vendor master; do not create or guess an ID.

### APINBOX_0010.pdf: ENTERED
- Approvers: Project Manager, Pointe Grand Columbia
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0001.pdf: HELD
- **OVERPO** (hold): PO2410315-008 is 180,000.00; billed to date 166,290.00 (AP-260702 PBS-601220 62,300.00; AP-260809 PBS-602845 58,910.00; AP-260911 PBS-603977 47,240.00; this run CMPBS604102 -2,160.00); remaining 13,710.00. This invoice (15,102.07) exceeds it by 1,392.07, more than the $500 tolerance. Needs a PO change order. _[§6]_
- Confidence: **High**: Rule outcome is deterministic: OVERPO — PO2410315-008 is 180,000.00; billed to date 166,290.00 (AP-260702 PBS-601220 62,300.00; AP-260809 PBS-602845 58,910.00; 

### APINBOX_0014.pdf: ENTERED
- **INFO**: Bill-to correction: addressed to HLLC (Hillpointe, LLC); posted to HPC per the construction routing rule. _[§2 Bill to corrections]_
- Approvers: Project Manager, Pointe Grand Kingsland East
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.
