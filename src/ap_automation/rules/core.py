"""Built-in rules. Each maps to a section of 04_AP_Policy (§n) and returns Findings.

hold=True  → the document is not entered (code routes per policy.yaml exception_codes)
hold=False → informational note shown in the exception log (document may still be entered)
"""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from ..dedupe import norm_bill_no, numeric_core
from ..models import Finding
from ..quality import check_arithmetic, check_grounding
from ..util import digits, money, norm_phone, norm_text
from . import rule

D0 = Decimal("0")


def _d(x) -> Decimal:
    return Decimal(str(x))


# ---------------------------------------------------------------------------------------------
@rule("not_a_bill")
def not_a_bill(ctx) -> list[Finding]:
    """§11: anything that is not a bill or credit is not entered (logged as OTHER)."""
    if ctx.is_bill:
        return []
    kind = ctx.ex.doc_kind.replace("_", " ")
    extra = ""
    if ctx.ex.doc_kind == "lien_waiver":
        extra = " Recorded as a waiver on file so a held pay application can be re-checked against it."
    elif ctx.ex.doc_kind in ("purchase_order", "subcontract", "service_agreement"):
        extra = " If it should be used for matching, add it to the purchase orders folder."
    return [Finding("OTHER", f"Document is a {kind}, not a bill or credit; nothing to enter.{extra}", "§11")]


@rule("extraction_quality")
def extraction_quality(ctx) -> list[Finding]:
    """Controls on the AI reading: grounding in raw text + arithmetic + required fields."""
    if not ctx.is_bill:
        return []
    pol = ctx.policy.get("extraction", {})
    out = check_grounding(ctx.doc, ctx.ex, pol.get("require_grounding", ["document_number", "total"]))
    out += check_arithmetic(ctx.ex, _d(pol.get("arithmetic_tolerance", 0.01)))
    if ctx.bill_date is None:
        out.append(Finding("OTHER", "No readable document date.", "§7", confidence="Low"))
    for w in ctx.ex.extraction_warnings:
        out.append(Finding("WARN", f"Reader was unsure: {w}", hold=False, confidence="Medium"))
    for o in ctx.ex.observations:
        ctx.trace(f"Reader observation: {o}")
    return out


@rule("vendor_master")
def vendor_master(ctx) -> list[Finding]:
    """§8: only Active vendor IDs; unknown vendor → NEWVEND."""
    if not ctx.is_bill:
        return []
    if ctx.vendor is None:
        phone_hits = ctx.md.vendor_by_phone(ctx.ex.vendor_phone)
        hint = f" Phone matches {phone_hits[0].vendor_id} {phone_hits[0].name}; confirm whether this is the same company." if phone_hits else ""
        if "INACTIVE" in ctx.vendor_note:
            return [Finding("OTHER", f"{ctx.vendor_note}. Inactive vendor IDs must not be used.{hint}", "§8")]
        return [Finding("NEWVEND", f"'{ctx.ex.vendor_name}' is not in the vendor master; do not create or guess an ID.{hint}", "§8")]
    if ctx.vendor_confidence != "High":
        return [Finding("INFO", ctx.vendor_note, "§8", hold=False, confidence="Medium")]
    return []


def _addr_tokens(s: str) -> tuple[set[str], set[str]]:
    zips = set(re.findall(r"\b\d{5}\b", s or ""))
    nums = set(re.findall(r"\b\d{2,5}\b", s or "")) - zips
    return zips, nums


