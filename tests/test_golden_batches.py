"""Golden end-to-end tests: Batch 01 → rerun → Batch 02, asserted against governance/SOURCE_ANALYSIS.md."""
from __future__ import annotations

import csv
import sqlite3
from datetime import date

import pytest

from ap_automation.ledger import Ledger
from conftest import B1, B2, D, by_file, codes, lines, run_labels


@pytest.fixture
def batch1(make_cfg):
    cfg = make_cfg()
    return cfg, run_labels(cfg, B1)


def test_batch01_decisions(batch1):
    _, rr = batch1
    r = by_file(rr)
    entered = {f for f, x in r.items() if x.decision == "ENTERED"}
    assert entered == {"APINBOX_0002.pdf", "APINBOX_0003.pdf", "APINBOX_0005.pdf", "APINBOX_0010.pdf", "APINBOX_0011.pdf", "APINBOX_0014.pdf"}
    assert r["APINBOX_0008.pdf"].decision == "ENTRATA_HANDOFF"
    expected_holds = {
        "APINBOX_0001.pdf": ["OVERPO"], "APINBOX_0004.pdf": ["NEWVEND", "NOPO", "OTHER"], "APINBOX_0006.pdf": ["BANKCHG"],
        "APINBOX_0007.pdf": ["DUP"], "APINBOX_0009.pdf": ["UNAPPCO", "LIEN"], "APINBOX_0012.pdf": ["NOPO"],
        "APINBOX_0013.pdf": ["LIEN", "COI"], "APINBOX_0015.pdf": ["DUP"],
    }
    for f, cs in expected_holds.items():
        assert r[f].decision == "HELD", f
        assert sorted(codes(r[f])) == sorted(cs), (f, codes(r[f]))
    assert all(x.confidence == "High" for x in r.values())


def test_0001_overpo_nets_credit_processed_first(batch1):
    _, rr = batch1
    assert rr.order[0] == "APINBOX_0011.pdf"  # credits first (A-19)
    msg = by_file(rr)["APINBOX_0001.pdf"].holds[0].message
    assert "remaining 13,710.00" in msg and "exceeds it by 1,392.07" in msg


def test_0002_allocation_and_one_time_service(batch1):
    _, rr = batch1
    r = by_file(rr)["APINBOX_0002.pdf"]
    assert lines(r) == [("66025", "HCM", "IT", "", "", "", D("1452.90")), ("66025", "HPC", "IT", "", "", "", D("1271.29")),
                        ("66025", "HPM", "IT", "", "", "", D("908.06")), ("65010", "HCM", "IT", "", "", "", D("1050.00"))]
    assert r.bill.reference_no == "OF-2024-0332" and r.bill.due_date == date(2026, 10, 31)
    assert r.approvers == ["Department head, Information Technology (IT)"]


def test_0003_pay_app_retainage_closed_period(batch1):
    _, rr = batch1
    r = by_file(rr)["APINBOX_0003.pdf"]
    assert lines(r) == [("51000", "HPC", "OPS", "2410315", "03300", "S", D("148500.00")),
                        ("20500", "HPC", "OPS", "2410315", "03300", "S", D("-14850.00"))]
    b = r.bill
    assert (b.bill_date, b.gl_posting_date, b.due_date) == (date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 30))
    assert b.total == D("133650.00")
    assert any("VP Construction" in a for a in r.approvers)


def test_0005_vendor_terms_override_invoice_terms(batch1):
    _, rr = batch1
    b = by_file(rr)["APINBOX_0005.pdf"].bill
    assert b.term_name == "Net 15" and b.due_date == date(2026, 10, 16)
    assert lines(by_file(rr)["APINBOX_0005.pdf"]) == [("54000", "HPC", "OPS", "2410315", "01540", "O", D("1240.00"))]


def test_0010_two_po_lines_tax_prorated(batch1):
    _, rr = batch1
    assert lines(by_file(rr)["APINBOX_0010.pdf"]) == [("53000", "HPC", "OPS", "2410315", "06100", "E", D("5616.00")),
                                                      ("53000", "HPC", "OPS", "2410315", "09250", "E", D("1452.60"))]


def test_0011_credit_is_adjustment(batch1):
    _, rr = batch1
    r = by_file(rr)["APINBOX_0011.pdf"]
    assert r.bill.doc_type == "Adjustment" and r.bill.due_date == r.bill.bill_date
    assert lines(r) == [("50000", "HPC", "OPS", "2410315", "06100", "M", D("-2160.00"))]
    assert "PBS-603977" in r.bill.description
    assert r.approvers == ["AP Manager review"]


def test_0014_billto_correction_and_not_a_cross_vendor_dup(batch1):
    _, rr = batch1
    r = by_file(rr)["APINBOX_0014.pdf"]
    assert r.decision == "ENTERED"
    assert any(f.code == "INFO" and "Bill-to correction" in f.message for f in r.findings)
    assert lines(r) == [("50000", "HPC", "OPS", "241088", "22000", "M", D("8081.71"))]


