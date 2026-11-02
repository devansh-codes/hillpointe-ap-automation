"""Command line: `uv run ap --help`."""
from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from .config import PolicyError, load_config

app = typer.Typer(add_completion=False, help="Hillpointe AP automation: Claude reads invoices, policy code decides.")
snap = typer.Typer(help="Save / restore / list ledger snapshots.")
pol = typer.Typer(help="Policy file helpers.")
app.add_typer(snap, name="snapshot")
app.add_typer(pol, name="policy")
con = Console()


@app.callback()
def _load_dotenv() -> None:
    """Read KEY=value lines from the repo's .env so `uv run ap ...` sees the API key (variables already set win)."""
    from .config import ROOT

    env = ROOT / ".env"
    if os.environ.get("AP_NO_DOTENV") or not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.removeprefix("export ").strip(), v.strip().strip("'\""))


def _cfg(state_dir: Optional[Path] = None, policy: Optional[Path] = None, out_dir: Optional[Path] = None):
    try:
        return load_config(policy_path=policy, state_dir=state_dir, out_dir=out_dir)
    except PolicyError as e:
        con.print(f"[red]policy.yaml has problems:[/red]\n{e}")
        raise typer.Exit(2)


@app.command()
def run(
    inbox: Path = typer.Argument(..., help="Folder of invoices / documents to process"),
    offline: bool = typer.Option(False, help="Use cached extractions only (no API calls)"),
    labels: list[Path] = typer.Option(None, help="Use hand-labelled JSON instead of the model (tests/evaluation)"),
    what_if: bool = typer.Option(False, "--what-if", help="Write outputs but do NOT update the ledger"),
    refs: list[Path] = typer.Option(None, help="Extra folder(s) of POs / subcontracts / agreements"),
    state_dir: Optional[Path] = typer.Option(None, help="Use a different ledger/state folder"),
    policy: Optional[Path] = typer.Option(None, help="Use a different policy.yaml"),
    out_dir: Optional[Path] = typer.Option(None, help="Write run outputs here instead of output/"),
    open_report: bool = typer.Option(False, "--open", help="Open the HTML report when done"),
):
    """Process a folder of documents."""
    from .engine import run as run_engine

    cfg = _cfg(state_dir, policy, out_dir)
    mode = "labels" if labels else ("offline" if offline else "auto")
    if mode == "auto" and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        con.print("[yellow]No ANTHROPIC_API_KEY set: only documents already in the extraction cache can be read; others will be held.[/yellow]")
    with Progress(TextColumn("[bold]Reading[/bold] {task.description}"), BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  console=con, transient=True) as prog:
        task = prog.add_task("documents", total=None)

        def tick(name, done, total):
            prog.update(task, total=total, completed=done, description=name)

        try:
            rr = run_engine(cfg, inbox, mode=mode, what_if=what_if, labels_dirs=labels, extra_refs=refs, progress=tick)
        except FileNotFoundError as e:
            con.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
    _summary(cfg, rr)
    if open_report:
        webbrowser.open((rr.out_dir / "run_report.html").as_uri())


def _summary(cfg, rr) -> None:
    t = Table(title=f"Run {rr.run_id}" + ("  [what-if: ledger NOT updated]" if rr.what_if else ""), show_lines=False)
    for c in ("File", "Decision", "Vendor", "Invoice", "Amount", "Code(s)", "Route / Approvers", "Conf."):
        t.add_column(c, overflow="fold")
    colors = {"ENTERED": "green", "ENTRATA_HANDOFF": "cyan", "HELD": "red", "NOT_A_BILL": "magenta", "ALREADY_PROCESSED": "dim"}
    prec = cfg.policy["exception_precedence"]
    for r in rr.results:
        holds = sorted(r.holds, key=lambda f: prec.index(f.code) if f.code in prec else 99)
        codes = ", ".join(dict.fromkeys(f.code for f in holds))
        route = cfg.route(holds[0].code) if holds else "; ".join(r.approvers)
        t.add_row(r.file_name, f"[{colors.get(r.decision, 'white')}]{r.decision}[/]", f"{r.vendor_id} {r.vendor_name}"[:34], r.bill_no,
                  f"{r.amount:,.2f}" if r.amount is not None else "", codes, route[:60], r.confidence)
    con.print(t)
    n = lambda d: sum(1 for r in rr.results if r.decision == d)  # noqa: E731
    con.print(f"Entered {n('ENTERED')} · Entrata {n('ENTRATA_HANDOFF')} · Held {n('HELD')} · Not a bill {n('NOT_A_BILL')} · "
              f"Already processed {n('ALREADY_PROCESSED')}   →  outputs in [bold]{rr.out_dir}[/bold]")
    if rr.ref_warnings:
        con.print("[yellow]Reference warnings:[/yellow] " + "; ".join(rr.ref_warnings))