@rule("payment_details")
def payment_details(ctx) -> list[Finding]:
    """§8: remit address / bank / phone / email must match the vendor master; any change request → BANKCHG."""
    v, ex = ctx.vendor, ctx.ex
    if not ctx.is_bill or v is None:
        return []
    issues = []
    if ex.payment_instruction_change_requested:
        issues.append(f"asks to change payment instructions (\"{(ex.payment_change_quote or '').strip()[:120]}\")")
    remit = ex.remit_to if (ex.remit_to and re.search(r"\d{5}", ex.remit_to)) else ex.vendor_address
    if remit:
        mz, mn = _addr_tokens(v.remit_address)
        iz, inn = _addr_tokens(remit)
        if (mz and iz and not (mz & iz)) or (mn and inn and not (mn & inn)):
            issues.append(f"remit address '{remit.strip()}' ≠ vendor master '{v.remit_address}'")
    if ex.vendor_phone and norm_phone(ex.vendor_phone) and norm_phone(ex.vendor_phone) != norm_phone(v.phone):
        issues.append(f"phone {ex.vendor_phone} ≠ phone of record {v.phone}")
    if ex.vendor_email and v.email and ex.vendor_email.strip().lower() != v.email.strip().lower():
        issues.append(f"email {ex.vendor_email} ≠ email of record {v.email}")
    if ex.bank_details_printed:
        printed = digits(ex.bank_details_printed)
        last4 = re.findall(r"(?:ending|last\s*4|acct\.?|account)[^\d]{0,15}(\d{4})", ex.bank_details_printed, re.I)
        cand = last4[-1] if last4 else (printed[-4:] if len(printed) >= 4 else "")
        if cand and v.bank_last4 and cand != v.bank_last4:
            issues.append(f"bank account ending {cand} ≠ account on file ending {v.bank_last4}")
    if not issues:
        return []
    return [Finding("BANKCHG", "Payment/contact details differ from the vendor master: " + "; ".join(issues)
                    + f". Treasury to verify by calling the phone number on file {v.phone}; never use contact details from the invoice.",
                    "§8")]


@rule("bill_to")
def bill_to(ctx) -> list[Finding]:
    """§2: wrong-but-valid Hillpointe entity → informational; non-Hillpointe name → hold."""
    if not ctx.is_bill:
        return []
    if not ctx.ex.bill_to_name and not ctx.ex.bill_to_block:
        return [Finding("WARN", "No bill-to block found on the document.", "§2", hold=False, confidence="Medium")]
    if not ctx.bill_to_entity:
        return [Finding("OTHER", f"Addressed to '{ctx.ex.bill_to_name}', which is not a Hillpointe legal entity.", "§2")]
    target = ""
    if ctx.category == "construction":
        target = ctx.policy["routing"]["Active Construction"]["entity"]
    elif ctx.category == "stabilized" and ctx.project:
        target = ctx.project.owner_entity
    if target and ctx.bill_to_entity != target and not (ctx.category == "stabilized" and ctx.bill_to_entity == "HPM"):
        return [Finding("INFO", f"Bill-to correction: addressed to {ctx.bill_to_entity} ({ctx.md.entities[ctx.bill_to_entity]['Legal Name']}); "
                                f"posted to {target} per the {ctx.category} routing rule.", "§2 Bill to corrections", hold=False)]
    return []


