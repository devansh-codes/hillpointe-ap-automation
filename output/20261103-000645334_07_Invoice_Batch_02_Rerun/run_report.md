# Run report: 20261103-000645334_07_Invoice_Batch_02_Rerun

- Inbox: `07_Invoice_Batch_02_Rerun`
- Extraction: `offline` · model `claude-opus-5-5` · prompt `v2`
- Policy hash: `8fd4bb314b07` · Ledger: **recorded** (committed right after these outputs were written)
- Processing order (credits first, then date, then name): APINBOX_0019.pdf, APINBOX_0020.pdf, APINBOX_0018.pdf, APINBOX_0017.pdf, APINBOX_0016.pdf

## Control totals

| Decision | Documents | Amount |
|---|---|---|
| ENTERED | 2 | 19,128.80 |
| ENTRATA_HANDOFF | 0 | 0.00 |
| HELD | 3 | 141,958.60 |
| NOT_A_BILL | 0 | 0.00 |
| ALREADY_PROCESSED | 0 | 0.00 |
| **Total in** | **5** | **161,087.40** |

Intacct import: 2 line(s) across 2 bill(s), lines total 19,128.80. Entrata handoff: 0 row(s).

## Documents

| File | Decision | Vendor | Invoice | Amount | Code | Route | Confidence |
|---|---|---|---|---|---|---|---|
| APINBOX_0019.pdf | HELD | V1001 Gulfline Concrete Partners LLC | GCP-0303 | 133,650.00 | DUP | AP Manager | High |
| APINBOX_0020.pdf | HELD | V1003 Coastal Site Services LLC | CSS-88502 | 1,240.00 | DUP | AP Manager | High |
| APINBOX_0018.pdf | ENTERED | V1009 Harbor Point Aggregates LLC | HPA-31877 | 16,948.80 |  | Project Manager, Pointe Grand Kingsland East | High |
| APINBOX_0017.pdf | HELD | V1002 Ridgeway Equipment Rental Inc | RER-77310 | 7,068.60 | DUP | AP Manager | High |
| APINBOX_0016.pdf | ENTERED | V1003 Coastal Site Services LLC | CSS-88611 | 2,180.00 |  | Project Manager, Pointe Grand Kingsland East | High |

## Why (per document)

### APINBOX_0019.pdf: HELD
- **DUP** (hold): Already entered: V1001 invoice GCP-0303 in run 20261103-000643675_01_Invoice_Batch_01 (APINBOX_0003.pdf) (same amount). _[§10]_
- Confidence: **High**: Rule outcome is deterministic: DUP — Already entered: V1001 invoice GCP-0303 in run 20261103-000643675_01_Invoice_Batch_01 (APINBOX_0003.pdf) (same amount).

### APINBOX_0020.pdf: HELD
- **DUP** (hold): Already entered: V1003 invoice CSS-88502 in run 20261103-000643675_01_Invoice_Batch_01 (APINBOX_0005.pdf) (same amount). Document is stamped PAST DUE. _[§10]_
- Confidence: **High**: Rule outcome is deterministic: DUP — Already entered: V1003 invoice CSS-88502 in run 20261103-000643675_01_Invoice_Batch_01 (APINBOX_0005.pdf) (same amount).

### APINBOX_0018.pdf: ENTERED
- **INFO**: Revised invoice replaces HPA-31877 (APINBOX_0012.pdf), which was held (NOPO) and never entered. The revision is evaluated on its own; the original is marked superseded. _[§10/§11]_
- Approvers: Project Manager, Pointe Grand Kingsland East
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.

### APINBOX_0017.pdf: HELD
- **DUP** (hold): Already entered: V1002 invoice RER-77310 in run 20261103-000643675_01_Invoice_Batch_01 (APINBOX_0010.pdf) (same amount). Document is stamped REPRINT. _[§10]_
- Confidence: **High**: Rule outcome is deterministic: DUP — Already entered: V1002 invoice RER-77310 in run 20261103-000643675_01_Invoice_Batch_01 (APINBOX_0010.pdf) (same amount).

### APINBOX_0016.pdf: ENTERED
- Approvers: Project Manager, Pointe Grand Kingsland East
- Confidence: **High**: All fields found in the document text, arithmetic ties, every rule passed.
