"""Field Guide as code. Intacct rejects the WHOLE file if one row fails, so a failing bill is held instead."""
from __future__ import annotations

from decimal import Decimal

from .models import Bill, EntrataRow
from .reference import MasterData


def _forbidden(acct: str, forbidden: list[str]) -> bool:
    for f in forbidden:
        if "-" in f:
            lo, hi = f.split("-")
            if acct.isdigit() and int(lo) <= int(acct) <= int(hi):
                return True
        elif acct == f:
            return True
    return False


def validate_bill(bill: Bill, md: MasterData, policy: dict, expected_total: Decimal, open_periods: list[str]) -> list[str]:
    errs: list[str] = []
    req = {"BILL_NO": bill.bill_no, "VENDOR_ID": bill.vendor_id, "TERM_NAME": bill.term_name, "DESCRIPTION": bill.description,
           "SUPDOC_ID": bill.supdoc_id}
    errs += [f"{k} is blank" for k, v in req.items() if not str(v or "").strip()]
    if bill.vendor_id not in md.vendors or not md.vendors[bill.vendor_id].active:
        errs.append(f"VENDOR_ID {bill.vendor_id} is not an active vendor")
    if bill.doc_type not in ("Bill", "Adjustment"):
        errs.append("DOC_TYPE must be Bill or Adjustment")
    if len(bill.description) > 80:
        errs.append("DESCRIPTION over 80 characters")
    if f"{bill.gl_posting_date.year}-{bill.gl_posting_date.month:02d}" not in open_periods:
        errs.append(f"GL_POSTING_DATE {bill.gl_posting_date} is not in an open period")
    if bill.doc_type == "Adjustment" and bill.due_date != bill.bill_date:
        errs.append("Adjustment DUE_DATE must equal BILL_DATE")
    if not bill.lines:
        errs.append("bill has no lines")
    valid_gl = set(md.gl_intacct) | set(md.cost_types.values())
    for i, l in enumerate(bill.lines, 1):
        p = f"line {i}"
        if _forbidden(l.acct_no, policy.get("forbidden_gl", [])):
            errs.append(f"{p}: ACCT_NO {l.acct_no} is system-controlled and may never be coded")
        elif l.acct_no not in valid_gl:
            errs.append(f"{p}: ACCT_NO {l.acct_no} is not in GL_Intacct")
        if l.location_id not in md.entities:
            errs.append(f"{p}: LOCATION_ID {l.location_id} unknown")
        if l.department_id not in md.departments:
            errs.append(f"{p}: DEPARTMENT_ID {l.department_id} unknown")
        if not l.memo or len(l.memo) > 80:
            errs.append(f"{p}: LINE_MEMO blank or over 80 characters")
        if l.task_id:
            if not l.project_id or l.project_id not in md.projects:
                errs.append(f"{p}: TASK_ID requires a valid PROJECT_ID")
            if l.task_id not in md.cost_codes:
                errs.append(f"{p}: TASK_ID {l.task_id} is not a cost code")
            elif l.cost_type_id not in md.cost_codes[l.task_id]:
                errs.append(f"{p}: cost type {l.cost_type_id} not allowed for cost code {l.task_id}")
            if l.acct_no != policy.get("retainage_gl") and md.cost_types.get(l.cost_type_id) != l.acct_no:
                errs.append(f"{p}: ACCT_NO {l.acct_no} does not match cost type {l.cost_type_id}")
        elif l.project_id or l.cost_type_id:
            errs.append(f"{p}: PROJECT_ID/COST_TYPE_ID set without TASK_ID")
        if bill.doc_type == "Adjustment" and l.amount >= 0:
            errs.append(f"{p}: Adjustment lines must be negative")
        if bill.doc_type == "Bill" and l.amount < 0 and l.acct_no != policy.get("retainage_gl"):
            errs.append(f"{p}: negative amount on a Bill outside retainage")
    if bill.total != expected_total:
        errs.append(f"lines sum to {bill.total:,.2f} but the document total is {expected_total:,.2f}")
    return errs


def validate_entrata(rows: list[EntrataRow], md: MasterData, expected_total: Decimal) -> list[str]:
    errs = []
    for r in rows:
        if r.entrata_gl not in md.gl_entrata:
            errs.append(f"Entrata GL {r.entrata_gl} not in GL_Entrata")
        if not r.approver:
            errs.append("approver blank")
    s = sum((r.amount for r in rows), Decimal("0"))
    if s != expected_total:
        errs.append(f"Entrata rows sum to {s:,.2f} but the invoice total is {expected_total:,.2f}")
    return errs
