"""Index of purchase orders, subcontracts and service agreements (extracted from 03_* at run time)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import ChangeOrder, ExtractedDocument
from .util import compact, money

REF_PATTERNS = [
    re.compile(r"\bPO[\s#:-]*\d{5,8}-\d{2,4}\b", re.I),
    re.compile(r"\bSC[\s#:-]*\d{5,8}-\d{2,4}\b", re.I),
    re.compile(r"\bSA-[A-Z0-9]+-\d{4}\b", re.I),
    re.compile(r"\bOF-\d{4}-\d{3,5}\b", re.I),
]


@dataclass
class RefLineD:
    line_no: str
    description: str
    cost_code: str
    cost_type: str
    pricing: str
    unit_rate: Optional[Decimal]
    amount: Decimal


@dataclass
class RefDoc:
    number: str
    kind: str  # po | sc | sa
    vendor_id: str
    vendor_name: str
    project_id: str
    lines: list[RefLineD]
    total: Decimal
    original_contract: Decimal = Decimal("0")
    change_orders: list[ChangeOrder] = field(default_factory=list)
    monthly_fee: Optional[Decimal] = None
    source_file: str = ""

    @property
    def executed_contract(self) -> Decimal:
        return self.original_contract + sum((money(c.amount) for c in self.change_orders if c.executed), Decimal("0"))


def find_references(*texts: str | None) -> list[str]:
    seen: list[str] = []
    for t in texts:
        for pat in REF_PATTERNS:
            for m in pat.finditer(t or ""):
                ref = re.sub(r"[\s#:]", "", m.group(0)).upper()
                ref = re.sub(r"^(PO|SC)-?", r"\1", ref) if not ref.startswith("SA-") else ref
                if ref not in seen:
                    seen.append(ref)
    return seen


class RefIndex:
    def __init__(self) -> None:
        self.docs: dict[str, RefDoc] = {}
        self.warnings: list[str] = []

    def add(self, ex: ExtractedDocument, source_file: str) -> None:
        kind = {"purchase_order": "po", "subcontract": "sc", "service_agreement": "sa"}.get(ex.doc_kind)
        if not kind or not ex.document_number:
            self.warnings.append(f"{source_file}: not a usable PO/subcontract/agreement ({ex.doc_kind})")
            return
        proj = re.search(r"\b(\d{6,7})\b", ex.ref_project_text or "")
        lines = [RefLineD(l.line_no or str(i + 1), l.description, (l.cost_code or "").zfill(5) if l.cost_code else "",
                          (l.cost_type or "").upper(), l.pricing or "",
                          money(l.unit_rate) if l.unit_rate is not None else None, money(l.amount))
                 for i, l in enumerate(ex.ref_lines)]
        total = money(ex.ref_total) if ex.ref_total is not None else sum((l.amount for l in lines), Decimal("0"))
        number = self._canon(ex.document_number)
        self.docs[number] = RefDoc(
            number=number, kind=kind, vendor_id=(ex.vendor_id_printed or "").upper(), vendor_name=ex.vendor_name or "",
            project_id=proj.group(1) if proj else "", lines=lines, total=total,
            original_contract=money(ex.original_contract_sum) if ex.original_contract_sum is not None else total,
            change_orders=ex.change_orders,
            monthly_fee=money(ex.monthly_fee) if ex.monthly_fee is not None else None, source_file=source_file,
        )

    @staticmethod
    def _canon(ref: str) -> str:
        found = find_references(ref)
        return found[0] if found else ref.upper().replace(" ", "")

    def get(self, ref: str) -> Optional[RefDoc]:
        return self.docs.get(self._canon(ref))

    def for_vendor(self, vendor_id: str) -> list[RefDoc]:
        return [d for d in self.docs.values() if d.vendor_id == vendor_id]
