# Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language / env | Python 3.12, **uv** (lockfile `uv.lock`) | Best PDF/Excel ecosystem; `uv sync` = one-command reproducible install |
| AI extraction | **Claude Opus 5.5** (`claude-opus-5-5`) via `anthropic` SDK 2.x `messages.create`, effort `medium`; fallback `claude-sonnet-5-5`. Bills: validated JSON; references: API-enforced JSON schema (ADR-0011) | Native PDF input (text + page image → sees watermarks); 32/32 accuracy measured |
| Schema | Pydantic v2 (`models.ExtractedDocument`) | Strict fixed format; anything that doesn't fit is rejected |
| PDF text layer | pdfplumber | Grounding cross-check of AI output against raw text |
| Word input | python-docx | .docx → ordered text (paragraphs + tables) for the model |
| Excel | openpyxl | Master data, history, template read live; output written onto the provided template |
| Fuzzy matching | rapidfuzz | Vendor names, bill-to entity, invoice line → PO line |
| Ledger | SQLite (stdlib) | ACID commit, UNIQUE constraint as a duplicate control, snapshots via backup API |
| Config | YAML (`config/policy.yaml`, `config/settings.yaml`) | Every rule value editable in one place; `ap policy validate` |
| CLI | Typer + Rich | `ap run / doctor / explain / diff / snapshot / policy validate / eval-extraction` |
| Web UI | FastAPI + uvicorn; one static HTML/CSS/JS page (no build step, no CDN) | `ap ui`: thin layer over the engine for the AP team (ADR-0012); works offline |
| Tests | pytest; reportlab (synthetic PDFs); poppler `pdftoppm` (synthetic PNG) | 149 tests, no API key needed |
| Money | `decimal.Decimal`, ROUND_HALF_UP to cents | No float error in accounting |

## Deliberate non-choices

- **No temperature setting.** Claude Opus 5.5 (and API version 2026-10-21 on every model) rejects `temperature`, and the
  SDK no longer exposes it. Repeatability comes from the hash-keyed extraction cache (a file is read once, then reused byte for byte),
  schema enforcement, and the grounding and arithmetic checks. See CHANGELOG / PLAN §11.
- **No agent loop / no LLM decisions.** The model never chooses GL, entity, approver or hold (ADR-0001).
- **No OCR library.** Images and scans go to the model directly; with no text layer, grounding can't run, so confidence is capped at Medium.

## Token efficiency (measured 2026-11-02)

| Practice | Where | Effect |
|---|---|---|
| **Read each file once.** SHA-256-keyed extraction cache (key = hash + prompt version + role + model) | `extract.CachedExtractor` | Reruns, resends with identical bytes (0019 = 0003) and evidence regeneration cost **0 tokens** |
| **Prompt caching** on the byte-stable system prompt + role schema (Opus 5.5 caches from 512 tokens; reads cost 0.05× input) | `ClaudeExtractor._system` | Package run $1.00 vs $1.43 uncached (−30%); unseen synthetic runs −40% |
| **Cache warm-up:** first request runs alone, the rest in parallel, so parallel calls read the cache instead of each writing it | `extract.extract_many` | Avoids 8 simultaneous cache writes at 1.25× |
| **Role-specific schemas** (bill vs reference) | `extract.api_schema(role)` | Smaller prompts and outputs per call |
| **Effort chosen by measurement**, not maxed | `settings.yaml` + `make eval` | medium = low = 32/32; low is −26% cost and −30% latency, kept as an option |
| **Repair only on failure**, carrying only the validation errors | `ClaudeExtractor.extract_with_meta` | 0 repairs needed across 55 real extractions |
| **Concise output instruction** (no explanations, empty fields stay empty) + `observations` kept to one sentence | prompt v2 | ≈ 800 output tokens per document |
| **No API call** for unsupported files or already-entered identical files | `extract_many`, engine idempotency | |
| **Token and cost metering** per document (input, output, cache read/write, seconds, repaired) | `state/extractions/*.json` → `meta` | Auditable spend; basis for every number above |
| Not used: Batch API (−50%) | — | Latency matters on screen; a good fit for nightly back-office volume (PLAN "what next") |

Average per document: ≈ 6.9k input tokens (mostly the PDF page image and text; ≈ 3.5k of it cached prompt) and ≈ 0.8k output tokens, ≈ $0.03.
