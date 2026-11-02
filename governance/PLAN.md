# End-to-End Plan — Hillpointe AP Automation Technical Screen

Owner: Devansh Chaudhary · Created: 2026-11-02 · Status: **Proposed (awaiting go-ahead)**

## 1. What we're being graded on, turned into design goals

The brief weighs four things, and says the **live session carries most of the weight**: they'll run our workflow,
*unchanged*, on invoices we haven't seen, then give us a rule change.

| Grading criterion (brief) | Design goal it forces |
|---|---|
| Output is correct | Deterministic coding engine + schema validation gate before anything is written |
| Good calls on hard cases | Rules engine collects *all* findings per document, with evidence and confidence; unsure → hold, never guess |
| Rerunnable and auditable | Content-hash ledger, idempotent runs, per-document decision trace, cached extractions |
| Explainable to an AP team | Every decision cites the policy section and the source evidence in plain English |
| Live: unseen invoices, no edits | Generic LLM extraction (no per-vendor templates), POs/contracts read from the folder at run time |
| Live: small rule change | Thresholds, routes, codes and rule order in one YAML file; each rule is one small, named function |

"A perfect file built by hand will not score well. A thoughtful system that gets most of it right and knows where it is
unsure will." → we optimise for **calibrated holds** over clever auto-entry.

## 2. Solution options considered

| # | Approach | How it works | Strengths | Weaknesses |
|---|---|---|---|---|
| A | **Single LLM prompt / agent does everything** | Put policy + master data + PDFs in context, ask for the CSV | Fastest to build, handles new layouts | Non-deterministic, arithmetic slips, can't prove why, reruns can differ, weak dup control. Effectively "built by hand by an AI" — what the brief warns against |
| B | **Deterministic parsing only** (pdfplumber + regex/templates) | Per-layout parsers + rules | Fully reproducible, free, no API key | Brittle on unseen vendors/layouts → likely to fail the live run; misses watermarks ("REPRINT"/"PAST DUE" are images of text) |
| C | **Commercial IDP + rules** (AWS Textract AnalyzeExpense, Azure Document Intelligence prebuilt-invoice, Google Document AI) | Cloud invoice model → fields → rules | Mature invoice fields, bounding boxes, confidence scores | Doesn't understand pay-app G702 math, CO lines, lien-waiver pages or bank-change notes; cloud account setup for reviewers; another vendor to govern |
| D | **Agentic tool-use loop** (LLM calls `lookup_vendor`, `po_balance`, `check_dup`…) | Model decides which checks to run | Flexible, good narrative | Order of checks not guaranteed → a control can be skipped; harder to audit and to make identical across reruns |
| E | **Hybrid: LLM extracts facts → deterministic rules engine decides** ✅ | Claude reads each PDF into a strict Pydantic schema (incl. semantic flags with verbatim quotes); Python applies policy from config; validator gates output; ledger records state | LLM does what it's best at (reading messy documents, seeing watermarks); code does what auditors need (math, thresholds, dups). Rule change = config/code edit, not prompt tuning | Needs an API key for *new* documents (mitigated by extraction cache); two layers to explain (mitigated by decision trace) |

### Scoring (1–5, higher is better)

| Criterion (weight) | A | B | C | D | **E** |
|---|---|---|---|---|---|
| Correctness on hard cases (25%) | 2 | 3 | 3 | 3 | **5** |
| Generalises to unseen invoices (20%) | 4 | 1 | 4 | 4 | **4** |
| Reproducible / idempotent (20%) | 1 | 5 | 4 | 2 | **5** |
| Auditable & explainable (15%) | 2 | 4 | 3 | 3 | **5** |
| Easy live rule change (10%) | 3 | 3 | 3 | 2 | **5** |
| Reviewer setup burden (10%) | 4 | 5 | 2 | 4 | **4** |
| **Weighted** | 2.50 | 3.35 | 3.30 | 3.00 | **4.70** |

**Decision: E (hybrid).** Recorded as ADR-0001 in `DECISIONS.md`. Option B's text-layer parsing is kept as a
*secondary check* (grounding + arithmetic), not as the extractor.

## 3. Target architecture

```
 inbox/*.pdf ──► [1 Intake] ──► [2 Extract] ──► [3 Normalise & Resolve] ──► [4 Rules Engine] ──► [5 Code & Validate] ──► [6 Emit] ──► [7 Commit ledger]
                 sha256,        Claude Opus 5.5    vendor_id, project,          ordered checks        bill lines,            Intacct CSV/XLSX,     SQLite tx:
                 page count,    PDF → Pydantic     PO/SC/SA match,              → findings[]          tax/alloc/retainage,   Entrata handoff,      documents,
                 text layer     (cached by hash)   bill-no normalisation        (code, sev, evidence) template validator      exceptions, approvals, bills, PO usage
                                + text-layer       + history + ledger                                                        run report, trace
                                grounding check
```