@rule("duplicates")
def duplicates(ctx) -> list[Finding]:
    """§10/§11: layered duplicate detection against ERP history + every prior run + earlier docs in this run."""
    if not ctx.is_bill or ctx.vendor is None or not ctx.ex.document_number:
        return []
    vid, norm, pol = ctx.vendor.vendor_id, ctx.bill_no_norm, ctx.policy
    prefixes = pol["dup"]["strip_prefixes"]
    entered = [e for e in ctx.history_and_ledger() if e.vendor_id == vid]
    marks = {m.upper() for m in ctx.ex.markings}
    is_revision = bool(ctx.ex.replaces_document_number or ctx.revision or any("REVISED" in m for m in marks))

    def where(e):
        return f"{e.system} record {e.file_name}" if e.source == "history" else f"run {e.run_id} ({e.file_name})"

    out: list[Finding] = []
    # Same-batch: a revised version of this document is in this batch → only the latest is entered
    rev_file = ctx.batch_revisions.get((vid, norm))
    if rev_file and rev_file != ctx.doc.name and not is_revision:
        return [Finding("OTHER", f"Superseded: a revised version of {ctx.ex.document_number} is in this batch ({rev_file}); only the latest version is evaluated.",
                        "§10 revised invoices", confidence="High")]

    if is_revision:
        orig = ctx.ex.replaces_document_number or ctx.base_no
        onorm = norm_bill_no(orig, prefixes)
        hit = [e for e in entered if e.bill_no_norm in (onorm, norm)]
        if hit:
            code = pol["dup"].get("revision_after_entered_code", "DUP")
            return [Finding(code, f"Revised invoice, but the original {orig} is already entered ({where(hit[0])}, {hit[0].amount:,.2f}). "
                                  "Only one version may be entered: AP Manager to decide whether to void the original and enter the revision.",
                            "§10 revised invoices", confidence="High")]
        prior = ctx.ledger.held_with_key(vid, onorm) + ctx.ledger.held_with_key(vid, norm)
        if prior:
            ctx.res.supersedes = prior[-1].sha256
            out.append(Finding("INFO", f"Revised invoice replaces {orig} ({prior[-1].file_name}), which was held ({prior[-1].primary_code}) and never entered. "
                                       "The revision is evaluated on its own; the original is marked superseded.", "§10/§11", hold=False))
        else:
            out.append(Finding("INFO", f"Marked as a revision of {orig}, which is not on file; evaluated normally.", "§10", hold=False, confidence="Medium"))
        return out

    # L1 exact normalised key
    l1 = [e for e in entered if e.bill_no_norm == norm]
    if l1:
        e = l1[0]
        same_amt = "same amount" if e.amount == ctx.total else f"amount on file {e.amount:,.2f} vs {ctx.total:,.2f}"
        stamp = f" Document is stamped {', '.join(sorted(marks))}." if marks else ""
        return [Finding("DUP", f"Already entered: {ctx.vendor.vendor_id} invoice {e.bill_no_raw} in {where(e)} ({same_amt}).{stamp}", "§10")]
    # L2 numeric core + same amount (formatting drift, e.g. INV-20417 vs 20417)
    core = numeric_core(ctx.ex.document_number)
    l2 = [e for e in entered if core and numeric_core(e.bill_no_raw) == core and e.amount == ctx.total]
    if l2:
        e = l2[0]
        return [Finding("DUP", f"Already entered as '{e.bill_no_raw}' in {where(e)}: same vendor, same number apart from formatting "
                               f"('{ctx.ex.document_number}'), same amount {e.amount:,.2f}.", "§10")]
    # Returned held document (different file, same key, previously held) → not a duplicate; re-check everything
    prior = [d for d in ctx.ledger.held_with_key(vid, norm) if d.sha256 != ctx.doc.sha256]
    if prior:
        ctx.res.returns = prior[-1].sha256
        out.append(Finding("INFO", f"Previously received as {prior[-1].file_name} and held ({prior[-1].primary_code}); never entered. "
                                   "Re-checked against every rule.", "§11", hold=False))
    # L3 same vendor + amount + service period, different number
    sp = ctx.service_period
    if sp:
        l3 = [e for e in entered if e.service_period == sp and e.amount == ctx.total]
        if l3:
            out.append(Finding("OTHER", f"Possible duplicate: {where(l3[0])} has the same vendor, amount and service period ({sp}) "
                                        f"under number {l3[0].bill_no_raw}.", "§10", confidence="Medium"))
            return out
    # L4 same vendor + amount + close date, different number
    days = int(pol["dup"].get("near_date_days", 7))
    if ctx.bill_date and days > 0:
        l4 = [e for e in entered if e.amount == ctx.total and e.bill_date and abs((e.bill_date - ctx.bill_date).days) <= days]
        if l4:
            out.append(Finding("OTHER", f"Possible duplicate: {where(l4[0])} has the same vendor and amount dated {l4[0].bill_date} "
                                        f"(within {days} days) under number {l4[0].bill_no_raw}.", "§10", confidence="Medium"))
    return out


def _likely_pos(ctx) -> list[tuple[int, object, str]]:
    """Rank this vendor's POs as candidates for an invoice that has no usable reference."""
    if ctx.vendor is None:
        return []
    cands = []
    unit_prices = {money(l.unit_price) for l in ctx.ex.line_items if l.unit_price is not None}
    tax_rates = {t.rate_percent for t in ctx.ex.tax_lines if t.rate_percent}
    for rd in ctx.refs.for_vendor(ctx.vendor.vendor_id):
        score, why = 0, []
        if any(l.unit_rate is not None and l.unit_rate in unit_prices for l in rd.lines):
            score += 3
            why.append("unit rate matches")
        proj = ctx.md.projects.get(rd.project_id)
        if proj and ctx.project and proj.project_id == ctx.project.project_id:
            score += 3
            why.append("project matches ship-to")
        if proj and tax_rates:
            state_rate = {"GA": 7.0, "SC": 8.0}.get(proj.state)
            if state_rate and state_rate in tax_rates:
                score += 1
                why.append(f"{proj.state} tax rate")
        cands.append((score, rd, ", ".join(why) or "same vendor"))
    return sorted(cands, key=lambda t: -t[0])