@app.command()
def doctor(state_dir: Optional[Path] = typer.Option(None), ping: bool = typer.Option(True, help="Make a 1-token model call")):
    """Pre-flight checks before a live run."""
    ok = True

    def line(passed: bool, msg: str, fix: str = ""):
        nonlocal ok
        ok &= passed
        con.print(("[green]✔[/green] " if passed else "[red]✘[/red] ") + msg + (f"  [dim]→ {fix}[/dim]" if fix and not passed else ""))

    line(sys.version_info >= (3, 12), f"Python {sys.version.split()[0]}", "install Python 3.12+ (uv does this: uv sync)")
    try:
        cfg = load_config(state_dir=state_dir)
        line(True, f"policy.yaml valid (hash {cfg.policy_hash})")
    except PolicyError as e:
        line(False, f"policy.yaml invalid: {e}", "fix the listed keys")
        raise typer.Exit(1)
    from .reference import load_master_data
    try:
        md = load_master_data(cfg.path("master_data"), cfg.path("history"))
        line(True, f"Master data: {len(md.vendors)} vendors, {len(md.projects)} projects, open period(s) {md.open_periods((cfg.policy.get('periods') or {}).get('open_period_override'))}, {len(md.history)} history bills")
        line(abs(sum(md.allocation.values()) - 1) < 1e-9, f"Allocation_Table sums to {sum(md.allocation.values()):.2f}")
    except Exception as e:  # noqa: BLE001
        line(False, f"Master data / history failed to load: {e}")
    from .emit import _template_cols
    try:
        imp, ent = _template_cols(cfg)
        line(len(imp) == 19 and len(ent) == 14, f"Import template: {len(imp)} Intacct columns, {len(ent)} Entrata columns")
    except Exception as e:  # noqa: BLE001
        line(False, f"Template failed to load: {e}")
    refs = [p for d in cfg.reference_dirs for p in d.glob("*") if p.is_file()]
    line(bool(refs), f"{len(refs)} reference documents (POs / subcontracts / agreements)")
    from .extract import CacheStore, intake
    cache = CacheStore(cfg)
    missing = [p.name for p in refs if not cache.get(intake(p).sha256, "reference")]
    line(True, f"Reference docs cached: {len(refs) - len(missing)}/{len(refs)}" + (f" (will be read on first run: {', '.join(missing)})" if missing else ""))
    from .ledger import Ledger
    led = Ledger(cfg.state_dir)
    runs = led.runs()
    view = led.load_view()
    line(True, f"Ledger {led.path}: {len(runs)} runs, {len(view.entered)} entered bills, snapshots: {', '.join(led.list_snapshots()) or 'none'}")
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    line(bool(key), "Anthropic credentials found", "export ANTHROPIC_API_KEY=... (needed for documents not in the cache)")
    if key and ping:
        try:
            import anthropic

            r = anthropic.Anthropic(max_retries=1).messages.create(model=cfg.settings["extraction"]["model"], max_tokens=16,
                                                                    messages=[{"role": "user", "content": "Reply OK"}])
            line(True, f"Model {cfg.settings['extraction']['model']} reachable (stop_reason={r.stop_reason})")
        except Exception as e:  # noqa: BLE001
            line(False, f"Model call failed: {type(e).__name__}: {str(e)[:150]}", "check key / network / model name")
    con.print("[bold green]Ready.[/bold green]" if ok else "[bold red]Not ready — fix the ✘ items.[/bold red]")
    raise typer.Exit(0 if ok else 1)


def _load_run(cfg, run_id: Optional[str]) -> tuple[str, list[dict]]:
    runs = sorted(p for p in cfg.output_dir.iterdir() if (p / "decisions.jsonl").exists()) if cfg.output_dir.exists() else []
    if not runs:
        con.print("[red]No runs found.[/red]")
        raise typer.Exit(1)
    if run_id:
        cand = [p for p in runs if p.name == run_id or p.name.startswith(run_id)]
        if not cand:
            con.print(f"[red]Run {run_id} not found.[/red] Available: {', '.join(p.name for p in runs[-8:])}")
            raise typer.Exit(1)
        p = cand[-1]
    else:
        p = max(runs, key=lambda q: q.stat().st_mtime)
    return p.name, [json.loads(l) for l in (p / "decisions.jsonl").read_text().splitlines() if l.strip()]


