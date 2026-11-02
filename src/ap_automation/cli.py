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
    from .health import run_checks

    ok = True
    for c in run_checks(state_dir=state_dir, ping=ping):
        ok &= c["ok"]
        con.print(("[green]✔[/green] " if c["ok"] else "[red]✘[/red] ") + c["message"]
                  + (f"  [dim]→ {c['fix']}[/dim]" if c["fix"] and not c["ok"] else ""))
    con.print("[bold green]Ready.[/bold green]" if ok else "[bold red]Not ready — fix the ✘ items.[/bold red]")
    raise typer.Exit(0 if ok else 1)


def _load_run(cfg, run_id: Optional[str]) -> tuple[str, list[dict]]:
    from .runs import RunNotFound, load_run

    try:
        return load_run(cfg, run_id)
    except RunNotFound as e:
        con.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def ui(port: int = typer.Option(8765, help="Port on 127.0.0.1"), open_browser: bool = typer.Option(True, "--open/--no-open")):
    """Open the web app for the AP team (same engine, ledger and policy as the CLI)."""
    from .ui.server import serve

    serve(port, open_browser)


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
    from .runs import compare_runs

    rows = compare_runs(a, b)
    t = Table(title=f"{ra}  →  {rb}")
    for c in ("File", "Before", "After", "What changed"):
        t.add_column(c, overflow="fold")
    for r in rows:
        t.add_row(r["file_name"], r["before"], r["after"], "; ".join(r["why"]))
    changed = len(rows)
    total = len({r["file_name"] for r in a} | {r["file_name"] for r in b})
    con.print(t)
    con.print(f"{changed} document(s) changed; {total - changed} unchanged.")


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