@rule("po_reference")
def po_reference(ctx) -> list[Finding]:
    """§6: construction invoices must reference a PO/subcontract that is on file, for this vendor."""
    if not ctx.is_bill or ctx.category not in ("construction", "unknown"):
        return []
    if ctx.category == "unknown":
        return [Finding("OTHER", "Cannot tell whether this is construction, a stabilized community or corporate: no project, "
                                 "reference or corporate vendor coding found.", "§2", confidence="Medium")]
    if ctx.ref and ctx.ref.kind in ("po", "sc"):
        if ctx.vendor and ctx.ref.vendor_id and ctx.ref.vendor_id != ctx.vendor.vendor_id:
            return [Finding("NOPO", f"{ctx.ref.number} belongs to vendor {ctx.ref.vendor_id}, not {ctx.vendor.vendor_id}.", "§6")]
        return []
    if ctx.ref_raw:
        return [Finding("NOPO", f"References {ctx.ref_raw}, which is not in the purchase order / subcontract files, so the contract "
                                "and project cannot be confirmed.", "§6", confidence="High")]
    msg = "No PO or subcontract referenced."
    cands = [c for c in _likely_pos(ctx) if c[0] > 0]
    conf = "High"
    if cands:
        s, rd, why = cands[0]
        p = ctx.md.projects.get(rd.project_id)
        msg += f" Likely match: {rd.number} ({p.name if p else rd.project_id}; {why}). Do not code to it until the project manager confirms."
        if p:
            ctx.project = p
    return [Finding("NOPO", msg, "§6", confidence=conf)]


def _rate_from_pricing(pricing: str) -> tuple[Decimal | None, str]:
    m = re.search(r"\$?([\d,]+\.?\d*)\s*(?:per|/)\s*([a-z]+)", pricing or "", re.I)
    if not m:
        return None, ""
    return money(m.group(1)), m.group(2).lower()


@rule("price_variance")
def price_variance(ctx) -> list[Finding]:
    """Two-way match on price (§6 / A-17). Warn by default; policy can make it a hold."""
    if not ctx.is_bill or ctx.is_credit or ctx.ref is None or ctx.ref.kind not in ("po",):
        return []
    pv = ctx.policy.get("price_variance", {})
    tol = _d(pv.get("tolerance_pct", 0.5)) / 100
    hold = pv.get("action", "warn") == "hold"
    issues = []
    for rl in ctx.ref.lines:
        rate, unit = (rl.unit_rate, "") if rl.unit_rate is not None else (None, "")
        r2, unit = _rate_from_pricing(rl.pricing)
        rate = rate if rate is not None else r2
        if rate is None or not unit:
            continue
        if unit.startswith("mo"):
            pre_tax = sum((money(l.amount) for l in ctx.ex.line_items), D0)
            if len(ctx.ref.lines) == 1 and abs(pre_tax - rate) > rate * tol:
                issues.append(f"billed {pre_tax:,.2f} for the month vs PO rate {rate:,.2f}/month")
        else:
            for l in ctx.ex.line_items:
                if l.unit and l.unit_price is not None and l.unit.lower().startswith(unit[:3]):
                    if abs(money(l.unit_price) - rate) > rate * tol:
                        issues.append(f"'{l.description[:40]}' billed at {money(l.unit_price):,.2f}/{l.unit} vs PO {rate:,.2f}/{unit}")
    if not issues:
        return []
    return [Finding("OTHER" if hold else "WARN", f"Price differs from {ctx.ref.number}: " + "; ".join(issues), "§6 two-way match",
                    hold=hold, confidence="Medium")]


