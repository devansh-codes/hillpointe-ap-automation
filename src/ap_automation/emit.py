"""Write every run output (PLAN §10). Template columns are read from the template, never hand-typed."""
from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from .config import Config
from .engine import RunResult
from .models import DocResult
from .reference import MasterData
from .util import fmt_money, us_date

D0 = Decimal("0")
EXC_COLS = ["File Name", "Decision", "Vendor ID", "Vendor", "Invoice No", "Amount", "Exception Code", "Secondary Codes",
            "Reason", "Recommended Route", "Confidence", "Confidence Reason", "Informational Notes"]
APPR_COLS = ["File Name", "System", "Vendor ID", "Vendor", "Invoice No", "Doc Type", "Amount", "Required Approvers", "Confidence"]


def _template_cols(cfg: Config) -> tuple[list[str], list[str]]:
    wb = openpyxl.load_workbook(cfg.path("template"), read_only=True)
    imp = [c.value for c in next(wb["Import_Template"].iter_rows(min_row=1, max_row=1)) if c.value]
    ent = [c.value for c in next(wb["Entrata_Handoff"].iter_rows(min_row=1, max_row=1)) if c.value]
    return imp, ent


def intacct_rows(results: list[DocResult]) -> list[dict]:
    rows = []
    for r in results:
        if r.decision != "ENTERED" or not r.bill:
            continue
        b = r.bill
        for i, l in enumerate(b.lines, 1):
            rows.append({"BILL_NO": b.bill_no, "DOC_TYPE": b.doc_type, "VENDOR_ID": b.vendor_id, "BILL_DATE": us_date(b.bill_date),
                         "GL_POSTING_DATE": us_date(b.gl_posting_date), "DUE_DATE": us_date(b.due_date), "TERM_NAME": b.term_name,
                         "REFERENCE_NO": b.reference_no, "DESCRIPTION": b.description, "LINE_NO": i, "ACCT_NO": l.acct_no,
                         "LOCATION_ID": l.location_id, "DEPARTMENT_ID": l.department_id, "PROJECT_ID": l.project_id,
                         "TASK_ID": l.task_id, "COST_TYPE_ID": l.cost_type_id, "LINE_MEMO": l.memo, "AMOUNT": f"{l.amount:.2f}",
                         "SUPDOC_ID": b.supdoc_id})
    return rows


def entrata_rows(results: list[DocResult]) -> list[dict]:
    rows = []
    for r in results:
        for e in r.entrata_rows:
            rows.append({"Property": e.property, "Owner Entity": e.owner_entity, "PROJECT_ID": e.project_id, "VENDOR_ID": e.vendor_id,
                         "Vendor Name": e.vendor_name, "Invoice No": e.invoice_no, "Invoice Date": us_date(e.invoice_date),
                         "Post Month": e.post_month, "Due Date": us_date(e.due_date), "Entrata GL": e.entrata_gl,
                         "Description": e.description, "Amount": f"{e.amount:.2f}", "Approver": e.approver, "SUPDOC_ID": e.supdoc_id})
    return rows


def exception_rows(cfg: Config, results: list[DocResult]) -> list[dict]:
    prec = {c: i for i, c in enumerate(cfg.policy["exception_precedence"])}
    rows = []
    for r in results:
        holds = sorted(r.holds, key=lambda f: prec.get(f.code, 99))
        infos = [f for f in r.infos if f.code in ("INFO", "WARN")]
        if r.decision in ("ENTERED", "ENTRATA_HANDOFF") and not infos:
            continue
        if r.decision == "ALREADY_PROCESSED":
            continue
        p = holds[0] if holds else None
        rows.append({
            "File Name": r.file_name, "Decision": r.decision, "Vendor ID": r.vendor_id, "Vendor": r.vendor_name,
            "Invoice No": r.bill_no, "Amount": f"{r.amount:.2f}" if r.amount is not None else "",
            "Exception Code": p.code if p else "INFO", "Secondary Codes": ", ".join(dict.fromkeys(f.code for f in holds[1:])),
            "Reason": " | ".join(f"[{f.code}] {f.message}" for f in holds) if holds else "Entered; see notes.",
            "Recommended Route": " + ".join(dict.fromkeys(cfg.route(f.code) for f in holds)) if holds else "Informational (no action)",
            "Confidence": r.confidence, "Confidence Reason": r.confidence_reason,
            "Informational Notes": " | ".join(f"[{f.code}] {f.message}" for f in infos),
        })
    return rows