def test_0015_formatting_drift_dup(batch1):
    _, rr = batch1
    assert "20417" in by_file(rr)["APINBOX_0015.pdf"].holds[0].message


def test_0012_nopo_names_likely_match(batch1):
    _, rr = batch1
    assert "Likely match: PO241088-022" in by_file(rr)["APINBOX_0012.pdf"].holds[0].message


def test_0008_entrata(batch1):
    _, rr = batch1
    rows = by_file(rr)["APINBOX_0008.pdf"].entrata_rows
    assert [(e.property, e.owner_entity, e.project_id, e.entrata_gl, e.amount, e.post_month, e.due_date) for e in rows] == [
        ("Pointe Grand Athens", "PGATH", "310522", "6200-0085", D("1475.00"), "10/2026", date(2026, 10, 31))]


def test_output_files_match_template(batch1):
    cfg, rr = batch1
    with open(rr.out_dir / "intacct_bill_import.csv") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys())[:3] == ["BILL_NO", "DOC_TYPE", "VENDOR_ID"] and len(rows[0]) == 19
    assert len(rows) == 11
    assert sum(D(r["AMOUNT"]) for r in rows) == D("152562.56")
    assert all(r["ACCT_NO"] not in ("20000",) and not r["ACCT_NO"].startswith("250") for r in rows)
    with open(rr.out_dir / "exception_log.csv") as f:
        exc = list(csv.DictReader(f))
    assert len([e for e in exc if e["Decision"] == "HELD"]) == 8
    assert (rr.out_dir / f"AP_Bill_Import_{B1.name}.xlsx").exists() and (rr.out_dir / "run_report.html").exists()


def test_rerun_batch01_is_idempotent(make_cfg):
    cfg = make_cfg()
    run_labels(cfg, B1)
    rr2 = run_labels(cfg, B1)
    r = by_file(rr2)
    assert not [x for x in rr2.results if x.decision in ("ENTERED", "ENTRATA_HANDOFF")]
    assert {f for f, x in r.items() if x.decision == "ALREADY_PROCESSED"} == {
        "APINBOX_0002.pdf", "APINBOX_0003.pdf", "APINBOX_0005.pdf", "APINBOX_0008.pdf", "APINBOX_0010.pdf", "APINBOX_0011.pdf", "APINBOX_0014.pdf"}
    assert sorted(codes(r["APINBOX_0013.pdf"])) == ["COI", "LIEN"]  # held docs re-evaluated, same result
    with open(rr2.out_dir / "intacct_bill_import.csv") as f:
        assert len(list(csv.DictReader(f))) == 0


def test_batch02_after_batch01(make_cfg):
    cfg = make_cfg()
    run_labels(cfg, B1)
    run_labels(cfg, B1)
    rr = run_labels(cfg, B2)
    r = by_file(rr)
    assert r["APINBOX_0016.pdf"].decision == "ENTERED"
    assert lines(r["APINBOX_0016.pdf"]) == [("54000", "HPC", "OPS", "241088", "01560", "O", D("2180.00"))]
    assert r["APINBOX_0016.pdf"].bill.due_date == date(2026, 10, 23)
    assert r["APINBOX_0018.pdf"].decision == "ENTERED"
    assert lines(r["APINBOX_0018.pdf"]) == [("50000", "HPC", "OPS", "241088", "31230", "M", D("16948.80"))]
    assert r["APINBOX_0018.pdf"].supersedes  # links to the held 0012
    for f in ("APINBOX_0017.pdf", "APINBOX_0019.pdf", "APINBOX_0020.pdf"):
        assert codes(r[f]) == ["DUP"], f
    assert "REPRINT" in r["APINBOX_0017.pdf"].holds[0].message and "PAST DUE" in r["APINBOX_0020.pdf"].holds[0].message
    # 0012 is now superseded in the ledger
    con = sqlite3.connect(cfg.state_dir / "ap_ledger.db")
    assert con.execute("SELECT MAX(superseded) FROM documents WHERE file_name='APINBOX_0012.pdf'").fetchone()[0] == 1
    # Nothing entered twice, enforced by the database
    dupes = con.execute("SELECT vendor_id, bill_no_norm, COUNT(*) FROM entered_bills GROUP BY 1,2 HAVING COUNT(*)>1").fetchall()
    assert dupes == []
    assert con.execute("SELECT COUNT(*) FROM entered_bills").fetchone()[0] == 9


def test_rerun_batch02_again_is_idempotent(make_cfg):
    cfg = make_cfg()
    for b in (B1, B2):
        run_labels(cfg, b)
    rr = run_labels(cfg, B2)
    assert not [x for x in rr.results if x.decision in ("ENTERED", "ENTRATA_HANDOFF")]


def test_db_unique_constraint_blocks_double_entry(make_cfg):
    cfg = make_cfg()
    run_labels(cfg, B1)
    con = sqlite3.connect(Ledger(cfg.state_dir).path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO entered_bills (vendor_id, bill_no_norm) VALUES ('V1001', 'GCP0303')")