def billed_to_date(ctx, ref_number: str, exclude_norm: str = "") -> tuple[Decimal, list[str]]:
    """PO consumption from ERP history + all prior runs + this run (incl. credits).

    `exclude_norm` leaves out this same bill (vendor + normalised number) so a resend is never counted against itself.
    """
    prefixes = ctx.policy["dup"]["strip_prefixes"]
    vid = ctx.vendor.vendor_id if ctx.vendor else ""
    total, parts = D0, []
    for h in ctx.md.history:
        if h.reference.upper() == ref_number.upper():
            if exclude_norm and h.vendor_id == vid and norm_bill_no(h.bill_no, prefixes) == exclude_norm:
                continue
            total += h.total
            parts.append(f"{h.record} {h.bill_no} {h.total:,.2f}")
    for ref, _line, amt, src, norm in ctx.ledger.po_used:
        if ref.upper() == ref_number.upper() and not (exclude_norm and norm == exclude_norm):
            total += amt
            parts.append(f"{src} {amt:,.2f}")
    for p in ctx.ledger.new_po:
        if p["reference"].upper() == ref_number.upper() and not (exclude_norm and p["bill_no_norm"] == exclude_norm):
            total += money(p["amount"])
            parts.append(f"this run {p['bill_no_norm']} {money(p['amount']):,.2f}")
    return total, parts


@rule("po_balance")
def po_balance(ctx) -> list[Finding]:
    """§6: hold when billed-to-date would exceed the PO by more than the tolerance; subcontracts vs executed contract."""
    if not ctx.is_bill or ctx.ref is None or ctx.category != "construction":
        return []
    tol = _d(ctx.policy["overpo"]["tolerance"])
    if ctx.ref.kind == "po":
        if ctx.is_credit:
            return []
        billed, parts = billed_to_date(ctx, ctx.ref.number, ctx.bill_no_norm)
        remaining = ctx.ref.total - billed
        over = ctx.total - remaining
        ctx.trace(f"PO {ctx.ref.number}: amount {ctx.ref.total:,.2f}, billed to date {billed:,.2f}, remaining {remaining:,.2f}, this bill {ctx.total:,.2f}")
        if over > tol:
            return [Finding("OVERPO", f"{ctx.ref.number} is {ctx.ref.total:,.2f}; billed to date {billed:,.2f} ({'; '.join(parts) or 'nothing'}); "
                                      f"remaining {remaining:,.2f}. This invoice ({ctx.total:,.2f}) exceeds it by {over:,.2f}, more than the "
                                      f"${tol:,.0f} tolerance. Needs a PO change order.", "§6")]
        if over > 0:
            return [Finding("INFO", f"Exceeds remaining PO balance by {over:,.2f}, within the ${tol:,.0f} tolerance.", "§6", hold=False)]
        return []
    if ctx.ref.kind == "sc" and ctx.is_pay_app:
        done = ctx.ex.pay_application.total_completed_to_date
        if done is not None and money(done) - ctx.ref.executed_contract > tol:
            return [Finding("OVERPO", f"Completed to date {money(done):,.2f} exceeds the executed subcontract value "
                                      f"{ctx.ref.executed_contract:,.2f} ({ctx.ref.number}, executed change orders only).", "§5/§6")]
    return []


@rule("change_orders")
def change_orders(ctx) -> list[Finding]:
    """§5.5: only executed change orders may be billed; otherwise hold the whole application."""
    if not ctx.is_bill or ctx.ref is None or ctx.ref.kind != "sc":
        return []
    pa = ctx.ex.pay_application
    billed = {(l.change_order_ref or "").upper().replace(" ", "") for l in ctx.ex.line_items if l.change_order_ref}
    if pa:
        billed |= {(l.change_order_ref or "").upper().replace(" ", "") for l in pa.lines_this_period if l.change_order_ref}
        billed |= {c.upper().replace(" ", "") for c in pa.change_orders_mentioned}
    billed.discard("")
    log = {c.co_id.upper().replace(" ", ""): c for c in ctx.ref.change_orders}
    bad = []
    for co in sorted(billed):
        c = log.get(co)
        if c is None:
            bad.append(f"{co} (not in the {ctx.ref.number} change order log)")
        elif not c.executed:
            bad.append(f"{co} '{c.description or ''}' {money(c.amount):,.2f} — status '{c.status_text}'")
    if pa and pa.net_change_by_change_orders is not None:
        executed = sum((money(c.amount) for c in ctx.ref.change_orders if c.executed), D0)
        if money(pa.net_change_by_change_orders) - executed > Decimal("0.01") and not bad:
            bad.append(f"net change by change orders {money(pa.net_change_by_change_orders):,.2f} > executed change orders {executed:,.2f}")
    if bad:
        return [Finding("UNAPPCO", "Application bills change order(s) that are not executed: " + "; ".join(bad)
                        + ". Hold the entire application and return it to the subcontractor for a revised application.", "§5.5")]
    return []


