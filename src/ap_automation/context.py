"""Per-document context: resolved vendor, project, reference document and category.

Resolution only looks things up in reference data. It never invents IDs; anything it
can't confirm is left empty and a rule turns that into a hold.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from rapidfuzz import fuzz

from .config import Config
from .dedupe import norm_bill_no, split_revision
from .extract import IntakeDoc
from .ledger import EnteredBill, LedgerView
from .models import DocResult, ExtractedDocument
from .reference import MasterData, Project, Vendor
from .refdocs import RefDoc, RefIndex, find_references
from .util import money, norm_company, parse_date

BILL_KINDS = ("invoice", "pay_application", "credit_memo")


@dataclass
class Ctx:
    cfg: Config
    md: MasterData
    refs: RefIndex
    ledger: LedgerView
    doc: IntakeDoc
    ex: ExtractedDocument
    res: DocResult
    run_id: str
    batch_revisions: dict[tuple[str, str], str] = field(default_factory=dict)  # (vendor_id, norm original) -> file
    vendor: Optional[Vendor] = None
    vendor_note: str = ""
    vendor_confidence: str = "High"
    references: list[str] = field(default_factory=list)
    ref: Optional[RefDoc] = None
    ref_raw: str = ""  # reference printed but not on file
    project: Optional[Project] = None
    category: str = "unknown"
    bill_to_entity: str = ""
    bill_date: Optional[date] = None
    total: Decimal = Decimal("0")
    bill_no_norm: str = ""
    base_no: str = ""
    revision: str = ""

    @property
    def policy(self) -> dict:
        return self.cfg.policy

    @property
    def is_bill(self) -> bool:
        return self.ex.doc_kind in BILL_KINDS

    @property
    def is_credit(self) -> bool:
        return self.ex.doc_kind == "credit_memo" or (self.ex.total is not None and self.ex.total < 0)

    @property
    def is_pay_app(self) -> bool:
        return self.ex.doc_kind == "pay_application" and self.ex.pay_application is not None

    @property
    def service_period(self) -> str:
        s, e = self.ex.service_period_start, self.ex.service_period_end
        return f"{s}..{e}" if s and e else ""

    def history_and_ledger(self) -> list[EnteredBill]:
        hist = [EnteredBill(h.vendor_id, norm_bill_no(h.bill_no, self.policy["dup"]["strip_prefixes"]), h.bill_no, h.system,
                            h.doc_type, h.total, h.bill_date, "", h.reference, "", h.record, "history", source="history")
                for h in self.md.history]
        return hist + self.ledger.all_entered()

    def trace(self, msg: str) -> None:
        self.res.trace.append(msg)


# --------------------------------------------------------------------------------------

def resolve_vendor(md: MasterData, ex: ExtractedDocument) -> tuple[Optional[Vendor], str, str]:
    """Returns (vendor, note, confidence). Only ever returns an ACTIVE vendor."""
    if ex.vendor_id_printed and ex.vendor_id_printed.upper() in md.vendors:
        v = md.vendors[ex.vendor_id_printed.upper()]
        if v.active:
            return v, f"vendor id {v.vendor_id} printed on document", "High"
    name = norm_company(ex.vendor_name)
    if not name:
        return None, "no vendor name on document", "Low"
    scored = sorted(((fuzz.token_sort_ratio(name, norm_company(v.name)), v) for v in md.vendors.values()),
                    key=lambda t: (t[0], t[1].active), reverse=True)
    best_score, best = scored[0]
    if best_score < 90:
        return None, f"no vendor-master match for '{ex.vendor_name}' (closest: {best.name}, {best_score:.0f}%)", "High"
    exact_active = [v for s, v in scored if s >= 99 and v.active]
    if exact_active:
        return exact_active[0], f"name matches vendor master '{exact_active[0].name}'", "High"
    if best.active:
        return best, f"name '{ex.vendor_name}' ≈ vendor master '{best.name}' ({best_score:.0f}%)", "Medium" if best_score < 97 else "High"
    # Best match is an inactive record: only follow a documented merge to its surviving active record.
    m = re.search(r"merged into (V\d+)", best.notes, re.I)
    if m and m.group(1) in md.vendors and md.vendors[m.group(1)].active:
        v = md.vendors[m.group(1)]
        return v, f"name matches INACTIVE {best.vendor_id} ({best.name}); vendor master says merged into {v.vendor_id}", "Medium"
    return None, f"name matches only INACTIVE vendor {best.vendor_id} ({best.name}) with no surviving record", "High"


def resolve_bill_to(md: MasterData, ex: ExtractedDocument) -> str:
    """Entity id the document is addressed to, or '' if not a Hillpointe entity."""
    candidates = [ex.bill_to_name or ""] + (ex.bill_to_block or "").splitlines()
    for raw in candidates:
        n = norm_company(raw.replace("c/o", ""))
        if not n:
            continue
        for eid, legal in md.entity_names().items():
            if fuzz.ratio(n, norm_company(legal)) >= 92:
                return eid
        for p in md.projects.values():
            if fuzz.ratio(n, norm_company(p.name)) >= 92:
                return p.owner_entity
    return ""


def _construction_vendor(v: Optional[Vendor]) -> bool:
    return bool(v) and any(k in v.vendor_type.lower() for k in ("subcontractor", "material", "equipment", "site"))


def build_ctx(cfg: Config, md: MasterData, refs: RefIndex, ledger: LedgerView, doc: IntakeDoc, ex: ExtractedDocument,
              res: DocResult, run_id: str, batch_revisions: dict) -> Ctx:
    c = Ctx(cfg, md, refs, ledger, doc, ex, res, run_id, batch_revisions)
    pol = cfg.policy
    c.bill_date = parse_date(ex.document_date)
    tot = ex.total
    if tot is None and ex.pay_application and ex.pay_application.current_payment_due is not None:
        tot = ex.pay_application.current_payment_due
    c.total = money(tot)
    if ex.doc_kind == "credit_memo" and c.total > 0:
        c.total = -c.total
    c.base_no, c.revision = split_revision(ex.document_number)
    c.bill_no_norm = norm_bill_no(ex.document_number, pol["dup"]["strip_prefixes"])

    c.vendor, c.vendor_note, c.vendor_confidence = resolve_vendor(md, ex)
    c.trace(f"Vendor: {c.vendor_note}" + (f" → {c.vendor.vendor_id}" if c.vendor else ""))
    c.bill_to_entity = resolve_bill_to(md, ex)

    # Reference documents
    c.references = find_references(*(ex.references or []), ex.customer_ref_raw, *(ex.notes or []))
    for r in c.references:
        rd = refs.get(r)
        if rd and rd.kind in ("po", "sc", "sa"):
            c.ref = rd
            break
    if c.ref is None:
        c.ref_raw = next((r for r in c.references if not r.startswith("OF-")), "")
    if c.ref:
        c.trace(f"Reference {c.ref.number} found on file ({c.ref.source_file}); project {c.ref.project_id}")
    elif c.references:
        c.trace(f"References printed: {', '.join(c.references)} (no matching PO/subcontract/agreement on file)")
    else:
        c.trace("No PO / subcontract / agreement reference printed")

    # Project & category
    if c.ref and c.ref.project_id in md.projects:
        c.project = md.projects[c.ref.project_id]
    if c.project is None and c.ref_raw:
        m = re.search(r"(\d{6,7})", c.ref_raw)
        if m and m.group(1) in md.projects:
            c.project = md.projects[m.group(1)]
    if c.project is None:
        c.project = md.project_by_text(" ".join(filter(None, [ex.ship_to_or_project_text, ex.bill_to_block, ex.bill_to_name])))

    if c.project is not None:
        route = pol["routing"].get(c.project.status)
        c.category = route["category"] if route else "unknown"
        c.trace(f"Project {c.project.project_id} {c.project.name} is '{c.project.status}' → {c.category}")
    elif c.vendor and (c.vendor.default_gl or c.vendor.owner_dept or "software" in c.vendor.vendor_type.lower()
                       or "office" in c.vendor.vendor_type.lower()):
        c.category = "corporate"
        c.trace("No project; vendor is a corporate/G&A vendor → corporate")
    elif c.bill_to_entity == "HCM" and not _construction_vendor(c.vendor):
        c.category = "corporate"
        c.trace("No project; addressed to HCM → corporate")
    elif _construction_vendor(c.vendor):
        c.category = "construction"
        c.trace("Construction vendor but the project cannot be identified from the document")
    else:
        c.category = "unknown"
        c.trace("Category could not be determined")
    res.category = c.category
    return c
