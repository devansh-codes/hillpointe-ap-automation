# Session 05 — Real-model integration & token efficiency

- **Date:** 2026-11-02 · **Tool:** Claude Code, Claude Opus 5.5

## Prompts (verbatim, secrets removed)

> Can I get the api keys from the simple claude account or I would need to create a developer account and pay for it?

> [screenshot of the Console "Create API key" dialog] should i keep the scope as devansh or org?

> [API key pasted into chat; **redacted here**. The key was written only to `.env` (gitignored). Action: revoke it in the Console and create a new one, because it appears in the local chat transcript.]

> Make sure to implement best AI practices for the most effective and effecient token usage in our solution

## What happened

1. `ap doctor` → all green with the key.
2. First real extraction: **every document failed cleanly** (held, no crash: fault isolation worked). The cause was API structured-output limits. The AI used free rejected calls to probe the limits, measuring instead of guessing: optional-field cap → union-type cap → grammar-size cap. Bills moved to validated JSON; references kept the API-enforced schema; added self-healing fallback (ADR-0011).
3. 32/32 extraction accuracy, but 34/35 decisions showed Medium confidence. Diagnosis: the model wrote observations into `extraction_warnings`. Fixed with prompt v2; the version bump invalidated the cache automatically. Result: 0 false warnings, all package decisions High.
4. Effort measured: medium and low both 32/32; kept medium (unseen-document margin), documented low as −26% cost.
5. Unseen synthetic hold-out with the real model: 24/24.
6. Token practices implemented and measured (TECH_STACK "Token efficiency"): ≈ $0.03/doc, prompt caching −30% to −45%.

## Human decisions
- Scope of API key: Default workspace (least privilege; org scope needs an extra header).
- Keep effort medium for the live session.