@rule("lien_waiver")
def lien_waiver(ctx) -> list[Finding]:
    """§5.3: vendors marked Lien Waiver Required must include a conditional waiver for the current payment."""
    v = ctx.vendor
    if not ctx.is_bill or ctx.is_credit or v is None or not v.lien_waiver_required:
        return []
    due = ctx.total
    w = ctx.ex.lien_waiver
    tol = _d(ctx.policy.get("lien", {}).get("waiver_amount_tolerance", 0.01))
    if w and w.present_in_document:
        problems = []
        if w.waiver_type and w.waiver_type != "conditional":
            problems.append(f"waiver is {w.waiver_type}, a conditional waiver is required")
        if w.amount is not None and abs(money(w.amount) - due) > tol:
            problems.append(f"waiver amount {money(w.amount):,.2f} ≠ current payment {due:,.2f}")
        if problems:
            return [Finding("LIEN", "Lien waiver attached but not acceptable: " + "; ".join(problems) + ".", "§5.3")]
        ctx.trace(f"Conditional lien waiver attached for {money(w.amount or due):,.2f}")
        return []
    if ctx.policy.get("lien", {}).get("accept_waiver_on_file", True):
        for wf in ctx.ledger.waivers + ctx.ledger.new_waivers:
            if wf["vendor_id"] == v.vendor_id and abs(money(wf["amount"]) - due) <= tol and (wf.get("waiver_type") or "conditional") == "conditional":
                return [Finding("INFO", f"Conditional lien waiver for {due:,.2f} received separately ({wf['file_name']}) and on file.", "§5.3 / A-16", hold=False)]
    said = " The application says the waiver will follow under separate cover." if (w and w.stated_to_follow_separately) else ""
    return [Finding("LIEN", f"{v.name} is marked Lien Waiver Required and no conditional waiver for the current payment "
                            f"({due:,.2f}) is attached or on file.{said}", "§5.3")]


@rule("coi")
def coi(ctx) -> list[Finding]:
    """§5.4: COI expiration must be on or after the bill date."""
    v = ctx.vendor
    if not ctx.is_bill or ctx.is_credit or v is None or v.coi_expiration is None or ctx.bill_date is None:
        return []
    grace = int(ctx.policy.get("coi", {}).get("grace_days", 0))
    if v.coi_expiration < ctx.bill_date - timedelta(days=grace):
        return [Finding("COI", f"Certificate of insurance expired {v.coi_expiration:%m/%d/%Y}, before the bill date {ctx.bill_date:%m/%d/%Y}.", "§5.4")]
    return []


