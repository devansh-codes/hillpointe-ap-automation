# Live Session Runbook (45 minutes)

What the brief says: *"share your screen, run your workflow on a new batch of invoices, make a rule change we give you,
and walk us through how your system makes its decisions."* The workflow is run **exactly as submitted, with no edits**.

> Commands verified against the built CLI on 2026-11-02 (see `tests/test_live_tooling.py`).

## T-30 min — before the call

```bash
cd Hillpointe_AP_Technical_Screen
git status                      # clean working tree = "exactly as submitted"
uv run ap doctor                # everything must be green (API key, model ping, refs, template, ledger, policy)
uv run ap snapshot restore submitted   # ledger in post-Batch-02 state
```
- Close other apps, increase terminal font, open `config/policy.yaml` in the editor, and have a phone hotspot ready.
- Open the last `output/*/run_report.html` in a browser tab as a fallback demo.

## 0–5 min — framing (talk, no commands)
"AI reads the documents; plain code applies your policy; anything uncertain is held and routed, never guessed. Every
decision has a trace, and a ledger guarantees nothing is entered twice."

## 5–15 min — run their batch
```bash
uv run ap run <path-to-their-folder> --open
```
- Narrate the progress bar, then the summary: entered / Entrata / held, with $ control totals.
- `run_report.html` opens. Walk through the Intacct lines → Entrata rows → exceptions by route → approvals.
- If any document shows `OTHER: extraction unavailable`, say why (fault isolation) and rerun just that file at the end.

## 15–30 min — make their rule change
1. Repeat the rule back in one sentence and name the policy key ("that's `overpo.tolerance` in policy.yaml").
2. Edit `config/policy.yaml` → `uv run ap policy validate`. Run ids are printed at the end of each run (or `ls output/`).
3. Re-decide the same batch:
   ```bash
   uv run ap snapshot restore pre-<their-folder>
   uv run ap run <path-to-their-folder> --open
   uv run ap diff <baseline-run> <new-run>
   ```
4. Point at the diff: which documents changed and which didn't, and why.
5. If it isn't a parameter: copy `src/ap_automation/rules/_TEMPLATE.py`, write the ~10-line rule, add it to the registry
   in `policy.yaml`, then validate, rerun and diff as above.

## 30–40 min — "how does it decide?"
```bash
uv run ap explain <hardest file in their batch>
```
Pick one hold and one entry. Show: extracted facts with quotes → each rule pass/fail with policy § → coding math (tax
split, retainage, allocation) → confidence and reason → approvers. Then show the duplicate logic with
`uv run ap explain` on any DUP.

## 40–45 min — what still needs a person and what's next
Use the one-page summary: what needs a person (all holds, Medium-confidence entries, approvals), time saved, next steps.

## If something goes wrong

| Symptom | Do this |
|---|---|
| `doctor` red on API | Check `ANTHROPIC_API_KEY` / `ant auth status`; switch to the hotspot; worst case run `--offline` on a cached batch to show the flow, and explain |
| Rate limited mid-run | Run completes with affected docs held (OTHER, "could not read"). Run the same command again: entered files are skipped, cached reads reused, only the failed ones are re-read |
| Wrong-looking decision | Don't edit code live. `ap explain` it, say whether it's an extraction or rule issue, and what you'd change |
| Accidentally committed a bad run | `ap snapshot restore pre-<folder>` |
