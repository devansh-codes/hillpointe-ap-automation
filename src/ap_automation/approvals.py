"""Approval matrix (§13), driven by policy.yaml `approvals`."""
from __future__ import annotations

from decimal import Decimal

from .context import Ctx
from .models import Bill


def approvers(ctx: Ctx, bill: Bill | None, gross_work: Decimal | None = None) -> list[str]:
    a = ctx.policy["approvals"]
    if ctx.is_credit:
        return [a["adjustment"]["approver"]]
    total = bill.total if bill else ctx.total
    if ctx.category == "construction":
        cfg = a["construction"]
        out = [ctx.project.approver if cfg["approver"] == "PROJECT_APPROVER" else cfg["approver"]]
        gross = gross_work if gross_work is not None else total
        add = cfg.get("additional")
        if add and gross > Decimal(str(add["when_gross_work_over"])):
            out.append(f"{add['title']} (gross work {gross:,.2f} > {Decimal(str(add['when_gross_work_over'])):,.0f})")
        return out
    if ctx.category == "stabilized":
        cfg = a["stabilized"]
        out = [ctx.project.approver if cfg["approver"] == "PROJECT_APPROVER" else cfg["approver"]]
        add = cfg.get("additional")
        if add and total > Decimal(str(add["when_invoice_over"])):
            out.append(f"{add['title']} (invoice {total:,.2f} > {Decimal(str(add['when_invoice_over'])):,.0f})")
        return out
    cfg = a["corporate"]
    dept_id = bill.lines[0].department_id if bill and bill.lines else (ctx.vendor.owner_dept if ctx.vendor else "")
    dept_name = ctx.md.departments.get(dept_id, {}).get("Department", dept_id)
    out = [cfg["approver"].format(department=f"{dept_name} ({dept_id})")]
    add = cfg.get("additional")
    if add and total > Decimal(str(add["when_bill_over"])):
        out.append(f"{add['title']} (bill {total:,.2f} > {Decimal(str(add['when_bill_over'])):,.0f})")
    return out
