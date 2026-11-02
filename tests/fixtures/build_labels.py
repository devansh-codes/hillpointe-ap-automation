"""Hand-labelled ground truth for every document in the package, transcribed from the PDFs.

Used for (1) end-to-end tests without an API key and (2) `ap eval-extraction`, which scores the
model's extraction against these labels. Regenerate with: uv run python tests/fixtures/build_labels.py
"""
import json
from pathlib import Path

from ap_automation.models import ExtractedDocument

OUT = Path(__file__).parent / "labels"
HPC_BILLTO = {"bill_to_name": "Hillpointe Construction, LLC",
              "bill_to_block": "Hillpointe Construction, LLC\nAttn: Accounts Payable\n631 W Morse Blvd, Suite 200\nWinter Park, FL 32789"}

REFS = {
    "PO2410315-008": dict(doc_kind="purchase_order", document_number="PO2410315-008", document_date="2026-06-20", vendor_name="Pinecrest Building Supply Co",
                          vendor_id_printed="V1004", ref_project_text="2410315 Pointe Grand Columbia", ref_status="Open", ref_total=180000,
                          ref_lines=[dict(line_no="1", description="Framing lumber package (studs, plates, joists, sheathing), delivered in phases",
                                          cost_code="06100", cost_type="M", pricing="Lump sum, billed per delivery", amount=180000)]),
    "PO2410315-011": dict(doc_kind="purchase_order", document_number="PO2410315-011", document_date="2026-03-02", vendor_name="Coastal Site Services LLC",
                          vendor_id_printed="V1003", ref_project_text="2410315 Pointe Grand Columbia", ref_status="Open", ref_total=18000,
                          ref_lines=[dict(line_no="1", description="Portable restrooms (6) and handwash stations (2), weekly service", cost_code="01540",
                                          cost_type="O", pricing="$1,240.00 per month", unit_rate=1240, amount=18000)]),
    "PO2410315-014": dict(doc_kind="purchase_order", document_number="PO2410315-014", document_date="2026-08-25", vendor_name="Ridgeway Equipment Rental Inc",
                          vendor_id_printed="V1002", ref_project_text="2410315 Pointe Grand Columbia", ref_status="Open", ref_total=25000,
                          ref_lines=[dict(line_no="1", description="Telehandler, 10,000 lb class, incl. delivery and pickup (framing scope)", cost_code="06100",
                                          cost_type="E", pricing="Rate per rental agreement", amount=15000),
                                     dict(line_no="2", description="Scissor lift, 19 ft electric, incl. delivery and pickup (drywall scope)", cost_code="09250",
                                          cost_type="E", pricing="Rate per rental agreement", amount=10000)]),
    "PO2410315-019": dict(doc_kind="purchase_order", document_number="PO2410315-019", document_date="2026-05-11", vendor_name="Harbor Point Aggregates LLC",
                          vendor_id_printed="V1009", ref_project_text="2410315 Pointe Grand Columbia", ref_status="Open", ref_total=52000,
                          ref_lines=[dict(line_no="1", description="Crushed aggregate base, delivered", cost_code="31230", cost_type="M",
                                          pricing="$41.10 per ton plus tax", unit_rate=41.10, amount=52000)]),
    "PO241088-009": dict(doc_kind="purchase_order", document_number="PO241088-009", document_date="2026-09-14", vendor_name="Coastal Site Services LLC",
                         vendor_id_printed="V1003", ref_project_text="241088 Pointe Grand Kingsland East", ref_status="Open", ref_total=8000,
                         ref_lines=[dict(line_no="1", description="Temporary chain link fence panels, install, monthly rental, removal", cost_code="01560",
                                         cost_type="O", pricing="$2,180.00 per month", unit_rate=2180, amount=8000)]),
    "PO241088-022": dict(doc_kind="purchase_order", document_number="PO241088-022", document_date="2026-08-04", vendor_name="Harbor Point Aggregates LLC",
                         vendor_id_printed="V1009", ref_project_text="241088 Pointe Grand Kingsland East", ref_status="Open", ref_total=40000,
                         ref_lines=[dict(line_no="1", description="Crushed aggregate base, delivered", cost_code="31230", cost_type="M",
                                         pricing="$38.40 per ton plus tax", unit_rate=38.40, amount=40000)]),
    "PO241088-031": dict(doc_kind="purchase_order", document_number="PO241088-031", document_date="2026-08-18", vendor_name="Copperline Plumbing Supply Inc",
                         vendor_id_printed="V1007", ref_project_text="241088 Pointe Grand Kingsland East", ref_status="Open", ref_total=20000,
                         ref_lines=[dict(line_no="1", description="PEX tubing, fittings, valves, supports for rough plumbing", cost_code="22000",
                                         cost_type="M", pricing="Per quote Q-88310", amount=20000)]),
    "SA-PGATH-2026_Service_Agreement": dict(doc_kind="service_agreement", document_number="SA-PGATH-2026", vendor_name="Magnolia Pool Services LLC",
                                            vendor_id_printed="V1012", ref_project_text="310522 Pointe Grand Athens", monthly_fee=1475,
                                            term_start="2026-01-01", term_end="2026-12-31",
                                            ref_lines=[dict(description="Pool and spa maintenance, weekly service and chemicals", amount=1475)]),
    "SA-PGSIM-2026_Service_Agreement": dict(doc_kind="service_agreement", document_number="SA-PGSIM-2026", vendor_name="Sterling Grounds and Pest LLC",
                                            vendor_id_printed="V1011", ref_project_text="3206040 Pointe Grand Simpsonville", monthly_fee=3850,
                                            term_start="2026-01-01", term_end="2026-12-31",
                                            ref_lines=[dict(description="Grounds maintenance", amount=3150), dict(description="Monthly pest service", amount=700)]),
    "SC2410315-03_Excerpt": dict(doc_kind="subcontract", document_number="SC2410315-03", document_date="2026-05-01", vendor_name="Gulfline Concrete Partners LLC",
                                 vendor_id_printed="V1001", ref_project_text="2410315 Pointe Grand Columbia", original_contract_sum=612000, ref_total=612000,
                                 ref_lines=[dict(line_no="1", description="Cast in place concrete: building slabs, Buildings 1 through 6", cost_code="03300",
                                                 cost_type="S", amount=612000)],
                                 change_orders=[dict(co_id="CO1", description="Thickened slab edges, Bldg 6, RFI 044", status_text="Executed", executed=True, amount=0)]),
    "SC2410315-06_Excerpt": dict(doc_kind="subcontract", document_number="SC2410315-06", document_date="2026-05-20", vendor_name="Summit Framing Group LLC",
                                 vendor_id_printed="V1005", ref_project_text="2410315 Pointe Grand Columbia", original_contract_sum=884000, ref_total=884000,
                                 ref_lines=[dict(line_no="1", description="Rough carpentry and framing labor, Buildings 1 through 6", cost_code="06100",
                                                 cost_type="S", amount=884000)],
                                 change_orders=[dict(co_id="CO1", description="Added corridor fire blocking", status_text="Executed", executed=True, amount=22500),
                                                dict(co_id="CO2", description="Cabinet and grab bar blocking", status_text="Pending, not executed", executed=False, amount=18400)]),
    "SC2410315-09_Excerpt": dict(doc_kind="subcontract", document_number="SC2410315-09", document_date="2026-07-01", vendor_name="Tri County Drywall Inc",
                                 vendor_id_printed="V1010", ref_project_text="2410315 Pointe Grand Columbia", original_contract_sum=458000, ref_total=458000,
                                 ref_lines=[dict(line_no="1", description="Gypsum drywall hang, tape and finish, Buildings 1 through 6", cost_code="09250",
                                                 cost_type="S", amount=458000)]),
}

