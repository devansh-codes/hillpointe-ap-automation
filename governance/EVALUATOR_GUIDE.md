# Evaluator Guide: test it end to end in the terminal

About 20 minutes. Steps 1–6 need **no API key**: they replay Claude's saved readings from `state/extractions/`.
Step 7 calls Claude on documents it has never seen (about $0.60 and 1 minute).
Expected results come from `governance/SOURCE_ANALYSIS.md`, which was worked out by hand from the policy.

> Tip: widen the terminal (≥ 160 columns) so the result tables don't wrap.

## 0. Get the code

```bash
git clone https://github.com/devansh-codes/hillpointe-ap-automation.git
cd hillpointe-ap-automation
curl -LsSf https://astral.sh/uv/install.sh | sh     # only if `uv` is not installed
uv sync                                             # installs Python 3.12 and dependencies
```

If `uv` complains about an active virtualenv, run `unset VIRTUAL_ENV` first.

## 1. Pre-flight

```bash
uv run ap doctor
```
**Expect:** ✔ for policy, master data (15 vendors, 5 projects, open period 2026-10), allocation table, template,
12 reference documents, 12/12 cached, and the ledger. Without a key, "Anthropic credentials" shows ✘. That only matters for step 7.

## 2. Automated tests (no key)

```bash
uv run pytest -q
```
**Expect:** `102 passed`. Covers Batch 01, the rerun, Batch 02, 24 unseen synthetic scenarios, 11 rule-change drills, and mocked API behaviour.

## 3. Batch 01: the main deliverable

Start from an empty ledger, then process the batch:
```bash
uv run ap reset-state --yes
uv run ap run 01_Invoice_Batch_01 --offline --open
```
**Expect:** `Entered 6 · Entrata 1 · Held 8 · Not a bill 0 · Already processed 0`, and the HTML report opens.

| File | Expected | Why |
|---|---|---|
| 0001 | HELD **OVERPO** | PO 180,000; billed to date 166,290 → exceeds by 1,392.07 (> $500) |
| 0002 | ENTERED | Corporate SaaS, allocated across entities |
| 0003 | ENTERED | Pay app 3: gross 148,500 + retainage −14,850; posting 10/01 (Sept closed); PM + **VP Construction** |
| 0004 | HELD **NEWVEND** | Vendor not in the master |
| 0005, 0010, 0014 | ENTERED | Construction invoices on a PO |
| 0006 | HELD **BANKCHG** | Payment-details change request → Treasury call-back |
| 0007, 0015 | HELD **DUP** | Already in ERP history (0015's `INV-20417` is history's `20417`) |
| 0008 | ENTRATA_HANDOFF | Stabilized community → Property Accounting |
| 0011 | ENTERED (Adjustment) | Credit memo |
| 0012 | HELD **NOPO** | No PO on the invoice; a likely PO is suggested |
| 0009 | HELD **UNAPPCO** + LIEN | Bills a change order that isn't executed; waiver missing |
| 0013 | HELD **LIEN + COI** | Waiver missing; insurance certificate expired |

Open the run folder printed at the end (`output/<run id>_01_Invoice_Batch_01/`) and check these files:
- `intacct_bill_import.csv`: 11 lines, total **152,562.56**, columns as in the template's Field Guide.
- `AP_Bill_Import_01_Invoice_Batch_01.xlsx`: the same data on Hillpointe's template, plus Entrata/Exceptions/Approvals tabs.
- `entrata_handoff.csv`, `exception_log.csv` (code, reason, route, confidence) and `approvals.csv`.

Ask "why?" for any document:
```bash
uv run ap explain APINBOX_0003      # what the AI read, every rule result, every coding step
uv run ap explain APINBOX_0001
```

## 4. Rerun the same batch: nothing should be entered twice

```bash
uv run ap run 01_Invoice_Batch_01 --offline
```
**Expect:** `Entered 0 · Entrata 0 · Held 8 · Already processed 7`. `intacct_bill_import.csv` in the new run folder has a header only.
Held documents are re-evaluated (they could have been fixed); entered ones are skipped.

## 5. Batch 02: revisions, reprints and resends

```bash
uv run ap run 07_Invoice_Batch_02_Rerun --offline
```
**Expect:** `Entered 2 · Held 3`.
- 0016 is ENTERED.
- 0018 (REVISED HPA-31877) is ENTERED, because its original (0012) was held and never entered; 0012 is marked superseded.
- 0017 (REPRINT), 0019 (exact resend of 0003) and 0020 (PAST DUE) are each **DUP**.

Inspect the registry of processed invoices:
```bash
uv run ap snapshot list
open state/processed_register.csv                     # or: column -s, -t < state/processed_register.csv | less -S
sqlite3 state/ap_ledger.db "select vendor_id, bill_no_norm, count(*) from entered_bills group by 1,2 having count(*)>1"
```
**Expect:** the last query returns **no rows**, so no vendor + invoice number was entered twice. (The table also has a UNIQUE constraint.)

## 6. Live-session drill: change a rule and see exactly what changes

