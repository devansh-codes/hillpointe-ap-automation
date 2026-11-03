"""Run orchestration: intake → extract → resolve → rules → code → validate → emit → commit."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from .approvals import approvers
from .coding import CodingError, code_construction, code_corporate, code_entrata
from .config import Config
from .context import BILL_KINDS, Ctx, build_ctx
from .dedupe import norm_bill_no, split_revision
from .extract import IntakeDoc, extract_many, intake, list_inbox, make_extractor
from .ledger import EnteredBill, Ledger, LedgerView
from .models import DocResult, ExtractedDocument, Finding
from .reference import MasterData, load_master_data
from .refdocs import RefIndex
from .rules import RULES
from .util import money, project_path
from .validate import validate_bill, validate_entrata

D0 = Decimal("0")


@dataclass
class RunResult:
    run_id: str
    inbox: Path
    out_dir: Path
    results: list[DocResult]
    committed: bool
    what_if: bool
    extractor: str
    ref_warnings: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)


def _git_commit(root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def build_ref_index(cfg: Config, extractor, extra_dirs: list[Path] | None = None) -> RefIndex:
    idx = RefIndex()
    docs = [intake(p, role="reference") for d in cfg.reference_dirs + (extra_dirs or []) if d.exists() for p in list_inbox(d)]
    got = extract_many(extractor, docs, cfg.settings["extraction"].get("concurrency", 8))
    for d in docs:
        ex, src = got[d.sha256]
        if ex is None:
            idx.warnings.append(f"{d.name}: reference document could not be read ({src})")
            continue
        idx.add(ex, d.name)
    return idx


def _order_key(item: tuple[IntakeDoc, Optional[ExtractedDocument]]):
    """Credits first, then bill date, then file name (A-19) so PO balances are deterministic."""
    d, ex = item
    credit = 0 if ex is not None and (ex.doc_kind == "credit_memo" or (ex.total is not None and ex.total < 0)) else 1
    return (credit, (ex.document_date or "9999") if ex else "9999", d.name)


def _primary(findings: list[Finding], precedence: list[str]) -> Optional[Finding]:
    holds = [f for f in findings if f.hold]
    if not holds:
        return None
    rank = {c: i for i, c in enumerate(precedence)}
    return sorted(holds, key=lambda f: rank.get(f.code, len(rank)))[0]


def _confidence(res: DocResult) -> tuple[str, str]:
    lows = [f for f in res.findings if f.confidence == "Low"]
    meds = [f for f in res.findings if f.confidence == "Medium"]
    if lows:
        return "Low", lows[0].message
    if meds:
        return "Medium", meds[0].message
    if res.decision == "HELD":
        p = res.holds[0] if res.holds else None
        return "High", f"Rule outcome is deterministic: {p.code} — {p.message[:120]}" if p else "High"
    if res.decision == "ALREADY_PROCESSED":
        return "High", "Same file (same SHA-256 and file name) was already processed in an earlier run."
    return "High", "All fields found in the document text, arithmetic ties, every rule passed."


def process_document(cfg: Config, md: MasterData, refs: RefIndex, view: LedgerView, doc: IntakeDoc,
                     ex: Optional[ExtractedDocument], src: str, run_id: str, batch_revisions: dict) -> DocResult:
    res = DocResult(file_name=doc.name, sha256=doc.sha256, supdoc_id=doc.supdoc_id, extraction=ex, extraction_source=src)
    pol = cfg.policy

    if ex is None:
        res.findings.append(Finding("OTHER", f"Could not read the document ({src.removeprefix('unavailable: ')}). "
                                             "Nothing entered; rerun when extraction is available or key it manually.",
                                    "Extraction control", confidence="Low"))
        res.decision = "HELD"
        res.trace.append(f"Extraction failed: {src}")
        _finish(cfg, res, view, run_id, None)
        return res

    res.doc_kind = ex.doc_kind
    res.bill_no = (ex.document_number or "").strip()
    res.trace.append(f"Read by {src}: {ex.doc_kind}, number {ex.document_number}, dated {ex.document_date}, total {ex.total}")

    # Idempotency: the exact same file (hash + name) already entered in a prior run → no-op.
    prior = view.prior_doc(doc.sha256, doc.name)
    if prior and prior.decision in ("ENTERED", "ENTRATA_HANDOFF"):
        res.decision = "ALREADY_PROCESSED"
        res.vendor_id, res.bill_no_norm = prior.vendor_id, prior.bill_no_norm
        res.amount = money(ex.total if ex.total is not None else (ex.pay_application.current_payment_due if ex.pay_application else 0))
        res.trace.append(f"Same file already processed in run {prior.run_id} ({prior.decision}); nothing new is entered.")
        res.confidence, res.confidence_reason = _confidence(res)
        return res
    if prior:
        res.trace.append(f"Same file was processed before in run {prior.run_id} and held ({prior.primary_code}); re-evaluating against current rules (§11).")

    ctx = build_ctx(cfg, md, refs, view, doc, ex, res, run_id, batch_revisions)
    res.vendor_id = ctx.vendor.vendor_id if ctx.vendor else ""
    res.vendor_name = ctx.vendor.name if ctx.vendor else (ex.vendor_name or "")
    res.amount = ctx.total
    res.bill_no_norm = ctx.bill_no_norm
    res.bill_date = ctx.bill_date
    res.service_period = ctx.service_period

    for name in pol["rules"]:
        try:
            found = RULES[name](ctx)
        except Exception as e:  # noqa: BLE001 - a crashing rule must hold the document, never pass it
            found = [Finding("OTHER", f"Rule '{name}' could not be evaluated ({type(e).__name__}: {e}).", "Control", confidence="Low")]
        for f in found:
            f.code = f.code if f.code in pol["exception_codes"] or not f.hold else "OTHER"
        res.findings += found
        status = "pass" if not any(f.hold for f in found) else "HOLD " + ", ".join(f.code for f in found if f.hold)
        notes = [f.code for f in found if not f.hold]
        res.trace.append(f"Rule {name}: {status}" + (f" (notes: {', '.join(notes)})" if notes else ""))
    res.project_id = ctx.project.project_id if ctx.project else ""
    res.reference_no = ctx.ref.number if ctx.ref else (ctx.ref_raw or "")

    if ex.doc_kind == "lien_waiver" and ctx.vendor:
        view.new_waivers.append({"vendor_id": ctx.vendor.vendor_id, "project_text": ex.lien_waiver.project if ex.lien_waiver else "",
                                 "amount": str(money(ex.lien_waiver.amount if ex.lien_waiver else 0)),
                                 "through_date": ex.lien_waiver.through_date if ex.lien_waiver else "",
                                 "waiver_type": (ex.lien_waiver.waiver_type if ex.lien_waiver else "") or "conditional",
                                 "sha256": doc.sha256, "file_name": doc.name, "run_id": run_id})

    if not ctx.is_bill:
        res.decision = "NOT_A_BILL"
    elif res.holds:
        res.decision = "HELD"
    else:
        _code(ctx, res)
    _finish(cfg, res, view, run_id, ctx)
    return res


def _code(ctx: Ctx, res: DocResult) -> None:
    md, pol = ctx.md, ctx.policy
    opens = md.open_periods((pol.get("periods") or {}).get("open_period_override"))
    try:
        if ctx.category == "stabilized":
            appr = approvers(ctx, None)
            rows = code_entrata(ctx, "; ".join(appr))
            errs = validate_entrata(rows, md, ctx.total)
            if errs:
                raise CodingError("Entrata handoff failed validation: " + "; ".join(errs))
            res.entrata_rows, res.approvers, res.decision = rows, appr, "ENTRATA_HANDOFF"
        elif ctx.category in ("construction", "corporate"):
            bill = code_construction(ctx) if ctx.category == "construction" else code_corporate(ctx)
            errs = validate_bill(bill, md, pol, ctx.total, opens)
            if errs:
                raise CodingError("Import validation failed: " + "; ".join(errs))
            gross = bill.lines[0].amount if ctx.is_pay_app else None
            res.bill, res.approvers, res.decision = bill, approvers(ctx, bill, gross), "ENTERED"
        else:
            raise CodingError("Category unknown.")
        res.trace.append("Coded and validated → " + res.decision)
    except CodingError as e:
        res.findings.append(Finding("OTHER", str(e), "Coding / Field Guide", confidence="Medium"))
        res.decision = "HELD"
        res.trace.append(f"Coding stopped: {e}")


def _finish(cfg: Config, res: DocResult, view: LedgerView, run_id: str, ctx: Optional[Ctx]) -> None:
    res.confidence, res.confidence_reason = _confidence(res)
    p = _primary(res.findings, cfg.policy["exception_precedence"])
    ex = res.extraction
    base_no, rev = split_revision(res.bill_no)
    view.new_docs.append({
        "run_id": run_id, "sha256": res.sha256, "file_name": res.file_name, "doc_kind": res.doc_kind, "vendor_id": res.vendor_id,
        "vendor_name": res.vendor_name, "bill_no_raw": res.bill_no, "bill_no_norm": res.bill_no_norm,
        "base_no": norm_bill_no(base_no, cfg.policy["dup"]["strip_prefixes"]) if res.bill_no else "", "revision": rev,
        "total": str(res.amount) if res.amount is not None else None,
        "bill_date": res.bill_date.isoformat() if res.bill_date else None, "service_period": res.service_period,
        "decision": res.decision, "primary_code": p.code if p else "",
        "secondary_codes": ",".join(f.code for f in res.holds if p and f is not p),
        "route": cfg.route(p.code) if p else "", "confidence": res.confidence, "confidence_reason": res.confidence_reason,
        "returns_sha": res.returns, "supersedes_sha": res.supersedes,
    })
    if res.supersedes:
        view.supersede_shas.add(res.supersedes)
    if res.decision in ("ENTERED", "ENTRATA_HANDOFF") and ctx is not None:
        system = "Entrata" if res.decision == "ENTRATA_HANDOFF" else "Sage Intacct"
        e = EnteredBill(res.vendor_id, res.bill_no_norm, res.bill_no, system, res.bill.doc_type if res.bill else "Invoice",
                        ctx.total, ctx.bill_date, ctx.service_period, res.reference_no, res.sha256, res.file_name, run_id)
        view.new_entered.append(e)
        if ctx.ref and ctx.ref.kind == "po":
            view.new_po.append({"reference": ctx.ref.number, "line_no": "", "amount": str(ctx.total), "vendor_id": res.vendor_id,
                                "bill_no_norm": res.bill_no_norm, "sha256": res.sha256, "run_id": run_id})


def run(cfg: Config, inbox: Path, mode: str = "auto", what_if: bool = False, labels_dirs: list[Path] | None = None,
        extra_refs: list[Path] | None = None, progress: Callable[[str, int, int], None] | None = None) -> RunResult:
    from .emit import write_outputs  # local: emit imports engine types

    inbox = inbox.resolve()
    if not inbox.is_dir():
        raise FileNotFoundError(f"Inbox folder not found: {inbox}")
    md = load_master_data(cfg.path("master_data"), cfg.path("history"))
    ledger = Ledger(cfg.state_dir)
    view = ledger.load_view()
    extractor = make_extractor(cfg, mode, labels_dirs)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S") + f"{now.microsecond // 1000:03d}"
    run_id = f"{stamp}_{inbox.name}" + ("_whatif" if what_if else "")

    refs = build_ref_index(cfg, extractor, extra_refs)
    docs = [intake(p) for p in list_inbox(inbox)]
    done = [0]

    def tick(d):
        done[0] += 1
        if progress:
            progress(d.name, done[0], len(docs))

    got = extract_many(extractor, docs, cfg.settings["extraction"].get("concurrency", 8), tick)
    items = sorted(((d, got[d.sha256][0]) for d in docs), key=_order_key)

    # Same-batch revisions: original + revised version in one batch → only the latest is evaluated
    from .context import resolve_vendor
    batch_revisions: dict[tuple[str, str], str] = {}
    for d, ex in items:
        if ex is None or ex.doc_kind not in BILL_KINDS:
            continue
        marks = " ".join(ex.markings).upper()
        orig = ex.replaces_document_number or (split_revision(ex.document_number)[0] if split_revision(ex.document_number)[1] else "")
        if orig or "REVISED" in marks:
            v, _, _ = resolve_vendor(md, ex)
            if v:
                batch_revisions[(v.vendor_id, norm_bill_no(orig or ex.document_number, cfg.policy["dup"]["strip_prefixes"]))] = d.name

    results = []
    for d, ex in items:
        try:
            results.append(process_document(cfg, md, refs, view, d, ex, got[d.sha256][1], run_id, batch_revisions))
        except Exception as e:  # noqa: BLE001 - fault isolation: one document can never sink the run
            res = DocResult(file_name=d.name, sha256=d.sha256, supdoc_id=d.supdoc_id, extraction=ex, extraction_source=got[d.sha256][1])
            res.findings.append(Finding("OTHER", f"Unexpected error while processing ({type(e).__name__}: {e}); held for review.",
                                        "Control", confidence="Low"))
            res.trace.append(f"Processing error: {type(e).__name__}: {e}")
            _finish(cfg, res, view, run_id, None)
            results.append(res)
    out_dir = cfg.output_dir / run_id
    rr = RunResult(run_id, inbox, out_dir, results, committed=False, what_if=what_if, extractor=mode,
                   ref_warnings=refs.warnings, order=[d.name for d, _ in items])
    write_outputs(cfg, md, rr)

    if not what_if:
        # Keep the state from *before this folder was first processed*: a rerun of the same folder must not
        # overwrite it, or "restore pre-<folder>" would bring back a ledger that already contains the batch.
        seen = any(Path(r["inbox"]).name == inbox.name for r in ledger.runs())
        if not seen or f"pre-{inbox.name}" not in ledger.list_snapshots():
            ledger.snapshot(f"pre-{inbox.name}")
        ent = [r for r in results if r.decision == "ENTERED"]
        ntr = [r for r in results if r.decision == "ENTRATA_HANDOFF"]
        held = [r for r in results if r.decision in ("HELD", "NOT_A_BILL")]
        s = lambda rs: str(sum(((r.amount or D0) for r in rs), D0))  # noqa: E731
        ledger.commit(view, {
            "run_id": run_id, "started_at": stamp, "inbox": project_path(inbox), "extractor": mode,
            "model": cfg.settings["extraction"]["model"], "prompt_version": cfg.settings["extraction"]["prompt_version"],
            "policy_hash": cfg.policy_hash, "git_commit": _git_commit(cfg.root), "docs": len(results), "entered": len(ent),
            "entrata": len(ntr), "held": len(held), "already_processed": sum(r.decision == "ALREADY_PROCESSED" for r in results),
            "amount_in": s(results), "amount_entered": s(ent), "amount_entrata": s(ntr), "amount_held": s(held),
        })
        rr.committed = True
    return rr
