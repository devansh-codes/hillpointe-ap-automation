"""Turn an accepted document into Intacct bill lines or Entrata handoff rows (PLAN §3.4).

Pure functions over Decimal. Any coding question the policy can't answer raises CodingError,
which the engine turns into an OTHER hold ("unclear means hold").
"""
from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from rapidfuzz import fuzz

from .context import Ctx
from .models import Bill, BillLine, EntrataRow
from .util import CENT, add_days, money, norm_text, truncate

D0 = Decimal("0")


class CodingError(Exception):
    pass


# ---------------------------------------------------------------------------- allocation helpers
def prorate(total: Decimal, weights: list[Decimal], remainder_to: int | None = None) -> list[Decimal]:
    """Split `total` over `weights` to the cent; rounding difference goes to `remainder_to` (default: largest weight)."""
    if not weights:
        return []
    base = sum(weights, D0)
    if base == 0:
        shares = [D0] * len(weights)
        shares[0] = total
        return shares
    shares = [(total * w / base).quantize(CENT, rounding=ROUND_HALF_UP) for w in weights]
    diff = total - sum(shares, D0)
    if diff:
        idx = remainder_to if remainder_to is not None else max(range(len(weights)), key=lambda i: abs(weights[i]))
        shares[idx] += diff
    return shares


def split_by_pct(total: Decimal, pcts: "OrderedDict[str, Decimal]", remainder_key: str) -> "OrderedDict[str, Decimal]":
    out = OrderedDict((k, (total * p).quantize(CENT, rounding=ROUND_HALF_UP)) for k, p in pcts.items())
    out[remainder_key] += total - sum(out.values(), D0)
    return out


# ---------------------------------------------------------------------------- dates and terms
def terms_for(ctx: Ctx) -> tuple[str, int]:
    ov = (ctx.policy.get("vendor_overrides") or {}).get(ctx.vendor.vendor_id, {})
    name = ov.get("terms") or ctx.vendor.terms or "Net 30"
    days = int("".join(ch for ch in name if ch.isdigit()) or 30)
    return name, days


def posting_date(ctx: Ctx, bill_date: date) -> date:
    override = (ctx.policy.get("periods") or {}).get("open_period_override")
    opens = ctx.md.open_periods(override)
    if not opens:
        raise CodingError("No open accounting period in the Periods tab.")
    key = f"{bill_date.year}-{bill_date.month:02d}"
    if key in opens:
        return bill_date
    y, m = map(int, opens[0].split("-"))
    ctx.trace(f"Bill date {bill_date:%m/%d/%Y} is not in an open period → GL posting date first day of {opens[0]}")
    return date(y, m, 1)


def due_date(ctx: Ctx, bill_date: date, adjustment: bool) -> date:
    if adjustment:
        return bill_date
    return add_days(bill_date, terms_for(ctx)[1])


# ---------------------------------------------------------------------------- line grouping
def _tax_total(ctx: Ctx) -> Decimal:
    return sum((money(t.amount) for t in ctx.ex.tax_lines), D0)


def _group_lines_to_ref(ctx: Ctx) -> "OrderedDict[str, Decimal]":
    """Map each invoice line to a PO line (by description similarity); delivery/freight follow their line."""
    ref = ctx.ref
    groups: "OrderedDict[str, Decimal]" = OrderedDict((rl.line_no, D0) for rl in ref.lines)
    if len(ref.lines) == 1:
        groups[ref.lines[0].line_no] = sum((money(l.amount) for l in ctx.ex.line_items), D0)
        return groups
    last = ref.lines[0].line_no
    for l in ctx.ex.line_items:
        scored = sorted(((fuzz.token_set_ratio(norm_text(l.description), norm_text(rl.description)), rl.line_no) for rl in ref.lines),
                        reverse=True)
        best_score, best = scored[0]
        if l.is_freight_or_delivery and best_score < 60:
            best = last
        elif best_score < 45:
            raise CodingError(f"Cannot tell which {ref.number} line '{l.description[:50]}' belongs to.")
        groups[best] += money(l.amount)
        last = best
        ctx.trace(f"Line '{l.description[:45]}' {money(l.amount):,.2f} → {ref.number} line {best} ({best_score:.0f}% match)")
    return OrderedDict((k, v) for k, v in groups.items() if v != 0)