GCP_0303 = dict(
    doc_kind="pay_application", vendor_name="Gulfline Concrete Partners LLC", vendor_address="PO Box 4410, West Columbia, SC 29171",
    vendor_phone="(803) 555-0141", vendor_email="ar@gulflineconcrete.example", remit_to="Remit to address on file", **HPC_BILLTO,
    ship_to_or_project_text="Pointe Grand Columbia, Columbia, SC", document_number="GCP-0303", document_date="2026-09-30", printed_terms="Net 30",
    customer_ref_raw="Subcontract SC2410315-03", references=["SC2410315-03"], total=133650,
    pay_application=dict(application_no="3", period_start="2026-09-01", period_end="2026-09-30", original_contract_sum=612000,
                         net_change_by_change_orders=0, contract_sum_to_date=612000, total_completed_to_date=352500, retainage_percent=10,
                         retainage_to_date=35250, total_earned_less_retainage=317250, previous_certificates=183600, current_payment_due=133650,
                         lines_this_period=[dict(description="Building 2 slab on grade", work_this_period=74250, retainage_this_period=7425),
                                            dict(description="Building 3 slab on grade", work_this_period=74250, retainage_this_period=7425)]),
    lien_waiver=dict(present_in_document=True, waiver_type="conditional", payment_kind="progress", claimant="Gulfline Concrete Partners LLC",
                     project="Pointe Grand Columbia, Columbia, SC", amount=133650, through_date="2026-09-30"),
    notes=["Conditional waiver and release on progress payment attached.", "Remit to address on file. Thank you for your business."])

