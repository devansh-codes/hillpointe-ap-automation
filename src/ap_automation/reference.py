"""Master data, ERP history and import-template loaders (read live from the xlsx every run)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import openpyxl

from .util import money, norm_company, norm_phone, norm_text, parse_date


@dataclass
class Vendor:
    vendor_id: str
    name: str
    status: str
    vendor_type: str
    terms: str
    remit_address: str
    phone: str
    bank_last4: str
    coi_expiration: Optional[date]
    lien_waiver_required: bool
    default_gl: str
    owner_dept: str
    notes: str
    email: str = ""

    @property
    def active(self) -> bool:
        return self.status.lower() == "active"

    @property
    def term_days(self) -> int:
        m = re.search(r"(\d+)", self.terms or "")
        return int(m.group(1)) if m else 30

    @property
    def shared_software(self) -> bool:
        return "allocate" in self.notes.lower()


@dataclass
class Project:
    project_id: str
    name: str
    state: str
    owner_entity: str
    posting_entity: str
    status: str
    ap_system: str
    approver: str


@dataclass
class HistoryBill:
    record: str
    system: str
    vendor_id: str
    vendor_name: str
    bill_no: str
    doc_type: str
    bill_date: Optional[date]
    entity: str
    project_id: str
    task_id: str
    cost_type: str
    primary_gl: str
    reference: str
    gross: Decimal
    retainage: Decimal
    total: Decimal
    status: str


@dataclass
class MasterData:
    entities: dict[str, dict]
    projects: dict[str, Project]
    departments: dict[str, dict]
    gl_intacct: dict[str, str]
    gl_entrata: dict[str, str]
    cost_codes: dict[str, set[str]]
    cost_types: dict[str, str]  # type -> COGS account
    vendors: dict[str, Vendor]
    allocation: dict[str, Decimal]
    periods: dict[str, str]  # "2026-10" -> Open
    history: list[HistoryBill] = field(default_factory=list)

    # ---- lookups -------------------------------------------------------------------
    def open_periods(self, override: str | None = None) -> list[str]:
        if override:
            return [override]
        return sorted(k for k, v in self.periods.items() if v.lower() == "open")

    def entity_names(self) -> dict[str, str]:
        return {k: v["Legal Name"] for k, v in self.entities.items()}

    def project_by_text(self, text: str | None) -> Optional[Project]:
        """Find a project whose id or name appears in free text (longest name wins)."""
        t = norm_text(text)
        if not t:
            return None
        best = None
        for p in self.projects.values():
            if p.project_id in (text or "") or norm_text(p.name) in t:
                if best is None or len(p.name) > len(best.name):
                    best = p
        return best

    def vendor_by_phone(self, phone: str | None) -> list[Vendor]:
        p = norm_phone(phone)
        return [v for v in self.vendors.values() if p and norm_phone(v.phone) == p]


def _rows(ws):
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    out = []
    for r in rows[1:]:
        if r[0] is None:
            continue
        out.append({header[i]: r[i] for i in range(len(header)) if header[i]})
    return out


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def _period_key(label: str) -> str | None:
    """'October 2026' -> '2026-10'."""
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", label or "")
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    return f"{m.group(2)}-{_MONTHS.index(m.group(1).lower()) + 1:02d}"


def load_master_data(master_path: Path, history_path: Path) -> MasterData:
    wb = openpyxl.load_workbook(master_path, data_only=True)

    entities = {_s(r["ENTITY_ID"]): r for r in _rows(wb["Entities"])}
    projects = {}
    for r in _rows(wb["Projects"]):
        pid = _s(r["PROJECT_ID"])
        projects[pid] = Project(pid, _s(r["Project Name"]), _s(r["State"]), _s(r["Owner Entity"]), _s(r["AP Posting Entity"]),
                                _s(r["Status"]), _s(r["AP System"]), _s(r["Approver"]))
    departments = {_s(r["DEPARTMENT_ID"]): r for r in _rows(wb["Departments"])}
    gl_intacct = {_s(r["ACCT_NO"]): _s(r["Account Name"]) for r in _rows(wb["GL_Intacct"])}
    gl_entrata = {_s(r["Entrata GL"]): _s(r["Account Name"]) for r in _rows(wb["GL_Entrata"])}
    cost_codes = {_s(r["COST_CODE"]).zfill(5): {t.strip() for t in _s(r["Allowed Cost Types"]).split(",")} for r in _rows(wb["Cost_Codes"])}
    cost_types = {_s(r["COST_TYPE_ID"]): _s(r["COGS Account"]) for r in _rows(wb["Cost_Types"])}

    vendors = {}
    for r in _rows(wb["Vendors"]):
        vid = _s(r["VENDOR_ID"])
        coi = r.get("COI Expiration")
        vendors[vid] = Vendor(
            vendor_id=vid, name=_s(r["Vendor Name"]), status=_s(r["Status"]), vendor_type=_s(r["Vendor Type"]),
            terms=_s(r["Terms"]), remit_address=_s(r["Remit Address"]), phone=_s(r["Phone of Record"]),
            bank_last4=_s(r["Bank Acct Last 4"]).zfill(4) if _s(r["Bank Acct Last 4"]) else "",
            coi_expiration=parse_date(coi) if coi and _s(coi).upper() != "N/A" else None,
            lien_waiver_required=_s(r["Lien Waiver Required"]).upper() == "Y",
            default_gl=_s(r["Default GL"]), owner_dept=_s(r["Owner Dept"]), notes=_s(r["Notes"]),
            email=_s(r.get("Email")),
        )

    allocation = {}
    for r in wb["Allocation_Table"].iter_rows(min_row=2, values_only=True):
        if r[0] and _s(r[0]) in entities and isinstance(r[1], (int, float)):
            allocation[_s(r[0])] = Decimal(str(r[1]))

    periods = {}
    for r in _rows(wb["Periods"]):
        k = _period_key(_s(r["Period"]))
        if k:
            periods[k] = _s(r["Status"])

    md = MasterData(entities, projects, departments, gl_intacct, gl_entrata, cost_codes, cost_types, vendors, allocation, periods)
    md.history = load_history(history_path)
    return md


def load_history(path: Path) -> list[HistoryBill]:
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for r in _rows(wb["Bill_History"]):
        if not _s(r.get("VENDOR_ID")):
            continue
        out.append(HistoryBill(
            record=_s(r["Record"]), system=_s(r["System"]), vendor_id=_s(r["VENDOR_ID"]), vendor_name=_s(r["Vendor Name"]),
            bill_no=_s(r["Bill / Invoice No"]), doc_type=_s(r["Doc Type"]), bill_date=parse_date(r["Bill Date"]),
            entity=_s(r["Entity"]), project_id=_s(r["PROJECT_ID"]), task_id=_s(r["TASK_ID"]).zfill(5) if _s(r["TASK_ID"]) else "",
            cost_type=_s(r["COST_TYPE_ID"]), primary_gl=_s(r["Primary GL"]), reference=_s(r["Reference"]),
            gross=money(r["Gross Amount"]), retainage=money(r["Retainage"]), total=money(r["Bill Total"]), status=_s(r["Status"]),
        ))
    return out


def vendor_name_key(name: str) -> str:
    return norm_company(name)