@rule("pay_app_math")
def pay_app_math(ctx) -> list[Finding]:
    """§5.2: previous certificates on the application must agree to bill history (+ prior runs)."""
    if not ctx.is_pay_app or ctx.vendor is None or not ctx.policy.get("pay_app", {}).get("check_previous_certificates", True):
        return []
    pa = ctx.ex.pay_application
    if pa.previous_certificates is None:
        return [Finding("OTHER", "Pay application does not show previous certificates for payment.", "§5.2", confidence="Medium")]
    ref = ctx.ref.number if ctx.ref else (ctx.ref_raw or "")
    prior = [e for e in ctx.history_and_ledger()
             if e.vendor_id == ctx.vendor.vendor_id and (not ref or (e.reference or "").upper() == ref.upper())
             and e.bill_no_norm != ctx.bill_no_norm]
    prior_net = sum((e.amount for e in prior), D0)
    tol = _d(ctx.policy.get("pay_app", {}).get("tolerance", 0.01))
    ctx.trace(f"Previous certificates on application {money(pa.previous_certificates):,.2f}; history + prior runs {prior_net:,.2f} "
              f"({', '.join(e.bill_no_raw for e in prior) or 'none'})")
    if abs(money(pa.previous_certificates) - prior_net) > tol:
        return [Finding("OTHER", f"Previous certificates on the application ({money(pa.previous_certificates):,.2f}) do not agree to bills "
                                 f"on file for {ref or 'this subcontract'} ({prior_net:,.2f}: {', '.join(e.bill_no_raw for e in prior) or 'none'}). "
                                 "Something may have been missed, double-billed or altered.", "§5.2")]
    return []


@rule("credit_original")
def credit_original(ctx) -> list[Finding]:
    """§9: a credit is coded like the original bill; the original must be found."""
    if not ctx.is_credit or ctx.vendor is None:
        return []
    orig = ctx.ex.credit_applies_to_invoice
    if not orig:
        if ctx.ref:
            return [Finding("INFO", "Credit memo does not name the original invoice; coded from the referenced PO.", "§9 / A-20",
                            hold=False, confidence="Medium")]
        return [Finding("OTHER", "Credit memo names no original invoice and no PO, so it cannot be coded like the original.", "§9")]
    onorm = norm_bill_no(orig, ctx.policy["dup"]["strip_prefixes"])
    hit = [e for e in ctx.history_and_ledger() if e.vendor_id == ctx.vendor.vendor_id and e.bill_no_norm == onorm]
    if hit:
        ctx.trace(f"Original invoice {orig} found ({hit[0].file_name}); credit coded the same way")
        return []
    if ctx.ref:
        return [Finding("INFO", f"Original invoice {orig} not found in history or prior runs; coded from {ctx.ref.number}.",
                        "§9 / A-20", hold=False, confidence="Medium")]
    return [Finding("OTHER", f"Original invoice {orig} is not on file and no PO is referenced; cannot code the credit.", "§9")]


@rule("service_agreement_fee")
def service_agreement_fee(ctx) -> list[Finding]:
    """§6: stabilized community service invoices must match the monthly fee in the service agreement."""
    if not ctx.is_bill or ctx.category != "stabilized":
        return []
    if ctx.ref is None or ctx.ref.kind != "sa":
        if ctx.ref_raw:
            return [Finding("OTHER", f"References {ctx.ref_raw}, which is not on file.", "§6")]
        return [Finding("INFO", "No service agreement referenced or on file for this vendor; monthly-fee check not applicable.",
                        "§6 / A-14", hold=False, confidence="Medium")]
    if ctx.vendor and ctx.ref.vendor_id and ctx.ref.vendor_id != ctx.vendor.vendor_id:
        return [Finding("OTHER", f"{ctx.ref.number} is with vendor {ctx.ref.vendor_id}, not {ctx.vendor.vendor_id}.", "§6")]
    fee = ctx.ref.monthly_fee
    tol = _d(ctx.policy.get("service_agreement", {}).get("fee_tolerance", 0.01))
    if fee is not None and abs(ctx.total - fee) > tol and not ctx.is_credit:
        return [Finding("OTHER", f"Invoice {ctx.total:,.2f} does not match the {ctx.ref.number} monthly fee {fee:,.2f}.", "§6")]
    return []


@rule("embedded_instructions")
def embedded_instructions(ctx) -> list[Finding]:
    """Text inside a document that tries to instruct the system is a fraud signal; a person must look."""
    if not ctx.ex.embedded_instructions:
        return []
    q = "; ".join(s[:100] for s in ctx.ex.embedded_instructions)
    return [Finding("OTHER", f"Document contains instructions aimed at the reviewer/system (\"{q}\"). Ignored; held for review.",
                    "Control", confidence="Medium")]


def _sim(a: str, b: str) -> float:
    return fuzz.token_set_ratio(norm_text(a), norm_text(b))