Make the over-PO limit $1,500 instead of $500:
```bash
sed -i.bak 's/  tolerance: 500.00 /  tolerance: 1500.00 /' config/policy.yaml    # or edit config/policy.yaml by hand
uv run ap policy validate
uv run ap snapshot restore pre-01_Invoice_Batch_01    # ledger as it was before Batch 01
uv run ap run 01_Invoice_Batch_01 --offline
uv run ap diff <first Batch 01 run id> <this run id>  # run ids = folder names in output/
```
**Expect:** the diff shows **1 document changed**: APINBOX_0001 goes from HELD OVERPO to ENTERED. The other 14 are unchanged.

Preview without recording anything (handy for "what would happen if…"):
```bash
uv run ap run 01_Invoice_Batch_01 --offline --what-if
```

Undo the rule change and return to the submitted state:
```bash
mv config/policy.yaml.bak config/policy.yaml           # or: git checkout config/policy.yaml
uv run ap snapshot restore submitted
```

More rule-change examples are in `README.md` §5. The full live-session script is in `governance/LIVE_SESSION_RUNBOOK.md`.

## 7. Unseen documents with the real model (needs an API key)

```bash
cp .env.example .env        # then put your key in .env: ANTHROPIC_API_KEY=sk-ant-...
uv run ap doctor            # every line ✔
uv run ap snapshot restore submitted
uv run ap run tests/synthetic/holdout_A --open
uv run ap run tests/synthetic/holdout_B
```
These are 24 documents Claude has never read: new layouts, a scanned PNG, a Word file, an `.xlsx` the system can't
read, a prompt-injection attempt, revisions, credits, PO edge cases and fraud signals. **Expect:**

| Document | Expected |
|---|---|
| A01 inactive vendor name · A05 over PO by $499 · A07b revision (same batch) · A08 recurring same amount, new month · A09 unit-price variance (warning) · A10 credit without original · A11 new layout · A13 Word file | ENTERED |
| A03 repair with no agreement · A12 scanned PNG · A20 previously held, returned corrected | ENTRATA_HANDOFF |
| A02 bill-to isn't a Hillpointe entity · A07a original superseded in the same batch · A14 prompt injection · A16 unsupported `.xlsx` · A18 corporate with no department | HELD OTHER |
| A06 revision after original was entered | HELD DUP |
| A15 arithmetic doesn't tie | HELD OTHER + OVERPO |
| A17 contract not on file | HELD NOPO + LIEN |
| A19 standalone lien waiver | NOT_A_BILL |
| B01 returned pay app, waiver now on file | HELD COI |
| B02 revised pay app | ENTERED |
| B03 copy of an entered invoice | HELD DUP |
| B04 over PO by $501 | HELD OVERPO |

Run `holdout_A` a second time: it finishes in seconds with no API calls, because each file is read once and cached by its SHA-256.
Token use and cost per document are in `state/extractions/*.json` under `meta`.

To try **your own** invoices, put them in any folder and run `./run.sh <folder>`.

Score the AI's reading against the hand labels:
```bash
make eval        # Expect 32/32 (served from cache: no new tokens)
```

## 8. Put it back

```bash
uv run ap snapshot restore submitted
git checkout config/policy.yaml
git status       # new folders appear only under output/ and state/
```

## 9. The same thing in the web app (optional, about 5 minutes)

```bash
uv run ap snapshot restore submitted
uv run ap ui                # opens http://127.0.0.1:8765
```
1. **Home** shows the three submitted runs (Batch 01, its rerun, Batch 02) with a summary each. The rerun is tagged **Rerun**,
   with 7 already processed and no new rows.
2. Open **Invoice Batch 01**. The tiles show 6 entered ($152,562.56), 1 Entrata and 8 held; the **Intacct import** tab shows the
   11 lines and the control total; the download buttons give the same files as `output/`.
3. Click **APINBOX_0013**. The PDF sits on the left; on the right, LIEN + COI with the route and policy section, what the AI
   read, and the step-by-step trail.
4. **Exceptions** shows 10 open holds grouped by route (7 from Batch 01, because 0012 was replaced by its revision, plus 3 DUP
   from Batch 02).
5. **Rules**: set Over-PO tolerance to 1500, choose Invoice Batch 01, then **Preview impact**. **Expect:** "1 document would
   change": APINBOX_0001, HELD OVERPO → ENTERED. Nothing is recorded. Press **Discard changes**.
6. **Run batch → Unseen test set A** (needs the API key) processes the 20 unseen documents live, with a progress bar.
7. Press ⌘K and type `OVERPO` or a vendor name to jump straight to a document.

## Where to look while evaluating

| Question | Look at |
|---|---|
| Why was this held or coded this way? | `uv run ap explain <file>`; `decisions.jsonl` in the run folder |
| Which policy section does a rule implement? | `src/ap_automation/rules/core.py` (each rule cites its §); `config/policy.yaml` |
| What did the AI do, and what is it *not* allowed to do? | `prompts/extract_document.v2.md`; `governance/DECISIONS.md` ADR-0001 and ADR-0011 |
| Expected answer for every document | `governance/SOURCE_ANALYSIS.md` |
| Assumptions and open questions | `governance/ASSUMPTIONS_AND_QUESTIONS.md` |
