"""Template for a new rule. Copy the function into rules/custom.py, rename, then add the name to policy.yaml `rules:`.

Available on ctx (see context.py):
  ctx.ex            extracted facts (ExtractedDocument): ctx.ex.total, ctx.ex.line_items, ctx.ex.document_date ...
  ctx.total         Decimal total (negative for credits)       ctx.bill_date  date printed on the document
  ctx.vendor        vendor-master record (or None)             ctx.project    Projects-tab record (or None)
  ctx.category      'construction' | 'stabilized' | 'corporate' | 'unknown'
  ctx.ref           matched PO/subcontract/agreement (or None)  ctx.policy     policy.yaml as a dict
  ctx.is_bill / ctx.is_credit / ctx.is_pay_app

Return a list of Finding(code, message, policy_ref, hold=True|False, confidence='High'|'Medium'|'Low').
`hold=False` findings are informational notes that appear in the exception log without stopping entry.
"""
from decimal import Decimal

from ..models import Finding
from . import rule


@rule("example_corporate_needs_po")
def example_corporate_needs_po(ctx) -> list[Finding]:
    limit = Decimal(str(ctx.policy.get("example", {}).get("corporate_po_over", 10000)))
    if ctx.category == "corporate" and ctx.total > limit and not ctx.references:
        return [Finding("NOPO", f"Corporate bill over ${limit:,.0f} without an order form or PO.", "Local policy change")]
    return []