@app.command()
def explain(target: str = typer.Argument(..., help="File name (APINBOX_0001), invoice number, or part of either"),
            run_id: Optional[str] = typer.Option(None, "--run", help="Run id (default: latest)"),
            out_dir: Optional[Path] = typer.Option(None, help="Outputs folder (default: output/)")):
    """Explain, step by step, how a document was decided."""
    cfg = _cfg(out_dir=out_dir)
    rid, recs = _load_run(cfg, run_id)
    t = target.lower()
    hits = [r for r in recs if t in r["file_name"].lower() or t in (r["bill_no"] or "").lower()]
    if not hits:
        con.print(f"[red]No document matching '{target}' in run {rid}.[/red]")
        raise typer.Exit(1)
    for r in hits:
        con.rule(f"{r['file_name']} — {r['decision']}  (run {rid})")
        ex = r.get("extraction") or {}
        con.print(f"[bold]1. What the AI read[/bold] ({r['extraction_source']}): {ex.get('doc_kind')} from '{ex.get('vendor_name')}', "
                  f"number {ex.get('document_number')}, dated {ex.get('document_date')}, total {ex.get('total')}, "
                  f"references {ex.get('references')}, markings {ex.get('markings')}")
        con.print("[bold]2. Step-by-step trace[/bold]")
        for i, s in enumerate(r["trace"], 1):
            con.print(f"   {i:>2}. {s}")
        con.print("[bold]3. Findings[/bold]")
        for f in r["findings"] or [{"code": "—", "message": "none", "hold": False, "policy_ref": ""}]:
            con.print(f"   • [{'red' if f['hold'] else 'cyan'}]{f['code']}[/] {'(HOLD) ' if f['hold'] else ''}{f['message']} [dim]{f['policy_ref']}[/dim]")
        if r["bill_lines"]:
            con.print("[bold]4. Intacct lines[/bold]")
            for l in r["bill_lines"]:
                con.print(f"   {l['acct']} {l['loc']}/{l['dept']} {l['project']} {l['task']} {l['cost_type']}  {float(l['amount']):>12,.2f}  {l['memo']}")
        if r["entrata_rows"]:
            con.print("[bold]4. Entrata rows[/bold]")
            for e in r["entrata_rows"]:
                con.print(f"   {e['gl']}  {float(e['amount']):>10,.2f}  {e['description']}")
        if r["approvers"]:
            con.print(f"[bold]5. Approvers:[/bold] {'; '.join(r['approvers'])}")
        con.print(f"[bold]Confidence:[/bold] {r['confidence']} — {r['confidence_reason']}")


@app.command()
def diff(run_a: str, run_b: str, out_dir: Optional[Path] = typer.Option(None, help="Outputs folder (default: output/)")):
    """Show which documents changed decision between two runs (e.g. before/after a rule change)."""
    cfg = _cfg(out_dir=out_dir)
    ra, a = _load_run(cfg, run_a)
    rb, b = _load_run(cfg, run_b)
    A, B = {r["file_name"]: r for r in a}, {r["file_name"]: r for r in b}

    def sig(r):
        codes = sorted({f["code"] for f in r["findings"] if f["hold"]})
        return r["decision"], ",".join(codes), "; ".join(r["approvers"]), sum(float(l["amount"]) for l in r["bill_lines"]) if r["bill_lines"] else None

    t = Table(title=f"{ra}  →  {rb}")
    for c in ("File", "Before", "After", "What changed"):
        t.add_column(c, overflow="fold")
    changed = 0
    for f in sorted(set(A) | set(B)):
        x, y = A.get(f), B.get(f)
        if x is None or y is None:
            t.add_row(f, x and x["decision"] or "—", y and y["decision"] or "—", "only in one run")
            changed += 1
            continue
        sx, sy = sig(x), sig(y)
        if sx != sy:
            changed += 1
            why = []
            if sx[0] != sy[0]:
                why.append(f"decision {sx[0]} → {sy[0]}")
            if sx[1] != sy[1]:
                why.append(f"codes [{sx[1]}] → [{sy[1]}]")
            if sx[2] != sy[2]:
                why.append(f"approvers '{sx[2]}' → '{sy[2]}'")
            new = [fd["message"] for fd in y["findings"] if fd["hold"] and fd["code"] not in sx[1].split(",")]
            gone = [fd["message"] for fd in x["findings"] if fd["hold"] and fd["code"] not in sy[1].split(",")]
            if new:
                why.append("new: " + new[0][:160])
            if gone:
                why.append("cleared: " + gone[0][:160])
            t.add_row(f, f"{sx[0]} {sx[1]}", f"{sy[0]} {sy[1]}", "; ".join(why))
    con.print(t)
    con.print(f"{changed} document(s) changed; {len(set(A) | set(B)) - changed} unchanged.")


@snap.command("save")
def snap_save(name: str, state_dir: Optional[Path] = typer.Option(None)):
    from .ledger import Ledger

    p = Ledger(_cfg(state_dir).state_dir).snapshot(name)
    con.print(f"Saved ledger snapshot '{name}' → {p}")