def _with_tax(ctx: Ctx, groups: "OrderedDict[str, Decimal]") -> "OrderedDict[str, Decimal]":
    tax = _tax_total(ctx)
    if not tax:
        return groups
    keys = list(groups)
    shares = prorate(tax, [groups[k] for k in keys])
    if len(keys) > 1:
        ctx.trace("Tax " + f"{tax:,.2f} pro-rated: " + ", ".join(f"line {k} {s:,.2f}" for k, s in zip(keys, shares)))
    return OrderedDict((k, groups[k] + s) for k, s in zip(keys, shares))


def _short_vendor(name: str) -> str:
    return re.sub(r"[\s,]+(LLC|L\.L\.C\.|Inc\.?|Co\.?|Corp\.?|Company|LP|Ltd\.?)$", "", name.strip(), flags=re.I)


def _pct(p: Decimal) -> str:
    return f"{(p * 100).normalize():f}%"


def _description(ctx: Ctx, what: str) -> str:
    vname = _short_vendor(ctx.vendor.name)
    where = f" {ctx.project.name}" if ctx.project else ""
    return truncate(f"{vname} {what}{where}", 80)


# ---------------------------------------------------------------------------- Intacct bills
def code_construction(ctx: Ctx) -> Bill:
    ref, proj, ex = ctx.ref, ctx.project, ctx.ex
    route = ctx.policy["routing"][proj.status]
    loc, dept = route["entity"], route.get("department", "OPS")
    lines: list[BillLine] = []
    adjustment = ctx.is_credit
    if ctx.is_pay_app:
        pa = ex.pay_application
        rl = ref.lines[0] if ref.lines else None
        if rl is None or not rl.cost_code or not rl.cost_type:
            raise CodingError(f"{ref.number} has no cost code / cost type.")
        gross = sum((money(l.work_this_period) for l in pa.lines_this_period), D0) if pa.lines_this_period else None
        retain = sum((money(l.retainage_this_period or 0) for l in pa.lines_this_period), D0) if pa.lines_this_period else None
        if gross is None or (retain == 0 and pa.retainage_percent):
            raise CodingError("Pay application does not show this period's work and retainage.")
        gl = ctx.md.cost_types[rl.cost_type]
        appno = pa.application_no or ""
        lines.append(BillLine(gl, loc, dept, gross, truncate(f"Pay App {appno} " + "; ".join(l.description for l in pa.lines_this_period), 80),
                              proj.project_id, rl.cost_code, rl.cost_type, rl.line_no))
        if retain:
            pct = f"{pa.retainage_percent:g}% " if pa.retainage_percent else ""
            lines.append(BillLine(ctx.policy["retainage_gl"], loc, dept, -retain, f"Retainage {pct}Pay App {appno}",
                                  proj.project_id, rl.cost_code, rl.cost_type, rl.line_no))
        what = f"Pay App {appno}"
    elif adjustment:
        rl = _credit_coding_line(ctx)
        memo = truncate("; ".join(l.description for l in ex.line_items) or "Vendor credit", 80)
        lines.append(BillLine(ctx.md.cost_types[rl.cost_type], loc, dept, ctx.total, memo, proj.project_id, rl.cost_code, rl.cost_type, rl.line_no))
        what = f"credit vs {ex.credit_applies_to_invoice}" if ex.credit_applies_to_invoice else "credit memo"
    else:
        groups = _with_tax(ctx, _group_lines_to_ref(ctx))
        by_no = {rl.line_no: rl for rl in ref.lines}
        for ln, amt in groups.items():
            rl = by_no[ln]
            if not rl.cost_code or not rl.cost_type:
                raise CodingError(f"{ref.number} line {ln} has no cost code / cost type.")
            descs = [l.description for l in ex.line_items if _belongs(l.description, rl, ref)]
            memo = truncate(", ".join(descs) if descs else rl.description, 80)
            lines.append(BillLine(ctx.md.cost_types[rl.cost_type], loc, dept, amt, memo, proj.project_id, rl.cost_code, rl.cost_type, ln))
        what = "invoice"
    desc = _description(ctx, what)
    if adjustment and ex.credit_applies_to_invoice:
        desc = truncate(f"Credit vs inv {ex.credit_applies_to_invoice} {_short_vendor(ctx.vendor.name)} {proj.name}", 80)
    return _bill(ctx, lines, desc, ref.number, adjustment)