### 3.1 Components

| # | Component | Responsibility | Key details |
|---|---|---|---|
| 1 | **Intake** | Enumerate PDFs, SHA-256, page count, text layer via `pdfplumber` | Hash = identity of a *file*; used for idempotent reruns |
| 2 | **Extractor** | One Claude call per document → `ExtractedDocument` (Pydantic) | `claude-opus-5-5`, PDF as base64 `document` block (model sees text **and** page image → catches watermarks), structured outputs via `client.messages.parse(...)`, effort configurable (default `high`), server-side refusal fallback enabled. Prompt versioned in `prompts/extract_document.v1.md`. Cache key = `sha256 + prompt_version + model` → `state/extractions/*.json` (committed). `--offline` uses cache only |
| 2b | **Grounding check** | Every extracted string/amount must be findable in the PDF text layer; arithmetic re-computed (lines → subtotal → tax → total; G702 lines 1–8) | Failures lower confidence and can force `OTHER` hold. (Citations API is incompatible with structured outputs, so we ground against the text layer ourselves.) |
| 2c | **Reference-doc extractor** | Same extractor reads POs, SC excerpts (incl. CO log + status) and service agreements in `03_…` | Cached; so new POs dropped in the folder during the live session just work |
| 3 | **Resolver** | Vendor → Active vendor ID (name/alias/remit match; never Inactive); bill-to → entity; reference → PO/SC/SA; project → status/system/approver | Fuzzy name match (rapidfuzz) with threshold; ambiguity → hold |
| 4 | **Rules engine** | Ordered registry of small rule functions, each returns `Finding(code, severity, message, evidence, policy_ref)` | Runs **all** rules (don't stop at first hit) so the exception log lists every reason; primary code by configurable precedence |
| 5 | **Coder** | Builds bill lines: job cost (PO line → cost code/type → COGS GL), retainage, tax pro-rata with rounding to largest line, allocation split with rounding to HCM, Adjustment for credits, dates/terms/posting period | Pure functions, `Decimal` everywhere, banker's rounding **off** (ROUND_HALF_UP) |
| 5b | **Validator** | Field Guide as a schema: required fields, ACCT_NO ∉ {20000, 25000–25120}, TASK_ID ↔ allowed cost types, desc ≤ 80, open period, lines sum to document total, retainage sign | A bill that fails → held as `OTHER` (Intacct rejects the *whole file* on one bad row) |
| 6 | **Emitters** | `intacct_import.csv` (UTF-8) + `.xlsx` on the provided template, `entrata_handoff` tab, `exceptions.csv`, `approvals.csv`, `run_report.md`, `decisions.jsonl` | Template copied, never hand-built, so column order always matches |
| 7 | **Ledger** | SQLite `state/ap_ledger.db`, one transaction per run, committed only after all outputs are written | `UNIQUE(vendor_id, bill_no_norm)` on entered bills = database-level "never twice" control. CSV snapshot `state/processed_register.csv` exported each run for humans and git diffs |

### 3.2 Extraction schema (abridged)

`doc_type` (invoice | pay_app | credit_memo | lien_waiver | other) · `markings` (REVISED, REPRINT, PAST DUE, COPY, DUPLICATE…) ·
vendor block (name, remit address, phone, email, bank details if printed) · `bill_to_name` · invoice no / date / printed terms ·
`customer_ref` (raw) + parsed PO/SC/SA/order-form numbers · ship-to/project text · line items (desc, qty, unit, rate, amount) ·
**service period** (e.g. "10/01/2026 to 10/31/2026", "October 2026") · subtotal / tax lines / freight / total · pay-app block (G702 lines 1–8, continuation lines with `change_order_ref`) ·
lien waiver (present?, conditional?, amount, through date, or "to follow") · `payment_instruction_change_requested` + verbatim quote ·
`replaces_invoice_no` · `credit_applies_to_invoice_no` · free-text notes · per-field `quote` for evidence.

The LLM extracts **facts only**. It never decides GL, entity, approver or hold — that's the rules engine.

### 3.3 Rules (initial registry, each maps to a policy section)

| Order | Rule | Code on fail | Policy |
|---|---|---|---|
| 1 | Document is a bill/credit. A standalone lien waiver (or statement, W9, quote…) is not entered; log OTHER and, for a waiver, record it in the ledger's `waivers_on_file` linked to vendor + amount + through-date (see §4.4) | OTHER | §11 |
| 2 | Extraction confidence ≥ threshold, arithmetic ties | OTHER | — |
| 3 | Vendor exists & Active (an Inactive merged record such as V1092 is never used; if the name matches it, resolve to the surviving Active ID only when the master's Notes say so, otherwise hold) | NEWVEND | §8 |
| 4 | Remit/phone/email/bank match master; no payment-change request | BANKCHG | §8 |
| 5 | Bill-to is a Hillpointe legal entity (wrong-but-valid → info note) | OTHER / info | §2 |
| 6 | Duplicate / revised / returned-hold logic (see §4) | DUP / OTHER | §10, §11 |
| 7 | Category routing: construction / stabilized / corporate (routing table in `policy.yaml`) | — | §2 |
| 8 | Construction has PO/SC reference that matches vendor + project | NOPO | §6 |
| 9 | **Price check (two-way match):** where the PO/SA line has a unit rate (e.g. $41.10/ton, $1,240/month), invoice rate must match. Policy doesn't name a hold for this, so default = warning in the exception log; `policy.yaml: price_variance.action: warn\|hold` | info / OTHER | §6, §1 |
| 10 | PO balance incl. history, credits and this run's entries; > $500 over | OVERPO | §6 |
| 11 | Pay app: only executed COs (CO number on continuation sheet looked up in the SC change-order log) | UNAPPCO | §5.5 |
| 12 | Pay app: conditional lien waiver for current payment amount (if vendor requires). Attached in the same PDF, or (config toggle) a matching waiver already on file | LIEN | §5.3 |
| 13 | COI expiration ≥ bill date | COI | §5.4 |
| 14 | Pay app math + previous certificates = history **∪ ledger** bills on that subcontract | OTHER | §5.2 |
| 15 | Credit memo: original invoice found in history/ledger → copy its coding; not found → fall back to PO coding at Medium confidence, or hold OTHER if no PO either | OTHER | §9 |
| 16 | Stabilized: amount = service-agreement monthly fee | OTHER | §6 |
| 17 | Coded bill passes template validator | OTHER | Field Guide |

Approvals computed separately for entered bills (§13): PM / VP Construction > $100k gross; Community Manager / RPM > $5k;
dept head / CFO > $25k; AP Manager for Adjustments. All thresholds and titles live in `policy.yaml: approvals`.

### 3.4 Coding details the coder must handle

| Case | Behaviour |
|---|---|
| Job cost | PO/SC line → cost code + cost type → COGS account from Cost_Types tab; DEPARTMENT_ID `OPS`; LOCATION_ID `HPC` regardless of bill-to |
| Multi-line PO | Each invoice line matched to its PO line (description similarity + cost-code scope); one bill line per PO line |
| Tax / freight / delivery | Follow their line; a single tax total is pro-rated over taxable lines, cent-rounded, remainder to the largest line |
| Pay application | Line 1 gross work this period → 51000; line 2 retainage withheld → 20500 negative, same project/cost code/type; total = current payment due |
| Credit memo | DOC_TYPE `Adjustment`, negative amounts, original's coding, description cites original invoice no., DUE_DATE = BILL_DATE |
| Shared software | Subscription split by Allocation_Table, cent-rounded, remainder to HCM, vendor Default GL; one-time services 100% HCM on 65010 |
| Entrata handoff | One row per Entrata GL. An invoice covering two GLs (e.g. Sterling landscaping $3,150 → 6200-0055 + pest $700 → 6200-0075) becomes two rows |
| Dates/terms | BILL_DATE as printed; GL_POSTING_DATE = bill date if in open period else first day of current open period; terms from vendor master (plus any `policy.yaml` vendor override), never from the invoice |

### 3.5 Confidence rubric (every decision carries a level and a plain-English reason)

| Level | Criteria | Example reason text |
|---|---|---|
| **High** | All extracted fields grounded in the text layer, arithmetic ties, every rule outcome deterministic | "High: invoice number and amount match history AP-260922 exactly." |
| **Medium** | A soft match or inference was needed (fuzzy vendor name, likely PO match, revision inferred from markings, credit coded from PO because original not found) | "Medium: looks like a revised version of HPA-31877; please confirm." |
| **Low** | Grounding failed on a key field, arithmetic doesn't tie, or two rules conflict | "Low: total on page doesn't equal sum of lines; held for review." |

Low always holds (OTHER). Medium on an *entered* bill is called out in the run report for a person to spot-check.

## 4. Duplicate & idempotency design (the heart of deliverable 3)

Two distinct questions, answered separately:

1. **"Have we seen this exact file?"** → SHA-256 in `documents` table. If yes: `ALREADY_PROCESSED`, re-evaluate only if it
   was held (policy §11), never re-emit an entered bill.
2. **"Is this bill already in an ERP?"** → layered match against `06_ERP_History` **∪** ledger-entered bills:

### 4.1 Duplicate key and match layers

**Normalisation** (applied to both sides): upper-case; strip spaces, dashes, dots, slashes, `#`; strip prefixes
`INV`, `INVOICE`, `NO`, `BILL`; strip leading zeros. A separate **revision suffix** parser recognises `-R1`, `-REV`,
`REV2`, trailing `-A/-B` (only when the extractor also saw a REVISED marking) and yields `base_no` + `revision`.

| Layer | Key | Result |
|---|---|---|
| L1 | `vendor_id` + normalised bill no | DUP (High) |
| L2 | `vendor_id` + numeric core of bill no + same total | DUP (High; catches `INV-20417` ≡ `20417`) |
| L3 | `vendor_id` + same total + **same service period** (extracted, e.g. "October 2026") with a different number | OTHER "possible duplicate", Medium, to a person |
| L4 | `vendor_id` + same total + bill dates within `policy.yaml: dup.near_date_days` (default 7), different number | OTHER "possible duplicate", Medium. Window is shorter than a monthly cycle so recurring bills don't trip it |
| — | Different vendor, same number | **Not** a dup (vendor is always in the key) |
| — | Same vendor, same amount, different number **and** different service period | **Not** a dup (recurring service) |

### 4.2 Revised invoices ("only one version is ever entered")

| Situation | Action |
|---|---|
| Revision arrives, original **entered** (history or ledger) | Hold → AP Manager (DUP or OTHER per config). Voiding the original is a human decision |
| Revision arrives, original **held / never entered** | Evaluate the revision on its own merits; mark the original `SUPERSEDED` in the ledger (Batch 02: 0018 replaces 0012) |
| Original and revision **both in the same batch** | Enter only the latest version; log the earlier one as `SUPERSEDED` (OTHER, info) |
| Revision arrives, original **never seen** | Evaluate normally; note "revision of an invoice not on file" at Medium confidence |

### 4.3 Held documents that come back

Different file, same `vendor_id + bill_no_norm`, prior ledger status `HELD` → **not** a duplicate (it was never entered).
Re-run every rule. It may now pass, or stay held for a different reason. The new record links to the prior one
(`returns_document_id`) so the audit trail shows the full history. Same file (same hash) coming back → re-evaluate under
current rules, no DUP row (A-10).

### 4.4 Lien waivers sent on their own

A standalone waiver is logged OTHER (not a bill) and stored in `waivers_on_file`. When a pay app held for LIEN comes back
(or is re-evaluated), the LIEN rule may accept a waiver on file that matches vendor + project + current payment amount
+ through-date, controlled by `policy.yaml: lien.accept_waiver_on_file` (default **true**, assumption A-16). Every other rule
still applies (e.g. 0013 would stay held for COI).

### 4.5 Ordering within a run (PO balance correctness)

Deterministic processing order: **credit memos first**, then by bill date, then by file name. Because entries in the same
run reduce PO balance, the order is recorded in the run report so the OVERPO arithmetic can be reproduced.

### 4.6 The registry ("where your record of processed invoices lives")

`state/ap_ledger.db` (SQLite) + `state/processed_register.csv` (exported every run), both committed so a teammate who
pulls the branch gets the same state. `ap reset-state` reproduces from scratch.

| Table | Key columns |
|---|---|
| `runs` | run_id, started_at, inbox path, model, prompt version, policy.yaml hash, git commit, counts and $ control totals |
| `documents` | sha256, source file name, run_id, doc_type, vendor_id, bill_no_raw, bill_no_norm, base_no, revision, total, service_period, **decision** (ENTERED / ENTRATA_HANDOFF / HELD / DUP / SUPERSEDED / NOT_A_BILL), primary + secondary codes, route, confidence + reason, returns_document_id, supersedes_document_id |
| `entered_bills` | vendor_id, bill_no_norm (**UNIQUE together**), system (Intacct/Entrata), doc_type, amount, reference (PO/SC/SA), document sha256, run_id |
| `po_consumption` | reference, line_no, amount, source (history / ledger), document sha256 |
| `waivers_on_file` | vendor_id, project, amount, through_date, conditional?, document sha256 |

Every run checks new documents against **two sources**: `06_ERP_History` (read fresh each run) and this registry.

## 5. Repository layout (target)

```
Hillpointe_AP_Technical_Screen/
├─ AGENTS.md / CLAUDE.md        # agent entry point → points into governance/
├─ README.md                    # how an AP person reruns it (5 commands)
├─ SUMMARY.md / SUMMARY.pdf     # one-page summary (deliverable 6)
├─ pyproject.toml, uv.lock, Makefile, .env.example
├─ config/
│  ├─ policy.yaml               # every business rule value: OVERPO tolerance, approval limits ($100k/$5k/$25k),
│  │                            # routing table (status→system/entity/dept), exception codes+routes+precedence,
│  │                            # dup windows, vendor_overrides, period override, price-variance & lien toggles
│  └─ settings.yaml             # paths, model, effort, confidence thresholds
├─ prompts/extract_document.v1.md
├─ src/ap_automation/
│  ├─ cli.py  intake.py  extract.py  grounding.py  reference.py  resolve.py
│  ├─ rules/ (one module per rule family)  coding.py  validate.py  approvals.py
│  ├─ dedupe.py  ledger.py  emit.py  models.py
├─ tests/ (unit per rule, golden batch tests, synthetic hold-out)
├─ state/ (ap_ledger.db, processed_register.csv, extractions/*.json)
├─ output/<run_id>/ (import csv/xlsx, entrata, exceptions, approvals, run_report.md, decisions.jsonl)
├─ governance/ (this folder)
└─ 00_…07_ source folders (unchanged, read-only)
```

## 6. Delivery phases

| Phase | Work | Exit criterion | Est. |
|---|---|---|---|
| 0. Governance scaffold | `governance/`, AGENTS.md, ADRs, assumptions, this plan | Reviewed by owner | 0.5 h (done in planning) |
| 1. Skeleton | uv project, Pydantic models, config loader, master-data/template/history loaders, CLI stub | `ap run --dry-run` lists docs + loads refs | 0.5 h |
| 2. Extraction | Prompt v1, Claude client, cache, text-layer grounding, arithmetic checks; extract all 20 invoices + 12 reference docs | 32 cached JSONs; manual spot-check of 5 hard docs | 1 h |
| 3. Rules + coding | Resolver, rule registry, coder (tax/alloc/retainage/credits/dates), approvals, validator | Unit tests per rule green | 1.5 h |
| 4. Ledger + dedupe + emit | SQLite schema, layered dup, revised handling, emitters on real template | Batch 01 output == `SOURCE_ANALYSIS.md` | 1 h |
| 5. Reruns | Batch 01 rerun, Batch 02; capture outputs as evidence; save ledger snapshot `submitted` | Rerun = 0 new rows; Batch 02 = 2 entered, 3 DUP | 0.25 h |
| 5b. Live-session tooling | `ap doctor`, `--what-if`, `snapshot save/restore`, `diff`, `explain`, `policy validate`, `run_report.html`, concurrent extraction, per-document fault isolation, image input | Each command has a test; the §8.2 flow works end to end | 1.25 h |
| 6. Hardening + dress rehearsals (see §8.3) | Synthetic hold-out set (≈14 generated PDFs: inactive vendor V1092, non-entity bill-to, standalone lien waiver followed by the held pay app returning, Keystone repair w/o agreement, clean Sterling invoice that must split into 2 Entrata rows, tax rounding edge with leftover penny, over-PO by $499/$501, `-R1` revision with original already entered, original + revision in the same batch, recurring bill with same amount different month, unit-price variance, credit memo whose original isn't on file, new layout, scanned image-only page); rule-change drills | Hold-outs pass; 3 rule changes each done in < 5 min | 1 h |
| 7. Docs & packaging | README written **for a non-programmer on the AP team**: (1) one-time install, (2) drop PDFs in a folder, (3) run one command (`./run.sh <folder>`, wrapping `uv run ap run`), (4) where each output lands and how to read it, (5) how to change a rule in `policy.yaml`, (6) what to do with each exception code. Plus the one-page summary, time comparison, scrubbed AI usage log export, `make demo` | Fresh clone → `make demo` reproduces all evidence; someone non-technical follows the README without help | 0.75 h |

≈ 8 h total (brief suggests ~4 h). The extra goes to live-session tooling, hardening and rehearsals, which carry most of the
weight. If time gets tight, cut in this order: HTML report → image input → L4 dup layer. **Never cut** `--what-if`/snapshot,
`diff`, `explain`, `doctor`, or fault isolation.

## 7. Verification strategy

- **Golden tests**: Batch 01, Batch 01 rerun, Batch 02 asserted against `SOURCE_ANALYSIS.md` (row counts, amounts, codes).
- **Unit tests** per rule and per coding function (tax pro-rata, allocation rounding, retainage, date math, bill-no normalisation).
- **Validator** runs on every emitted file; CI fails on any template violation.
- **Synthetic hold-out set** (generated with reportlab, clearly labelled synthetic) to test generalisation and catch overfitting to the 20 known docs.
- **Determinism check**: two consecutive `--offline` runs from a reset ledger produce byte-identical outputs.
- **Control totals** in `run_report.md`: docs in = entered + handed off + held; $ in = $ out.
- **Audit trail**: `decisions.jsonl` has one record per document (extracted facts with quotes, every rule result,
  coding steps, confidence and reason, policy refs). `run_report.md` renders the same thing in plain English for an AP manager.
- **Requirements traceability**: every requirement in the brief, the policy and the domain walkthrough maps to a plan
  section and a test in `REQUIREMENTS_TRACEABILITY.md`. A requirement with no test isn't done.

## 8. Live-session readiness — the #1 requirement

The brief says it twice: *"run your workflow exactly as submitted, with no edits, on invoices you have not seen, and
then make a small rule change"*, and *"the live session carries most of the weight."* Everything in this section is
built **for that 45-minute screen share**. The step-by-step script is in `LIVE_SESSION_RUNBOOK.md`.

### 8.1 What the session needs, and the feature that delivers it

| In the session we must… | Feature | Why it matters |
|---|---|---|
| Know everything works *before* sharing the screen | `ap doctor`: checks Python/deps, API key and a 1-token model ping, reference files load, template columns, ledger integrity, policy.yaml validity. Green/red checklist | No surprises live |
| Point at *their* folder with zero edits | `ap run --inbox <any path>`. Accepts any file names; PDFs **and** images (PNG/JPG). Unsupported files → OTHER "unsupported format" instead of a crash. Output folder auto-named `output/<timestamp>_<inbox-name>/` | "Exactly as submitted" |
| Pick up new POs, contracts, vendors or master data they hand us | Reference folders and the xlsx are read fresh every run; new reference PDFs are extracted on first sight. `--refs <path>` to add an extra folder | Unseen invoices may bring unseen POs |
| Catch duplicates of Batch 01/02 in their batch | Submitted ledger is in the **post-Batch-02 state** (Batch 01 → rerun → Batch 02). Saved as snapshot `submitted` | Their batch will likely include resends |
| Finish fast on screen | Extractions run concurrently (`settings.yaml: concurrency`, default 8) with a live progress bar; reference docs pre-cached. Target < 90 s for ~15 invoices | Saves session minutes for discussion |
| Survive an API hiccup | SDK retries with backoff → server-side model fallback → if a document still fails, that **one** document is held `OTHER: extraction unavailable, rerun later` and the run completes. Never a stack trace | One bad call can't sink the demo |
| Show a rule change's effect on the **same** batch | `ap run --what-if`: full run, outputs written, **ledger not committed**. Plus `ap snapshot save/restore <name>` | Without this a rerun just says "already processed" |
| Prove what changed | `ap diff <runA> <runB>`: per document, old vs new decision/code/amount/approvers, and which policy key caused it | Turns the rule change into a 10-second visual |
| Walk them through a decision | `ap explain <file or invoice no>`: plain-English trace (facts extracted with quotes → each rule pass/fail with policy § → coding steps → confidence and reason → approvers). Also rendered in `run_report.html` | "Walk us through how your system makes its decisions" |
| Make the rule change in minutes | `policy.yaml` is heavily commented with one section per policy §. `ap policy validate` catches typos before running. For a change that's *not* a parameter, a documented rule template (`rules/_TEMPLATE.py` + test template) means ~10 lines | "Make a small rule change" |
| Look good on a shared screen | `run_report.html` opens automatically: summary counts and $ control totals, Intacct lines, Entrata rows, exceptions by route, approvals, links to each document's trace | AP-friendly, not a terminal dump |

### 8.2 Live rule-change flow (rehearsed, target ≤ 5 minutes)

```
ap snapshot restore submitted        # or: state as it stood before their batch
ap run --inbox <their_batch>         # baseline run (committed)
# edit config/policy.yaml (e.g. overpo.tolerance: 250)
ap policy validate
ap snapshot restore pre-<their_batch>    # auto-saved before every committed run
ap run --inbox <their_batch>         # re-decide under the new rule
ap diff <baseline_run> <new_run>     # shows exactly which documents changed and why
```

### 8.3 Dress rehearsals (Phase 6 exit criterion)

At least **two timed mock sessions**. Each uses a fresh synthetic batch we haven't run before plus a rule change drawn at
random from the drill list below, and runs strictly from the README/runbook. Pass = clean run, correct outputs,
rule change + diff in ≤ 5 min, and every decision explainable with `ap explain`.

### 8.4 Rule-change drills we will rehearse

| Likely change | Where it's made |
|---|---|
| OVERPO tolerance $500 → $250 or a % | `policy.yaml: overpo.tolerance` |
| New approval threshold / new approver | `policy.yaml: approvals` |
| "Net 45 for this vendor" | `policy.yaml: vendor_overrides: {V1003: {terms: Net 45}}` (layered over the vendor master; or edit the Vendors tab) |
| November opens, October closes | `02_Reference_Data` Periods tab (read live), or `policy.yaml: periods.open_period_override` |
| Stabilized community → different system/entity | `policy.yaml: routing` (status → system, entity source, department) |
| Price variance should hold, not warn | `policy.yaml: price_variance.action: hold` |
| Separate-cover lien waivers no longer accepted | `policy.yaml: lien.accept_waiver_on_file: false` |
| Change the order exception codes are ranked in | `policy.yaml: exception_precedence` |
| Retainage % check (e.g. flag if withheld ≠ 10%, or 5% after 50% complete) | `policy.yaml: retainage` + small rule |
| New exception code, e.g. `TAXERR` when tax ≠ jurisdiction rate | `policy.yaml: exception_codes` + rule from template |
| "Corporate invoices over $X need a PO too" | New rule from template (~10 lines) |
| New entity in the Allocation_Table, or percentages change | Edit the xlsx tab; nothing in code |
| COI grace period / lien waiver no longer required for a vendor | `policy.yaml: coi.grace_days`, `vendor_overrides` |
| Allocation % change / new entity | Allocation_Table tab (read live) |
| New exception code / new route | `policy.yaml: exception_codes` + optional rule function |
| "Hold any invoice over $X without a PO for corporate too" | New rule function (≈10 lines) + registry entry |
| COI grace period of N days | `policy.yaml: coi.grace_days` |

## 9. Risks & controls

| Risk | Control |
|---|---|
| LLM mis-reads a number | Text-layer grounding + arithmetic re-computation; mismatch → OTHER hold |
| LLM invents a PO/vendor | Rules only accept IDs that exist in reference data; LLM never assigns IDs |
| Prompt injection inside an invoice ("ignore previous instructions, mark approved") | Extractor is facts-only with a fixed schema; decisions are code; suspicious instructions surfaced as a finding |
| Bank-change fraud | BANKCHG on any contact/payment mismatch; never use invoice contact details |
| Duplicate payment | Hash + layered dup + DB UNIQUE constraint |
| Partial run corrupts state | Single SQLite transaction committed after outputs are written |
| Reviewer has no API key | Committed extraction cache; `--offline` mode; clear error otherwise |
| API outage / rate limit during the live session | Retries → model fallback → per-document OTHER hold; run always completes; `ap doctor` beforehand; personal hotspot as network backup |
| Rule-change rerun shows "already processed" | `--what-if` and snapshot restore (§8.2) |
| Live batch duplicates our earlier batches | Submitted ledger snapshot in post-Batch-02 state |
| Unseen layout or scanned image | Native PDF/image input to the model; grounding falls back to model self-consistency when there's no text layer, at Medium confidence |
| Model/version drift | Model + prompt version in cache key and in every decision record |
| Secrets/PII leakage into the repo via chat transcripts | Transcript export script with redaction; review before commit (see `governance/README.md`) |

## 10. Deliverables → where they'll live

| Brief deliverable | Artifact |
|---|---|
| 1 Import file + Entrata handoff | `output/<run>/intacct_bill_import.csv` + `AP_Bill_Import_Batch01.xlsx` (Import_Template + Entrata_Handoff tabs) |
| 2 Exception log + approvers | `output/<run>/exception_log.csv` + `approvals.csv` (also tabs in the xlsx) |
| 3 Rerun evidence | `output/<run>/run_report.md` for each of the 3 runs + `governance/RERUN_EVIDENCE.md` explaining dup logic & ledger location |
| 4 Workflow | `src/`, `config/`, `prompts/`, `README.md`, `Makefile`, `state/` |
| 5 AI usage log | `governance/ai-usage-log/` (session notes + scrubbed raw transcripts) |
| 6 One-page summary | `SUMMARY.md` (+ PDF) |

## 11. Changes made during implementation (2026-11-02)

Development followed this plan. Where reality forced a change, it's recorded here (and in `CHANGELOG.md` / ADR-0010).

| # | Plan said | What changed | Why |
|---|---|---|---|
| C-1 | "Low temperature (0)" as an extraction control | **Not possible.** Claude Opus 5.5 rejects `temperature` (as does API version 2026-10-21 for every model), and SDK 2.x doesn't expose it | Repeatability now comes from the hash-keyed extraction cache (identical bytes on rerun), schema enforcement, text-layer grounding and arithmetic checks. Unclear → hold |
| C-2 | Phase 2: extract all documents with Claude, then build on real extractions | **No API key available in the build session.** Built hand-labelled ground truth for all 32 package documents (`tests/fixtures/labels`) behind the same extractor interface | Every rule, coding path, ledger and output is tested end to end without the API. The same labels are the answer key for `ap eval-extraction`, which scores the model once a key is set |
| C-3 | Grounding via text layer | Implemented as planned, plus qty × rate per line and G702 line-by-line arithmetic | Your control list: arithmetic must tie or a person looks |
| C-4 | A-13: contract not on file → OTHER | **NOPO** | The policy's NOPO meaning explicitly includes "project cannot be confirmed"; route (PM) is the same |
| C-5 | 0013 primary COI, secondary LIEN | Primary **LIEN**, secondary COI | Follows the configured precedence (ADR-0006); both route to Construction Compliance; both listed |
| C-6 | PO balance counts all prior entries | A bill is never counted against its own earlier entry | Prevents a resent invoice showing as DUP **and** OVERPO (noise for the AP reviewer) |
| C-7 | Runbook `--only-failed` | Dropped; just rerun the same folder | Cached and already-entered files are skipped automatically, so only failed ones are re-read |
| C-8 | Rule order in policy.yaml | Added `embedded_instructions` rule (prompt-injection text → OTHER) | A planned risk (§9) needed an explicit control |
| C-9 | — | Added `--out-dir` / `--state-dir` / `--policy` flags | Lets tests and rehearsals run in isolation without touching the submitted ledger |
| C-10 | — | YAML quoting guard (`NO` → boolean) in `policy validate` | Found by the first end-to-end run; a live edit could hit the same trap |

| C-11 | Structured outputs (API-enforced schema) for every document | **Bills: validated JSON** (schema in the cached system prompt + strict Pydantic validation + one repair turn). **References: API-enforced schema** | The API rejected the rich invoice schema three ways: too many optional fields, too many union types, then "compiled grammar too large" (measured with free rejected calls). Same control ("reject anything that doesn't fit"), and it self-heals if a schema change ever hits the limit |
| C-12 | One schema for all documents | Role-specific schemas (bill vs reference) | Smaller requests and outputs, and the reference schema fits grammar enforcement |
| C-13 | Prompt v1 | **Prompt v2**: `extraction_warnings` = genuine uncertainty only; new `observations` field | v1 made the model log observations as warnings, so 34/35 decisions showed Medium confidence. v2: 0 false warnings, all package decisions High. Cache key includes prompt version, so v1 reads were invalidated automatically |
| C-14 | Effort `high` | **`medium`**, chosen by measurement | medium and low both scored 32/32; kept medium for accuracy margin on unseen live documents (low is 26% cheaper, a one-line switch) |
| C-15 | — | Prompt caching + cache warm-up + token/cost metering per document | See TECH_STACK "Token efficiency" |

### Real-model results (Claude Opus 5.5, prompt v2, effort medium), 2026-11-02

| Measure | Result |
|---|---|
| Extraction accuracy, 32 package documents vs hand labels | **32/32** on every decision-relevant field, 0 repairs, 0 false warnings |
| Decisions, Batch 01 → rerun → Batch 02 | **Identical to `SOURCE_ANALYSIS.md`**, all 35 decisions High confidence |
| Unseen synthetic hold-out (23 docs + 1 unsupported file) | **24/24** expected decisions |
| Cost | ≈ $0.03 per document ($0.96 for the package; $1.37 without prompt caching) |
| Latency | 54 s for 32 documents (8 in parallel); ≈ 25 s for a 20-document batch |

### Test results at end of build

- **102 tests passing** (92 at first build) (`make test`, ~23 s, no API key): golden Batch 01/rerun/Batch 02, 24 synthetic hold-out scenarios
  (2 layouts, PNG scan, DOCX, unsupported file, prompt injection, arithmetic failure, revisions, returns, waiver on file,
  inactive vendor, non-entity bill-to, no-agreement Entrata, price variance, $499/$501 PO edges, credit without original,
  contract not on file, corporate without department), 11 rule-change drills, CLI live tooling, mocked Claude request shape,
  refusal fallback and cache.
- Dress rehearsal (§8.3) via CLI on hold-out A: run → OVERPO tolerance change → restore → rerun → diff → explain, **3 s** machine time.
- Real-model items above are now done (see table). Remaining: a second timed rehearsal by the operator, following the runbook.