def approval_rows(results: list[DocResult]) -> list[dict]:
    rows = []
    for r in results:
        if r.decision not in ("ENTERED", "ENTRATA_HANDOFF"):
            continue
        rows.append({"File Name": r.file_name, "System": "Entrata" if r.decision == "ENTRATA_HANDOFF" else "Sage Intacct",
                     "Vendor ID": r.vendor_id, "Vendor": r.vendor_name, "Invoice No": r.bill_no,
                     "Doc Type": r.bill.doc_type if r.bill else "Invoice", "Amount": f"{r.amount:.2f}",
                     "Required Approvers": "; ".join(r.approvers), "Confidence": r.confidence})
    return rows


def _write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def decision_record(r: DocResult) -> dict:
    return {
        "file_name": r.file_name, "sha256": r.sha256, "decision": r.decision, "category": r.category, "doc_kind": r.doc_kind,
        "vendor_id": r.vendor_id, "vendor_name": r.vendor_name, "bill_no": r.bill_no, "dup_key": f"{r.vendor_id}|{r.bill_no_norm}",
        "amount": str(r.amount) if r.amount is not None else None, "project_id": r.project_id, "reference_no": r.reference_no,
        "confidence": r.confidence, "confidence_reason": r.confidence_reason,
        "findings": [f.as_dict() for f in r.findings], "approvers": r.approvers, "trace": r.trace,
        "bill_lines": [{"acct": l.acct_no, "loc": l.location_id, "dept": l.department_id, "project": l.project_id, "task": l.task_id,
                        "cost_type": l.cost_type_id, "memo": l.memo, "amount": str(l.amount)} for l in (r.bill.lines if r.bill else [])],
        "entrata_rows": [{"gl": e.entrata_gl, "amount": str(e.amount), "description": e.description} for e in r.entrata_rows],
        "extraction_source": r.extraction_source,
        "extraction": r.extraction.model_dump(mode="json") if r.extraction else None,
        "supersedes_sha": r.supersedes, "returns_sha": r.returns,
    }


def write_outputs(cfg: Config, md: MasterData, rr: RunResult) -> None:
    out = rr.out_dir
    out.mkdir(parents=True, exist_ok=True)
    imp_cols, ent_cols = _template_cols(cfg)
    irows, erows = intacct_rows(rr.results), entrata_rows(rr.results)
    xrows, arows = exception_rows(cfg, rr.results), approval_rows(rr.results)

    _write_csv(out / "intacct_bill_import.csv", imp_cols, irows)
    _write_csv(out / "entrata_handoff.csv", ent_cols, erows)
    _write_csv(out / "exception_log.csv", EXC_COLS, xrows)
    _write_csv(out / "approvals.csv", APPR_COLS, arows)
    with open(out / "decisions.jsonl", "w") as f:
        for r in rr.results:
            f.write(json.dumps(decision_record(r), sort_keys=True) + "\n")
    (out / "run_meta.json").write_text(json.dumps({
        "run_id": rr.run_id, "inbox": str(rr.inbox), "inbox_name": rr.inbox.name, "what_if": rr.what_if,
        "extractor": rr.extractor, "policy_hash": cfg.policy_hash, "started_at": datetime.now().isoformat(timespec="seconds"),
        "ref_warnings": rr.ref_warnings,
    }, indent=2))

    # XLSX on the provided template
    wb = openpyxl.load_workbook(cfg.path("template"))
    ws = wb["Import_Template"]
    for i, row in enumerate(irows, start=2):
        for j, c in enumerate(imp_cols, start=1):
            v = row[c]
            ws.cell(i, j, float(v) if c == "AMOUNT" else (int(v) if c == "LINE_NO" else v))
    ws2 = wb["Entrata_Handoff"]
    if ws2.max_row > 1:
        ws2.delete_rows(2, ws2.max_row)
    for i, row in enumerate(erows, start=2):
        for j, c in enumerate(ent_cols, start=1):
            ws2.cell(i, j, float(row[c]) if c == "Amount" else row[c])
    for title, cols, rows in (("Exception_Log", EXC_COLS, xrows), ("Approvals", APPR_COLS, arows)):
        s = wb.create_sheet(title)
        s.append(cols)
        for c in s[1]:
            c.font = Font(bold=True)
        for row in rows:
            s.append([row[c] for c in cols])
    wb.save(out / f"AP_Bill_Import_{rr.inbox.name}.xlsx")

    (out / "run_report.md").write_text(render_markdown(cfg, rr, irows, erows, xrows, arows))
    (out / "run_report.html").write_text(render_html(cfg, rr, irows, erows, xrows, arows))