def _belongs(desc: str, rl, ref) -> bool:
    if len(ref.lines) == 1:
        return True
    best = max(ref.lines, key=lambda r: fuzz.token_set_ratio(norm_text(desc), norm_text(r.description)))
    return best.line_no == rl.line_no


def _credit_coding_line(ctx: Ctx):
    """Use the original bill's coding from history when available, else the PO line."""
    from .dedupe import norm_bill_no

    orig = ctx.ex.credit_applies_to_invoice
    if orig:
        onorm = norm_bill_no(orig, ctx.policy["dup"]["strip_prefixes"])
        for h in ctx.md.history:
            if h.vendor_id == ctx.vendor.vendor_id and norm_bill_no(h.bill_no, ctx.policy["dup"]["strip_prefixes"]) == onorm and h.task_id:
                ctx.trace(f"Credit coded like original {h.bill_no} ({h.record}): {h.project_id}/{h.task_id}/{h.cost_type}")
                from .refdocs import RefLineD
                return RefLineD("", "", h.task_id, h.cost_type, "", None, D0)
    if ctx.ref and ctx.ref.lines:
        return ctx.ref.lines[0]
    raise CodingError("Cannot determine the original coding for this credit.")


def code_corporate(ctx: Ctx) -> Bill:
    v, ex = ctx.vendor, ctx.ex
    route = ctx.policy["routing"]["corporate"]
    corp = ctx.policy.get("corporate", {})
    dept = v.owner_dept or corp.get("default_department")
    if not dept:
        raise CodingError("Corporate bill: no requesting or owner department in the vendor master; a person must assign the department.")
    gl = v.default_gl
    if not gl:
        hist = [h for h in ctx.md.history if h.vendor_id == v.vendor_id and h.primary_gl]
        if not hist:
            raise CodingError("Corporate bill: vendor has no Default GL and no coding history.")
        gl = hist[-1].primary_gl
        ctx.trace(f"GL {gl} taken from this vendor's last bill {hist[-1].bill_no} (no Default GL in vendor master)")
    entity = route["entity"]
    one_time_kw = [k.lower() for k in corp.get("one_time_service_keywords", [])]
    groups: "OrderedDict[str, Decimal]" = OrderedDict()
    for i, l in enumerate(ex.line_items):
        groups[str(i)] = money(l.amount)
    groups = _with_tax(ctx, groups) if groups else OrderedDict({"0": ctx.total})
    lines: list[BillLine] = []
    sub_total = D0
    for i, amt in groups.items():
        l = ex.line_items[int(i)] if ex.line_items else None
        desc = l.description if l else "Invoice total"
        if v.shared_software and l and any(k in desc.lower() for k in one_time_kw):
            lines.append(BillLine(corp.get("one_time_service_gl", "65010"), entity, dept, amt, truncate(f"One-time: {desc}", 80)))
            ctx.trace(f"'{desc[:40]}' is a one-time service → 100% {entity} GL {corp.get('one_time_service_gl')}")
        elif v.shared_software:
            sub_total += amt
        else:
            lines.append(BillLine(gl, entity, dept, amt, truncate(desc, 80)))
    if v.shared_software and sub_total:
        pcts = OrderedDict(ctx.md.allocation)
        if not pcts or sum(pcts.values()) != 1:
            raise CodingError("Allocation_Table percentages do not sum to 100%.")
        split = split_by_pct(sub_total, pcts, remainder_key=entity if entity in pcts else next(iter(pcts)))
        ctx.trace(f"Subscription {sub_total:,.2f} allocated: " + ", ".join(f"{k} {_pct(pcts[k])} = {a:,.2f}" for k, a in split.items()))
        alloc_lines = [BillLine(gl, k, dept, a, truncate(f"Subscription allocation {_pct(pcts[k])} {k}", 80)) for k, a in split.items()]
        lines = alloc_lines + lines
    ref = ctx.references[0] if ctx.references else ""
    return _bill(ctx, lines, _description(ctx, "invoice"), ref, ctx.is_credit)


