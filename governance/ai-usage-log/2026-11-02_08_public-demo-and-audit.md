# 2026-11-02 · 08 · Public demo, independent audit, freeze for interview day

**Tool:** Claude Code (Opus 5.5), with two sub-agents (an independent read-only audit; a traceability-matrix rewrite).
**Human:** Devansh.

## Asked
1. Deploy publicly on GitHub Pages so the link can be shared, with no access to the private GitHub repo.
2. Deep-dive the system against the README and all files so nothing needs changing before interview day.

## Done
- Static read-only build of the web UI (`scripts/build_site.py`, `make site`) published from a separate public repo
  `devansh-codes/hillpointe-ap-demo` (Pages: https://devansh-codes.github.io/hillpointe-ap-demo/). The source repo stays
  private. Local paths scrubbed; no key, `.env` or extraction cache. Write actions show a "read-only demo" message.
- Independent audit (a sub-agent given the code, not my conclusions; offline and on a throw-away ledger only). It found 3
  blockers, 8 should-fixes and 8 nice-to-haves. Fixed: diff blind to non-decision changes, damaged .docx crash,
  false positives in the multi-invoice check, CLI zip/sub-folder input, stale summary/runbook/traceability/ADR order,
  wrong help text, local paths in reports, snapshot hygiene. Regenerated evidence (identical outputs except run ids).
- My mistake, caught and fixed: one redeploy pushed an incomplete site because a failed build was piped through `tail`
  (exit status lost). Rebuilt and redeployed within minutes; the build now reads the runs from the `submitted` snapshot.

## Open for the human
- Whether to keep the public demo public: it shows the exercise documents and their decisions (brief: data is fictional,
  may be used in public AI tools; it doesn't address publishing).
- Commit and push the source repo (needed so a fresh clone matches the docs).
