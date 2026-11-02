# Hillpointe AP Invoice Automation

Reads vendor invoices, pay applications and credit memos. It produces the Sage Intacct bill import file, the Entrata handoff
list, an exception log with routes, and the approvers for every bill. A record of everything processed means nothing is
ever entered twice.

**How it works, in one line:** Claude (AI) *reads* each document into fixed fields; plain, predictable code applies
Hillpointe's AP policy, does the arithmetic, checks duplicates and decides. Anything unclear is held for a person, never guessed.

---

## 1. One-time setup (about 5 minutes)

1. Install **uv** (it installs Python for you): `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. In this folder: `uv sync`
3. Put your Anthropic API key in a file named `.env` (copy `.env.example`): `ANTHROPIC_API_KEY=sk-ant-...`
4. Check everything is ready: `uv run ap doctor`. Every line should show ✔.

## 2. Process a batch of invoices

1. Put the PDFs (scans, images and Word files work too) in any folder, e.g. `inbox/2026-11-03/`.
2. Run:
   ```bash
   ./run.sh inbox/2026-11-03
   ```
   (same as `uv run ap run inbox/2026-11-03 --open`)
3. A summary table prints and the report opens in your browser.

Want to preview without recording anything? Add `--what-if`.

## 3. Where the results are

Everything for one run is in `output/<date-time>_<folder name>/`:

| File | What it is | Who uses it |
|---|---|---|
| `intacct_bill_import.csv` | Sage Intacct upload file (one row per bill line, template columns) | AP: upload to Intacct |
| `AP_Bill_Import_<folder>.xlsx` | Same data on Hillpointe's template, plus Entrata_Handoff, Exception_Log and Approvals tabs | AP review |
| `entrata_handoff.csv` | Stabilized-community invoices for Property Accounting to enter in Entrata | Property Accounting |
| `exception_log.csv` | Every document NOT entered: code, plain-English reason, route, confidence. Also informational notes on entered bills (e.g. bill-to corrections) | AP Manager and the routes listed |
| `approvals.csv` | Required approvers for every bill entered | Approvers |
| `run_report.html` / `.md` | Summary, control totals, and a click-to-expand "why" for every document | Anyone |
| `decisions.jsonl` | Full audit trail: what the AI read, every rule result, coding steps | Audit |

## 4. What each exception code means and who gets it

| Code | Meaning | Route |
|---|---|---|
| DUP | Already entered (ERP history or an earlier run) | AP Manager |
| NOPO | Construction bill with no PO/subcontract on file (a likely match is suggested) | Project Manager |
| OVERPO | Would exceed the PO by more than $500 | Project Manager and Supply Chain |
| UNAPPCO | Pay app bills a change order that isn't executed | Project Manager; return to subcontractor |
| LIEN | Required conditional lien waiver missing | Construction Compliance |
| COI | Vendor insurance certificate expired | Construction Compliance |
| NEWVEND | Vendor not in the vendor master | Vendor Master team |
| BANKCHG | Remit address, phone, email or bank differs, or a request to change payment details | Treasury (call the number **on file**) |
| OTHER | Anything else that needs a person, explained in the reason | AP Manager |

**Confidence:** *High* = every field found in the document text, maths ties, rules are clear-cut. *Medium* = a judgment
was needed (e.g. fuzzy vendor name, scanned image, price differs from PO); spot-check it. *Low* = the reading failed a check;
it is always held.

## 5. Changing a rule

All business-rule values live in **`config/policy.yaml`** (commented, one section per policy §). Examples:

| Change | Edit |
|---|---|
| Over-PO limit $500 → $250 | `overpo: tolerance: 250` |
| Net 45 for one vendor | `vendor_overrides: {V1003: {terms: "Net 45"}}` |
| VP Construction above $150k | `approvals: construction: additional: when_gross_work_over: 150000` |
| November is now the open month | edit the Periods tab in `02_Reference_Data`, or `periods: open_period_override: "2026-11"` |
| Price differences should hold, not warn | `price_variance: action: hold` |

Then run `uv run ap policy validate`. Vendors, projects, GL accounts, allocation % and periods are read live from
`02_Reference_Data/Hillpointe_Master_Data.xlsx`, so edit them there. New POs/contracts go in `03_Purchase_Orders_and_Subcontracts/`.
A brand-new kind of rule is about 10 lines: copy `src/ap_automation/rules/_TEMPLATE.py` into `rules/custom.py` and add its name to `rules:` in policy.yaml.

**See the effect of a rule change on a batch you already ran:**
```bash
uv run ap snapshot restore pre-<folder name>   # put the ledger back to before that batch (auto-saved every run)
uv run ap run <folder>                          # re-decide under the new rule
uv run ap diff <old run id> <new run id>        # exactly which documents changed, and why
```

## 6. "Why did it decide that?"

```bash
uv run ap explain APINBOX_0009        # by file name or invoice number; latest run by default
```

## 7. The record of what's been processed (never enter twice)

- `state/ap_ledger.db` is the registry (SQLite) of every document and decision. It is the source of truth for duplicates, together with `06_ERP_History`.
- `state/processed_register.csv` is the same registry as a spreadsheet, refreshed every run.
- `state/extractions/` holds what the AI read from each file, keyed by the file's fingerprint (SHA-256). Reprocessing the same file reuses it: identical results, no AI cost.
- `state/snapshots/` holds ledger snapshots (`submitted` = state after Batch 01 → rerun → Batch 02).

Duplicate logic: vendor ID + normalised invoice number (case, spaces, dashes, `INV` prefixes and leading zeros ignored);
then same vendor + same number ignoring formatting + same amount; then "possible duplicate" flags (same amount + same service
period, or same amount within 7 days) that go to a person. Different vendors can share numbers; the same vendor can bill the
same amount monthly. Revised invoices: only one version is ever entered. Details: `governance/RERUN_EVIDENCE.md`.

## 8. For developers and reviewers

```bash
make test          # 96 tests, no API key needed (hand-labelled fixtures + synthetic hold-out set)
make evidence      # reset ledger → Batch 01 → rerun Batch 01 → Batch 02 → snapshot 'submitted'
make eval          # score Claude's extraction against hand labels (needs API key)
```
Project context, plan, decisions and the AI usage log are in **`governance/`** (start with `governance/README.md`).
The one-page summary is `SUMMARY.md`.