def _bill(ctx: Ctx, lines: list[BillLine], desc: str, ref_no: str, adjustment: bool) -> Bill:
    bd = ctx.bill_date
    term_name, _ = terms_for(ctx)
    return Bill(bill_no=ctx.ex.document_number.strip(), doc_type="Adjustment" if adjustment else "Bill", vendor_id=ctx.vendor.vendor_id,
                bill_date=bd, gl_posting_date=posting_date(ctx, bd), due_date=due_date(ctx, bd, adjustment), term_name=term_name,
                reference_no=ref_no, description=desc, lines=lines, supdoc_id=ctx.doc.supdoc_id)


# ---------------------------------------------------------------------------- Entrata rows
def entrata_gl_for(ctx: Ctx, text: str) -> str:
    t = norm_text(text)
    best, best_len = "", 0
    for gl, kws in ctx.policy.get("entrata_gl_keywords", {}).items():
        for kw in kws:
            k = norm_text(kw)
            if k and k in t and len(k) > best_len and gl in ctx.md.gl_entrata:
                best, best_len = gl, len(k)
    return best


def code_entrata(ctx: Ctx, approver: str) -> list[EntrataRow]:
    proj, ex = ctx.project, ctx.ex
    items = [(l.description, money(l.amount)) for l in ex.line_items] or [(ex.ship_to_or_project_text or "Invoice", ctx.total)]
    groups: "OrderedDict[str, Decimal]" = OrderedDict()
    descs: dict[str, list[str]] = {}
    for desc, amt in items:
        gl = entrata_gl_for(ctx, desc)
        if not gl and ctx.ref and len(ctx.ref.lines) >= 1:
            gl = entrata_gl_for(ctx, " ".join(rl.description for rl in ctx.ref.lines))
        if not gl:
            hist = [h for h in ctx.md.history if h.vendor_id == ctx.vendor.vendor_id and h.system == "Entrata"]
            if len({h.primary_gl for h in hist}) == 1:
                gl = hist[0].primary_gl
                ctx.trace(f"'{desc[:40]}' → {gl} from this vendor's Entrata history")
        if not gl:
            raise CodingError(f"No Entrata GL fits '{desc[:60]}'; Property Accounting must choose the account.")
        groups[gl] = groups.get(gl, D0) + amt
        descs.setdefault(gl, []).append(desc)
        ctx.trace(f"'{desc[:45]}' {amt:,.2f} → Entrata GL {gl} {ctx.md.gl_entrata.get(gl, '')}")
    groups = _with_tax(ctx, groups)
    bd = ctx.bill_date
    post = posting_date(ctx, bd)
    fmt = ctx.policy.get("entrata_post_month_format", "%m/%Y")
    return [EntrataRow(property=proj.name, owner_entity=proj.owner_entity, project_id=proj.project_id, vendor_id=ctx.vendor.vendor_id,
                       vendor_name=ctx.vendor.name, invoice_no=ex.document_number, invoice_date=bd, post_month=post.strftime(fmt),
                       due_date=due_date(ctx, bd, ctx.is_credit), entrata_gl=gl,
                       description=truncate(f"{', '.join(descs[gl])}", 80), amount=amt, approver=approver, supdoc_id=ctx.doc.supdoc_id)
            for gl, amt in groups.items()]