# ----------------------------------------------------------------------------------------- reports
def _counts(rr: RunResult) -> dict:
    by = {}
    for r in rr.results:
        by.setdefault(r.decision, []).append(r)
    s = lambda rs: sum(((r.amount or D0) for r in rs), D0)  # noqa: E731
    return {k: (len(v), s(v)) for k, v in by.items()} | {"_all": (len(rr.results), s(rr.results))}


def render_markdown(cfg: Config, rr: RunResult, irows, erows, xrows, arows) -> str:
    c = _counts(rr)
    L = [f"# Run report: {rr.run_id}", "",
         f"- Inbox: `{rr.inbox}`",
         f"- Extraction: `{rr.extractor}` · model `{cfg.settings['extraction']['model']}` · prompt `{cfg.settings['extraction']['prompt_version']}`",
         f"- Policy hash: `{cfg.policy_hash}` · Ledger: " + ("**NOT updated (what-if run)**" if rr.what_if else "**recorded** (committed right after these outputs were written)"),
         f"- Processing order (credits first, then date, then name): {', '.join(rr.order)}", "",
         "## Control totals", "", "| Decision | Documents | Amount |", "|---|---|---|"]
    for k in ("ENTERED", "ENTRATA_HANDOFF", "HELD", "NOT_A_BILL", "ALREADY_PROCESSED"):
        n, a = c.get(k, (0, D0))
        L.append(f"| {k} | {n} | {fmt_money(a)} |")
    n, a = c["_all"]
    L += [f"| **Total in** | **{n}** | **{fmt_money(a)}** |", "",
          f"Intacct import: {len(irows)} line(s) across {c.get('ENTERED', (0,))[0]} bill(s), lines total "
          f"{fmt_money(sum((Decimal(r['AMOUNT']) for r in irows), D0))}. Entrata handoff: {len(erows)} row(s).", ""]
    if rr.ref_warnings:
        L += ["## Reference document warnings", ""] + [f"- {w}" for w in rr.ref_warnings] + [""]
    L += ["## Documents", "", "| File | Decision | Vendor | Invoice | Amount | Code | Route | Confidence |", "|---|---|---|---|---|---|---|---|"]
    for r in rr.results:
        p = sorted(r.holds, key=lambda f: cfg.policy["exception_precedence"].index(f.code) if f.code in cfg.policy["exception_precedence"] else 99)
        code = ", ".join(dict.fromkeys(f.code for f in p)) if p else ""
        route = cfg.route(p[0].code) if p else ("; ".join(r.approvers) if r.approvers else "")
        L.append(f"| {r.file_name} | {r.decision} | {r.vendor_id} {r.vendor_name} | {r.bill_no} | {fmt_money(r.amount)} | {code} | {route} | {r.confidence} |")
    L += ["", "## Why (per document)", ""]
    for r in rr.results:
        L.append(f"### {r.file_name}: {r.decision}")
        for f in r.findings:
            L.append(f"- **{f.code}**{' (hold)' if f.hold else ''}: {f.message} _[{f.policy_ref}]_")
        if r.approvers:
            L.append(f"- Approvers: {'; '.join(r.approvers)}")
        L.append(f"- Confidence: **{r.confidence}**: {r.confidence_reason}")
        L.append("")
    return "\n".join(L)