RER_77310 = dict(
    doc_kind="invoice", vendor_name="Ridgeway Equipment Rental Inc", vendor_address="2280 Augusta Rd, Lexington, SC 29072", vendor_phone="(803) 555-0177",
    remit_to="Ridgeway Equipment Rental Inc, 2280 Augusta Rd, Lexington, SC 29072", **HPC_BILLTO,
    ship_to_or_project_text="Pointe Grand Columbia jobsite, Columbia, SC", document_number="RER-77310", document_date="2026-10-05", printed_terms="Net 30",
    customer_ref_raw="PO2410315-014", references=["PO2410315-014"], service_period_start="2026-09-08", service_period_end="2026-10-05",
    line_items=[dict(description="Telehandler 10K lb, 4 week rate (09/08/2026 to 10/05/2026), Unit TH-1142", quantity=1, unit="4WK", unit_price=4850, amount=4850),
                dict(description="Delivery and pickup, telehandler", quantity=1, unit="EA", unit_price=350, amount=350, is_freight_or_delivery=True),
                dict(description="Scissor lift 19 ft electric, 4 week rate (09/08/2026 to 10/05/2026), Unit SL-0387", quantity=1, unit="4WK", unit_price=1120, amount=1120),
                dict(description="Delivery and pickup, scissor lift", quantity=1, unit="EA", unit_price=225, amount=225, is_freight_or_delivery=True)],
    subtotal=6545, tax_lines=[dict(label="SC sales tax 6% + Richland local 2%", rate_percent=8, amount=523.60)], total=7068.60,
    notes=["Damage waiver declined per customer.", "Rental agreement RA-55120 on file."])

CSS_88502 = dict(
    doc_kind="invoice", vendor_name="Coastal Site Services LLC", vendor_address="1190 Louisville Rd, Savannah, GA 31415", vendor_phone="(912) 555-0122",
    remit_to="Coastal Site Services LLC, 1190 Louisville Rd, Savannah, GA 31415", **HPC_BILLTO, ship_to_or_project_text="Pointe Grand Columbia",
    document_number="CSS-88502", document_date="2026-10-01", printed_terms="Due upon receipt", customer_ref_raw="PO2410315-011", references=["PO2410315-011"],
    service_period_start="2026-10-01", service_period_end="2026-10-31",
    line_items=[dict(description="Portable restroom, weekly service, October 2026", quantity=6, unit="EA", unit_price=160, amount=960),
                dict(description="Handwash station, weekly service, October 2026", quantity=2, unit="EA", unit_price=140, amount=280)],
    subtotal=1240, total=1240, notes=["Service period 10/01/2026 to 10/31/2026."])

HPA_31877_BASE = dict(
    doc_kind="invoice", vendor_name="Harbor Point Aggregates LLC", vendor_address="6020 Hwy 17, Richmond Hill, GA 31324", vendor_phone="(912) 555-0148",
    remit_to="Harbor Point Aggregates LLC, 6020 Hwy 17, Richmond Hill, GA 31324", **HPC_BILLTO, document_number="HPA-31877", document_date="2026-10-02",
    printed_terms="Net 30",
    line_items=[dict(description="Crushed aggregate base, delivered. Tickets 77401 to 77429", quantity=412.5, unit="TON", unit_price=38.40, amount=15840)],
    subtotal=15840, tax_lines=[dict(label="Sales tax 7%", rate_percent=7, amount=1108.80)], total=16948.80)

