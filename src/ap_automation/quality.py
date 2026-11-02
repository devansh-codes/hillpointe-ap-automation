"""Controls that make the model's reading trustworthy (run before any business rule).

1. Schema         - enforced by structured outputs + Pydantic validation (extract.py).
2. Arithmetic     - lines + tax = total; pay-app summary lines tie.
3. Grounding      - invoice number and total must appear in the PDF text layer.
Any failure -> hold as OTHER with Low confidence ("unclear means hold").
"""
from __future__ import annotations

import re
from decimal import Decimal

from .extract import IntakeDoc
from .models import ExtractedDocument, Finding
from .util import compact, money


def _amount_in_text(amount: Decimal, text: str) -> bool:
    plain = text.replace(",", "").replace("$", "")
    a = f"{abs(amount):.2f}"
    return re.search(rf"(?<![\d.]){re.escape(a)}(?!\d)", plain) is not None


def check_grounding(doc: IntakeDoc, ex: ExtractedDocument, required: list[str]) -> list[Finding]:
    if not doc.has_text_layer:
        return [Finding("WARN", "No text layer (image or scan): fields could not be cross-checked against raw text.",
                        hold=False, confidence="Medium")]
    out = []
    text_c = compact(doc.text)
    if "document_number" in required and ex.doc_kind not in ("lien_waiver", "statement", "other"):
        if not ex.document_number:
            out.append(Finding("OTHER", "No invoice/document number could be read.", "Field Guide BILL_NO", confidence="Low"))
        elif compact(ex.document_number) not in text_c:
            out.append(Finding("OTHER", f"Extracted invoice number '{ex.document_number}' does not appear in the document text.",
                               "Extraction control", confidence="Low"))
    total = ex.total if ex.total is not None else (ex.pay_application.current_payment_due if ex.pay_application else None)
    if "total" in required and ex.doc_kind in ("invoice", "pay_application", "credit_memo"):
        if total is None:
            out.append(Finding("OTHER", "No total amount could be read.", "Extraction control", confidence="Low"))
        elif not _amount_in_text(money(total), doc.text):
            out.append(Finding("OTHER", f"Extracted total {money(total):,.2f} does not appear in the document text.",
                               "Extraction control", confidence="Low"))
    return out


def check_arithmetic(ex: ExtractedDocument, tol: Decimal) -> list[Finding]:
    out: list[Finding] = []

    def bad(msg: str) -> None:
        out.append(Finding("OTHER", f"Arithmetic does not tie: {msg}", "Extraction control", confidence="Low"))

    if ex.doc_kind in ("invoice", "credit_memo") and ex.line_items:
        lines = sum((money(l.amount) for l in ex.line_items), Decimal("0"))
        tax = sum((money(t.amount) for t in ex.tax_lines), Decimal("0"))
        if ex.subtotal is not None and abs(lines - money(ex.subtotal)) > tol:
            bad(f"sum of lines {lines:,.2f} ≠ subtotal {money(ex.subtotal):,.2f}")
        base = money(ex.subtotal) if ex.subtotal is not None else lines
        if ex.total is not None and abs(base + tax - money(ex.total)) > tol:
            bad(f"subtotal {base:,.2f} + tax {tax:,.2f} ≠ total {money(ex.total):,.2f}")
        for l in ex.line_items:
            if l.quantity is not None and l.unit_price is not None and abs(money(l.quantity * l.unit_price) - money(l.amount)) > Decimal("0.02"):
                bad(f"line '{l.description[:40]}' qty × rate ≠ amount")
    pa = ex.pay_application
    if ex.doc_kind == "pay_application":
        if pa is None:
            bad("pay application summary missing")
            return out
        g = {k: (money(v) if v is not None else None) for k, v in pa.model_dump().items() if isinstance(v, (int, float))}
        def eq(a, b, label):
            if a is not None and b is not None and abs(a - b) > tol:
                bad(label)
        o, c, s = g.get("original_contract_sum"), g.get("net_change_by_change_orders"), g.get("contract_sum_to_date")
        if o is not None and c is not None:
            eq(o + c, s, "contract sum to date ≠ original + change orders")
        done, ret, earned = g.get("total_completed_to_date"), g.get("retainage_to_date"), g.get("total_earned_less_retainage")
        if done is not None and ret is not None:
            eq(done - ret, earned, "earned less retainage ≠ completed − retainage")
        prev, due = g.get("previous_certificates"), g.get("current_payment_due")
        if earned is not None and prev is not None:
            eq(earned - prev, due, "current payment due ≠ earned − previous certificates")
        if pa.lines_this_period and due is not None:
            work = sum((money(l.work_this_period) for l in pa.lines_this_period), Decimal("0"))
            r = sum((money(l.retainage_this_period or 0) for l in pa.lines_this_period), Decimal("0"))
            eq(work - r, due, "this period's work − retainage ≠ current payment due")
    return out