@snap.command("restore")
def snap_restore(name: str, state_dir: Optional[Path] = typer.Option(None)):
    from .ledger import Ledger

    led = Ledger(_cfg(state_dir).state_dir)
    try:
        led.restore(name)
    except FileNotFoundError as e:
        con.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    con.print(f"Ledger restored to snapshot '{name}' ({len(led.runs())} runs on record).")


@snap.command("list")
def snap_list(state_dir: Optional[Path] = typer.Option(None)):
    from .ledger import Ledger

    for n in Ledger(_cfg(state_dir).state_dir).list_snapshots():
        con.print(n)


@pol.command("validate")
def policy_validate(policy: Optional[Path] = typer.Option(None)):
    """Check policy.yaml for mistakes before running."""
    cfg = _cfg(policy=policy)
    p = cfg.policy
    con.print(f"[green]✔ policy.yaml is valid[/green] (hash {cfg.policy_hash})")
    con.print(f"  OVERPO tolerance ${p['overpo']['tolerance']:,} · VP Construction > ${p['approvals']['construction']['additional']['when_gross_work_over']:,} · "
              f"RPM > ${p['approvals']['stabilized']['additional']['when_invoice_over']:,} · CFO > ${p['approvals']['corporate']['additional']['when_bill_over']:,}")
    con.print(f"  Rules ({len(p['rules'])}): {', '.join(p['rules'])}")
    if p.get("vendor_overrides"):
        con.print(f"  Vendor overrides: {p['vendor_overrides']}")


@app.command("reset-state")
def reset_state(yes: bool = typer.Option(False, "--yes"), state_dir: Optional[Path] = typer.Option(None)):
    """Clear the ledger (start from scratch). Extraction cache is kept."""
    from .ledger import Ledger

    led = Ledger(_cfg(state_dir).state_dir)
    if not yes and not typer.confirm(f"Erase {led.path}? (a snapshot 'before-reset' is saved first)"):
        raise typer.Exit(1)
    led.snapshot("before-reset")
    led.reset()
    con.print("Ledger cleared. Snapshot 'before-reset' saved.")


@app.command("eval-extraction")
def eval_extraction(inbox: list[Path] = typer.Argument(..., help="Folder(s) of documents"),
                    labels: list[Path] = typer.Option(..., help="Folder(s) of hand-labelled JSON"),
                    offline: bool = typer.Option(False)):
    """Compare model extraction to hand-labelled ground truth on the fields the rules depend on."""
    from .extract import LabelExtractor, extract_many, intake, list_inbox, make_extractor

    cfg = _cfg()
    ext = make_extractor(cfg, "offline" if offline else "auto")
    lab = LabelExtractor(labels)
    docs = [intake(p, role="reference" if any(r.resolve() == d.resolve() for r in cfg.reference_dirs) else "bill") for d in inbox for p in list_inbox(d)]
    got = extract_many(ext, docs, cfg.settings["extraction"].get("concurrency", 8))
    fields = ["doc_kind", "vendor_name", "document_number", "document_date", "total", "subtotal", "references",
              "payment_instruction_change_requested", "replaces_document_number", "credit_applies_to_invoice"]
    t = Table(title="Extraction vs labels")
    for c in ("File", "Match", "Mismatches"):
        t.add_column(c, overflow="fold")
    total = ok_all = 0
    for d in docs:
        ex, src = got[d.sha256]
        try:
            truth, _ = lab.extract(d)
        except Exception:  # noqa: BLE001
            continue
        if ex is None:
            t.add_row(d.name, "[red]no extraction[/red]", src)
            continue
        bad = []
        for f in fields:
            a, b = getattr(ex, f), getattr(truth, f)
            if f == "vendor_name":
                from .util import norm_company
                a, b = norm_company(a), norm_company(b)
            if f == "references":  # only references the rules can use (PO / SC / SA / order form)
                from .refdocs import find_references
                a, b = sorted(find_references(*a)), sorted(find_references(*b))
            if a != b:
                bad.append(f"{f}: got {a!r} want {b!r}")
        if truth.pay_application and ex.pay_application:
            for f in ("previous_certificates", "current_payment_due", "total_completed_to_date"):
                if getattr(ex.pay_application, f) != getattr(truth.pay_application, f):
                    bad.append(f"pay_application.{f}")
        if bool(truth.lien_waiver and truth.lien_waiver.present_in_document) != bool(ex.lien_waiver and ex.lien_waiver.present_in_document):
            bad.append("lien_waiver.present_in_document")
        if {m for m in truth.markings} - {m for m in ex.markings}:
            bad.append(f"markings missing {set(truth.markings) - set(ex.markings)}")
        total += 1
        ok_all += not bad
        t.add_row(d.name, "[green]yes[/green]" if not bad else "[red]no[/red]", "; ".join(bad))
    con.print(t)
    con.print(f"{ok_all}/{total} documents match on every decision-relevant field.")


if __name__ == "__main__":
    app()