def _table(cols: list[str], rows: list[dict]) -> str:
    h = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    b = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>" for r in rows)
    return f"<div class='tw'><table><thead><tr>{h}</tr></thead><tbody>{b or '<tr><td colspan=99><em>none</em></td></tr>'}</tbody></table></div>"


def render_html(cfg: Config, rr: RunResult, irows, erows, xrows, arows) -> str:
    c = _counts(rr)
    tiles = "".join(f"<div class='tile'><div class='n'>{c.get(k, (0, D0))[0]}</div><div>{lbl}</div><div class='a'>{fmt_money(c.get(k, (0, D0))[1])}</div></div>"
                    for k, lbl in (("ENTERED", "Entered (Intacct)"), ("ENTRATA_HANDOFF", "Entrata handoff"), ("HELD", "Held"),
                                   ("NOT_A_BILL", "Not a bill"), ("ALREADY_PROCESSED", "Already processed")))
    traces = "".join(
        f"<details><summary><b>{html.escape(r.file_name)}</b> · {r.decision} · {html.escape(r.vendor_name)} · {html.escape(r.bill_no)} · "
        f"{fmt_money(r.amount)} · confidence {r.confidence}</summary><ol>"
        + "".join(f"<li>{html.escape(t)}</li>" for t in r.trace)
        + "</ol><ul>" + "".join(f"<li><b>{f.code}</b>{' (hold)' if f.hold else ''}: {html.escape(f.message)} <i>[{html.escape(f.policy_ref)}]</i></li>" for f in r.findings)
        + "</ul></details>" for r in rr.results)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AP Run Report</title><style>
:root{{--bg:#fff;--fg:#1b1f24;--mut:#5b6470;--line:#d9dee4;--tile:#f4f6f8;--acc:#1f5fbf}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14171b;--fg:#e6e9ed;--mut:#9aa4af;--line:#2b3138;--tile:#1c2127;--acc:#7fb0ff}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:16px;max-width:1400px}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:4px}}
.meta{{color:var(--mut)}} .tiles{{display:flex;flex-wrap:wrap;gap:10px}} .tile{{background:var(--tile);border-radius:8px;padding:10px 14px;min-width:140px}}
.tile .n{{font-size:24px;font-weight:600;color:var(--acc)}} .tile .a{{color:var(--mut)}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:12.5px}} th,td{{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}}
th{{background:var(--tile)}} details{{margin:6px 0;padding:6px 8px;background:var(--tile);border-radius:6px}}
</style></head><body>
<h1>AP run report: {html.escape(rr.run_id)}</h1>
<div class="meta">Inbox {html.escape(str(rr.inbox))} · extraction {html.escape(rr.extractor)} · model {html.escape(cfg.settings['extraction']['model'])} ·
policy {cfg.policy_hash} · ledger: {'NOT updated (what-if run)' if rr.what_if else 'recorded'}</div>
<h2>Control totals</h2><div class="tiles">{tiles}</div>
<p class="meta">{c['_all'][0]} documents in, {fmt_money(c['_all'][1])} total.</p>
<h2>Sage Intacct import ({len(irows)} lines)</h2>{_table(list(irows[0].keys()) if irows else ['BILL_NO'], irows)}
<h2>Entrata handoff ({len(erows)} rows)</h2>{_table(list(erows[0].keys()) if erows else ['Property'], erows)}
<h2>Exception log ({len(xrows)} rows)</h2>{_table(EXC_COLS, xrows)}
<h2>Approvals</h2>{_table(APPR_COLS, arows)}
<h2>Decision trace (click a document)</h2>{traces}
</body></html>"""
