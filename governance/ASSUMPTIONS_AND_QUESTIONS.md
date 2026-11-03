# Assumptions & Open Questions

The brief says: "If something is unclear, email your question… Where you make an assumption instead, write it down."
Each assumption is applied in code via config where possible, so it can be flipped in the live session.

| ID | Topic | Assumption | Effect on Batch 01 | Email Hillpointe? |
|---|---|---|---|---|
| A-1 | Credit vs PO balance order | Credits in the same run are applied to PO billed-to-date **before** invoices (conservative: more remaining balance). | 0001 is OVERPO either way (over by 1,392.07 or 3,552.07) | No, outcome doesn't change |
| A-2 | Pay-app line structure | One gross line (total work this period) + one retainage line, like Example_Completed. Not split per building. | 0003 → 2 lines | Optional |
| A-3 | Pay app in a closed period | GL_POSTING_DATE moves to 10/01/2026; DUE_DATE still = bill date + terms (10/30/2026). | 0003 | Yes, quick confirm |
| A-4 | Tax/delivery on multi-line PO | Delivery lines are grouped with the rental line they serve; tax allocated pro-rata on taxable lines; rounding to the largest line. | 0010 → 2 lines (5,616.00 / 1,452.60) | No |
| A-5 | Credit memo tax | Credit entered as one negative line including tax (tax follows the line). TERM_NAME = vendor master terms; DUE_DATE = bill date. | 0011 | No |
| A-6 | Multiple hold reasons | Report all codes; primary by precedence in ADR-0006 (e.g. 0013 LIEN primary, COI secondary; 0009 UNAPPCO primary, LIEN secondary). | 0009, 0013 | No |
| A-7 | Entrata "Post Month" format | `10/2026` (MM/YYYY). | 0008 | Yes, quick confirm |
| A-8 | Missing vendor-master email | Vendor master has no email column, so an invoice email can't "differ". Not BANKCHG by itself; remit/phone/bank still checked. | 0002 not held | No |
| A-9 | Corporate department | LedgerLoop lines use vendor Owner Dept `IT` on every allocated line, including HPC/HPM lines. | 0002 | Optional |
| A-10 | Re-processing a held file unchanged | Same hash → re-evaluated against current rules (policy §11), same result expected; not logged as DUP. | Rerun evidence | No |
| A-11 | Revised invoice whose original was entered | Hold as DUP → AP Manager (voiding the original is a human decision). Not exercised in this package. | — | Optional |
| A-12 | Possible-duplicate (same vendor+amount+date, different number) | Hold as OTHER for review rather than auto-DUP. | — | No |
| A-13 | Subcontract not in package (e.g. SC241088-04 Live Oak) | Can't verify CO status → hold **NOPO** "not in the subcontract files, cannot be confirmed", route PM (changed from OTHER, PLAN C-4). | Live-session readiness | Yes |
| A-14 | Stabilized invoice with no service agreement (e.g. Keystone repair) | Fee-match rule only applies when an SA exists; GL from description (e.g. 6300-0160). | Live-session readiness | Optional |
| A-15 | Bluewater office supplies precedent | History codes BOP to HPC / 62107 with no dept. Treat as corporate, entity/dept from requesting party on invoice; if unclear → OTHER. | Live-session readiness | Yes |

| A-16 | Lien waiver under separate cover | A standalone conditional waiver on file that matches vendor + project + current payment amount + through-date satisfies the LIEN rule when the held pay app is re-evaluated. Toggle `lien.accept_waiver_on_file`. | 0013 stays held (COI) either way | Yes |
| A-17 | Unit-price variance vs PO | The policy has no price-variance hold, so a rate mismatch is a **warning** in the exception log, not a hold. Toggle `price_variance.action`. | None in Batch 01 (all rates match) | Optional |
| A-18 | Two-way match only | No receiving records are in the package, so matching is invoice ↔ PO/SC/SA. Delivery notes on the invoice ("signed by site super") are kept as evidence but not required. | — | No |
| A-19 | Processing order within a run | Credits first, then bill date, then file name, so PO balances are deterministic. | 0011 before 0001 | No |
| A-20 | Credit memo with no original on file | Code from the referenced PO at Medium confidence. If there's no PO either, hold OTHER → AP Manager. | 0011's original PBS-603977 is in history | Optional |
| A-21 | Original + revision in the same batch | Enter only the latest; log the earlier one as SUPERSEDED (info). | — | No |
| A-22 | Bill addressed to an entity whose AP system is neither Intacct nor Entrata (Entities tab: OZF1 → Juniper Square) with no project tying it elsewhere | Hold OTHER → AP Manager. The policy does not cover it. If a PO/subcontract identifies the project, the §2 bill-to correction applies instead. | Entities tab "AP System" column | Optional |
| A-23 | Bill dated in a **future** period (e.g. 11/03/2026 while only October is open) | Follow §6 literally ("otherwise, the first day of the current open period") → posts 10/01, but show a WARN on the bill so a person confirms. Not held. | §6 wording was written for closed periods | **Yes**: hold until the period opens, or post to the open period? |
| A-24 | One file holding more than one invoice | Hold OTHER: the text layer shows two different invoice numbers. Ask for the file to be split so each bill is checked on its own. | §11; no policy text | Optional |
| A-25 | Damaged file that cannot be opened | Hold OTHER ("ask the vendor to resend"); never sent to the model; the rest of the batch continues. | §11 | No |

## Draft email (send before building, answers within one business day)

> Hi team — a few quick confirmations on the AP exercise:
> 1. When a pay app is dated in a closed period, should DUE_DATE still be computed from the printed bill date (we assume yes) while GL_POSTING_DATE moves to 10/01?
> 2. Preferred format for Entrata "Post Month" — `10/2026`, `Oct 2026`, or `10/01/2026`?
> 3. If a pay app references a subcontract not in the package, should we hold (we'd use OTHER → PM) or code from history?
> 4. For corporate vendors with no Owner Dept (e.g. office supplies), which department and entity should we default to?
> 6. A bill dated in a future period (November while October is open): hold until November opens, or post to 10/01 as §6 literally says?
> 5. If a subcontractor sends the conditional lien waiver separately from the pay application, does a matching waiver on file satisfy the requirement (we assume yes)?