INVOICES = {
    "APINBOX_0001": dict(
        doc_kind="invoice", vendor_name="Pinecrest Building Supply Co", vendor_address="PO Box 9183, Columbia, SC 29290", vendor_phone="(803) 555-0190",
        remit_to="Pinecrest Building Supply Co, PO Box 9183, Columbia, SC 29290", **HPC_BILLTO, ship_to_or_project_text="Pointe Grand Columbia, Bldg 4",
        document_number="PBS-604418", document_date="2026-10-06", printed_terms="Net 30", customer_ref_raw="PO2410315-008", references=["PO2410315-008"],
        line_items=[dict(description="2x6x10 SPF stud", quantity=1800, unit="EA", unit_price=5.42, amount=9756),
                    dict(description="2x6x16 #2 SYP plate", quantity=220, unit="EA", unit_price=9.87, amount=2171.40),
                    dict(description="7/16 in OSB sheathing 4x8", quantity=160, unit="SHT", unit_price=12.85, amount=2056)],
        subtotal=13983.40, tax_lines=[dict(label="SC sales tax 6% + Richland local 2%", rate_percent=8, amount=1118.67)], total=15102.07,
        notes=["Delivery 4 of framing package. Additional quantities per field request from site super."]),
    "APINBOX_0002": dict(
        doc_kind="invoice", vendor_name="LedgerLoop Software Inc", vendor_address="88 Market St, Suite 400, Austin, TX 78701", vendor_email="billing@ledgerloop.example",
        remit_to="LedgerLoop Software Inc, 88 Market St, Suite 400, Austin, TX 78701", bill_to_name="Hillpointe Corporate Management, LLC",
        bill_to_block="Hillpointe Corporate Management, LLC\nAttn: Accounts Payable\n631 W Morse Blvd, Suite 200\nWinter Park, FL 32789",
        document_number="LL-2026-1184", document_date="2026-10-01", printed_terms="Net 30", customer_ref_raw="Order Form OF-2024-0332", references=["OF-2024-0332"],
        service_period_start="2026-10-01", service_period_end="2026-10-31",
        line_items=[dict(description="LedgerLoop Platform subscription, October 2026 (per seat)", quantity=87, unit="SEAT", unit_price=41.75, amount=3632.25),
                    dict(description="Implementation support, report builder configuration", quantity=6, unit="HR", unit_price=175, amount=1050)],
        subtotal=4682.25, total=4682.25, notes=["Seats reflect active users as of 09/30/2026."]),
    "APINBOX_0003": GCP_0303,
    "APINBOX_0004": dict(
        doc_kind="invoice", vendor_name="Brightline Landscape Design LLC", vendor_address="77 Gloucester St, Brunswick, GA 31520", vendor_phone="(912) 555-0131",
        remit_to="Brightline Landscape Design LLC, 77 Gloucester St, Brunswick, GA 31520", bill_to_name="Hillpointe Development",
        bill_to_block="Hillpointe Development\n631 W Morse Blvd, Suite 200\nWinter Park, FL 32789",
        ship_to_or_project_text="Pointe Grand Kingsland East (amenity concept)", document_number="BLD-1007", document_date="2026-10-04", printed_terms="Net 15",
        line_items=[dict(description="Conceptual landscape plan and plant palette, amenity area", quantity=1, unit="LS", unit_price=6500, amount=6500)],
        subtotal=6500, total=6500, notes=["New client. Please send W9 request to the email above.", "Work requested by development team."]),
    "APINBOX_0005": CSS_88502,
    "APINBOX_0006": dict(
        doc_kind="invoice", vendor_name="Sterling Grounds & Pest LLC", vendor_address="9 Commerce Ct, Suite 210, Greenville, SC 29607", vendor_phone="(864) 555-0199",
        vendor_email="accounts@sterling-grounds-pay.example", remit_to="Sterling Grounds & Pest LLC, 9 Commerce Ct, Suite 210, Greenville, SC 29607",
        bank_details_printed="First Lakeside Bank, Routing XXXXX0614, Account ending 9930", payment_instruction_change_requested=True,
        payment_change_quote="IMPORTANT: Our banking information has changed effective immediately. Please update your records and remit all future payments by ACH to: First Lakeside Bank, Routing XXXXX0614, Account ending 9930.",
        bill_to_name="Pointe Grand Simpsonville", bill_to_block="Pointe Grand Simpsonville\nc/o Hillpointe Property Management, LLC\n631 W Morse Blvd, Suite 200\nWinter Park, FL 32789",
        ship_to_or_project_text="Pointe Grand Simpsonville, Simpsonville, SC", document_number="SGP-11092", document_date="2026-10-03", printed_terms="Net 30",
        customer_ref_raw="SA-PGSIM-2026", references=["SA-PGSIM-2026"], service_period_start="2026-10-01", service_period_end="2026-10-31",
        line_items=[dict(description="Grounds maintenance, October 2026", quantity=1, unit="LS", unit_price=3150, amount=3150),
                    dict(description="Monthly pest service, October 2026", quantity=1, unit="LS", unit_price=700, amount=700)],
        subtotal=3850, total=3850, notes=["Payments sent to the old account will be returned."]),
    "APINBOX_0007": dict(
        doc_kind="invoice", vendor_name="Copperline Plumbing Supply Inc", vendor_address="PO Box 2207, Jacksonville, FL 32203", vendor_phone="(904) 555-0158",
        remit_to="Copperline Plumbing Supply Inc, PO Box 2207, Jacksonville, FL 32203", **HPC_BILLTO,
        ship_to_or_project_text="Pointe Grand Kingsland East, Kingsland, GA", document_number="55102", document_date="2026-09-18", printed_terms="Net 30",
        customer_ref_raw="PO241088-031", references=["PO241088-031"],
        line_items=[dict(description="PEX A tubing 1/2 in, 300 ft coil", quantity=10, unit="CL", unit_price=186, amount=1860),
                    dict(description="PEX A tubing 3/4 in, 100 ft coil", quantity=20, unit="CL", unit_price=98, amount=1960),
                    dict(description="Brass fittings assortment per quote Q-88310", quantity=1, unit="LS", unit_price=2423.17, amount=2423.17),
                    dict(description="Ball valve 3/4 in lead free", quantity=48, unit="EA", unit_price=58.75, amount=2820)],
        subtotal=9063.17, tax_lines=[dict(label="GA sales tax 4% + Camden local 3%", rate_percent=7, amount=634.42)], total=9697.59,
        notes=["Delivered 09/17/2026, signed by site super."]),
    "APINBOX_0008": dict(
        doc_kind="invoice", vendor_name="Magnolia Pool Services LLC", vendor_address="210 Prince Ave, Athens, GA 30601", vendor_phone="(706) 555-0119",
        remit_to="Magnolia Pool Services LLC, 210 Prince Ave, Athens, GA 30601", bill_to_name="Pointe Grand Athens",
        bill_to_block="Pointe Grand Athens\nc/o Hillpointe Property Management, LLC\n631 W Morse Blvd, Suite 200\nWinter Park, FL 32789",
        ship_to_or_project_text="Pointe Grand Athens, Athens, GA", document_number="MPS-4471", document_date="2026-10-01", printed_terms="Net 30",
        customer_ref_raw="SA-PGATH-2026", references=["SA-PGATH-2026"], service_period_start="2026-10-01", service_period_end="2026-10-31",
        line_items=[dict(description="Pool and spa maintenance, October 2026, weekly service and chemicals", quantity=1, unit="LS", unit_price=1475, amount=1475)],
        subtotal=1475, total=1475),
    "APINBOX_0009": dict(
        doc_kind="pay_application", vendor_name="Summit Framing Group LLC", vendor_address="415 Columbia Ave, Lexington, SC 29072", vendor_phone="(803) 555-0165",
        **HPC_BILLTO, ship_to_or_project_text="Pointe Grand Columbia", document_number="SFG-2410-05", document_date="2026-09-30", printed_terms="Net 30",
        customer_ref_raw="Subcontract SC2410315-06", references=["SC2410315-06"], total=103140,
        pay_application=dict(application_no="5", period_start="2026-09-01", period_end="2026-09-30", original_contract_sum=884000,
                             net_change_by_change_orders=40900, contract_sum_to_date=924900, total_completed_to_date=626600, retainage_percent=10,
                             retainage_to_date=62660, total_earned_less_retainage=563940, previous_certificates=460800, current_payment_due=103140,
                             change_orders_mentioned=["CO1", "CO2"],
                             lines_this_period=[dict(description="Building 5 wall framing", work_this_period=54600, retainage_this_period=5460),
                                                dict(description="Building 5 roof trusses set", work_this_period=41600, retainage_this_period=4160),
                                                dict(description="Change Order 2: cabinet and grab bar blocking", work_this_period=18400,
                                                     retainage_this_period=1840, change_order_ref="CO2")]),
        notes=["Net change by change orders includes CO1 and CO2."]),
    "APINBOX_0010": RER_77310,
    "APINBOX_0011": dict(
        doc_kind="credit_memo", vendor_name="Pinecrest Building Supply Co", vendor_address="PO Box 9183, Columbia, SC 29290", vendor_phone="(803) 555-0190",
        remit_to="Pinecrest Building Supply Co, PO Box 9183, Columbia, SC 29290", **HPC_BILLTO, ship_to_or_project_text="Pointe Grand Columbia",
        document_number="CM-PBS-604102", document_date="2026-10-02", printed_terms="N/A", customer_ref_raw="PO2410315-008", references=["PO2410315-008"],
        line_items=[dict(description="Return: 2x10x16 #2 SYP joist (original invoice PBS-603977)", quantity=100, unit="EA", unit_price=-20, amount=-2000)],
        subtotal=-2000, tax_lines=[dict(label="SC sales tax 6% + Richland local 2%", rate_percent=8, amount=-160)], total=-2160,
        credit_applies_to_invoice="PBS-603977", notes=["Credit applies to original invoice PBS-603977 dated 09/09/2026."]),
    "APINBOX_0012": dict(**HPA_31877_BASE, ship_to_or_project_text="Hillpointe jobsite", notes=["Customer PO: ______________", "Delivered 09/22/2026 to 09/30/2026."]),
    "APINBOX_0013": dict(
        doc_kind="pay_application", vendor_name="Tri County Drywall Inc", vendor_address="702 Sunset Blvd, West Columbia, SC 29169", vendor_phone="(803) 555-0126",
        **HPC_BILLTO, ship_to_or_project_text="Pointe Grand Columbia", document_number="TCD-2410-02", document_date="2026-09-29", printed_terms="Net 30",
        customer_ref_raw="Subcontract SC2410315-09", references=["SC2410315-09"], total=57600,
        pay_application=dict(application_no="2", period_start="2026-09-01", period_end="2026-09-30", original_contract_sum=458000,
                             net_change_by_change_orders=0, contract_sum_to_date=458000, total_completed_to_date=105000, retainage_percent=10,
                             retainage_to_date=10500, total_earned_less_retainage=94500, previous_certificates=36900, current_payment_due=57600,
                             lines_this_period=[dict(description="Building 1 hang", work_this_period=38000, retainage_this_period=3800),
                                                dict(description="Building 1 tape and finish, partial", work_this_period=26000, retainage_this_period=2600)]),
        lien_waiver=dict(present_in_document=False, stated_to_follow_separately=True),
        notes=["Conditional lien waiver to follow under separate cover."]),
    "APINBOX_0014": dict(
        doc_kind="invoice", vendor_name="Copperline Plumbing Supply Inc", vendor_address="PO Box 2207, Jacksonville, FL 32203", vendor_phone="(904) 555-0158",
        remit_to="Copperline Plumbing Supply Inc, PO Box 2207, Jacksonville, FL 32203", bill_to_name="Hillpointe, LLC",
        bill_to_block="Hillpointe, LLC\nAttn: Accounting\n631 W Morse Blvd, Suite 200\nWinter Park, FL 32789",
        ship_to_or_project_text="Pointe Grand Kingsland East, Kingsland, GA", document_number="55388", document_date="2026-10-07", printed_terms="Net 30",
        customer_ref_raw="PO241088-031", references=["PO241088-031"],
        line_items=[dict(description="PEX A tubing 1/2 in, 300 ft coil", quantity=8, unit="CL", unit_price=186, amount=1488),
                    dict(description="PEX A tubing 3/4 in, 100 ft coil", quantity=15, unit="CL", unit_price=98, amount=1470),
                    dict(description="Pipe supports and clips", quantity=1, unit="LS", unit_price=1195, amount=1195),
                    dict(description="Ball valve 3/4 in lead free", quantity=40, unit="EA", unit_price=58.75, amount=2350),
                    dict(description="Manifold, 8 port", quantity=6, unit="EA", unit_price=175, amount=1050)],
        subtotal=7553, tax_lines=[dict(label="GA sales tax 4% + Camden local 3%", rate_percent=7, amount=528.71)], total=8081.71,
        notes=["Delivered 10/06/2026."]),
    "APINBOX_0015": dict(
        doc_kind="invoice", vendor_name="Ridgeway Equipment Rental Inc", vendor_address="2280 Augusta Rd, Lexington, SC 29072", vendor_phone="(803) 555-0177",
        remit_to="Ridgeway Equipment Rental Inc, 2280 Augusta Rd, Lexington, SC 29072", **HPC_BILLTO,
        ship_to_or_project_text="Pointe Grand Columbia jobsite, Columbia, SC", document_number="INV-20417", document_date="2026-09-12", printed_terms="Net 30",
        customer_ref_raw="PO2410315-014", references=["PO2410315-014"], service_period_start="2026-08-25", service_period_end="2026-09-07",
        line_items=[dict(description="Telehandler 10K lb, 2 week rate (08/25/2026 to 09/07/2026), Unit TH-1142", quantity=1, unit="2WK", unit_price=2650, amount=2650),
                    dict(description="Delivery and pickup, telehandler", quantity=1, unit="EA", unit_price=350, amount=350, is_freight_or_delivery=True)],
        subtotal=3000, tax_lines=[dict(label="SC sales tax 6% + Richland local 2%", rate_percent=8, amount=240)], total=3240,
        notes=["Rental agreement RA-55120 on file."]),
    # ---- Batch 02
    "APINBOX_0016": dict(
        doc_kind="invoice", vendor_name="Coastal Site Services LLC", vendor_address="1190 Louisville Rd, Savannah, GA 31415", vendor_phone="(912) 555-0122",
        remit_to="Coastal Site Services LLC, 1190 Louisville Rd, Savannah, GA 31415", **HPC_BILLTO, ship_to_or_project_text="Pointe Grand Kingsland East",
        document_number="CSS-88611", document_date="2026-10-08", printed_terms="Due upon receipt", customer_ref_raw="PO241088-009", references=["PO241088-009"],
        service_period_start="2026-10-01", service_period_end="2026-10-31",
        line_items=[dict(description="Temporary chain link fence rental, 1,450 LF, October 2026", quantity=1, unit="LS", unit_price=2180, amount=2180)],
        subtotal=2180, total=2180, notes=["Rental period 10/01/2026 to 10/31/2026."]),
    "APINBOX_0017": dict(RER_77310, markings=["REPRINT"]),
    "APINBOX_0018": dict(**HPA_31877_BASE, markings=["REVISED INVOICE"], customer_ref_raw="PO241088-022", references=["PO241088-022"],
                         ship_to_or_project_text="Pointe Grand Kingsland East, Kingsland, GA", replaces_document_number="HPA-31877",
                         notes=["Revised to add customer PO per Hillpointe request. Replaces original invoice HPA-31877.", "Delivered 09/22/2026 to 09/30/2026."]),
    "APINBOX_0019": GCP_0303,
    "APINBOX_0020": dict(CSS_88502, markings=["PAST DUE"]),
}


def main() -> None:
    (OUT / "refs").mkdir(parents=True, exist_ok=True)
    for name, d in REFS.items():
        (OUT / "refs" / f"{name}.json").write_text(ExtractedDocument.model_validate(d).model_dump_json(indent=2))
    for name, d in INVOICES.items():
        (OUT / f"{name}.json").write_text(ExtractedDocument.model_validate(d).model_dump_json(indent=2))
    print(f"wrote {len(REFS)} reference + {len(INVOICES)} invoice labels to {OUT}")


if __name__ == "__main__":
    main()
