"""Generalisation: unseen synthetic documents (tests/synthetic/generate.py), run after Batch 01 + Batch 02.

Each scenario declares its expected (decision, hold codes). This is the closest stand-in for the live session's
"invoices you have not seen": new vendors' layouts, file formats, revisions, returns, fraud signals, edge amounts.
"""
from __future__ import annotations

from datetime import date

import pytest

from conftest import B1, B2, D, by_file, codes, lines, run_labels
from ap_automation.config import ROOT

import sys
sys.path.insert(0, str(ROOT / "tests/synthetic"))
from generate import A, B  # noqa: E402

HA, HB = ROOT / "tests/synthetic/holdout_A", ROOT / "tests/synthetic/holdout_B"


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    from ap_automation.config import load_config

    tmp = tmp_path_factory.mktemp("holdout")
    cfg = load_config(state_dir=tmp / "state", out_dir=tmp / "out")
    out = {}
    for name, inbox in (("b1", B1), ("b2", B2), ("A", HA), ("B", HB)):
        out[name] = run_labels(cfg, inbox)
    return cfg, out


def _find(rr, stem):
    return next(r for r in rr.results if r.file_name.startswith(stem))


@pytest.mark.parametrize("stem", sorted(A))
def test_holdout_A(runs, stem):
    _, out = runs
    r = _find(out["A"], stem)
    want_decision, want_codes = A[stem][1]
    assert (r.decision, sorted(codes(r))) == (want_decision, sorted(want_codes)), (r.findings, r.trace)


@pytest.mark.parametrize("stem", sorted(B))
def test_holdout_B(runs, stem):
    _, out = runs
    r = _find(out["B"], stem)
    want_decision, want_codes = B[stem][1]
    assert (r.decision, sorted(codes(r))) == (want_decision, sorted(want_codes)), (r.findings, r.trace)


def test_unsupported_file_is_held_not_crashed(runs):
    r = _find(runs[1]["A"], "SYN_A16")
    assert r.decision == "HELD" and codes(r) == ["OTHER"] and "unsupported" in r.findings[0].message


def test_inactive_vendor_resolves_to_surviving_record(runs):
    r = _find(runs[1]["A"], "SYN_A01")
    assert r.vendor_id == "V1002" and r.confidence == "Medium" and "V1092" in r.confidence_reason


def test_keystone_entrata_with_rpm(runs):
    r = _find(runs[1]["A"], "SYN_A03")
    assert [(e.owner_entity, e.project_id, e.entrata_gl, e.amount) for e in r.entrata_rows] == [("STQOZB", "231138", "6300-0160", D("5600.00"))]
    assert any("Regional Property Manager" in a for a in r.approvers)


def test_within_tolerance_is_noted(runs):
    r = _find(runs[1]["A"], "SYN_A05")
    assert any(f.code == "INFO" and "within the $500 tolerance" in f.message for f in r.findings)


def test_scanned_png_is_medium_confidence_and_coded(runs):
    r = _find(runs[1]["A"], "SYN_A12")
    assert r.confidence == "Medium" and r.entrata_rows[0].entrata_gl == "6300-0145"


def test_docx_software_allocation(runs):
    r = _find(runs[1]["A"], "SYN_A13")
    assert [(l.location_id, l.acct_no, l.amount) for l in r.bill.lines] == [
        ("HCM", "66025", D("1452.90")), ("HPC", "66025", D("1271.29")), ("HPM", "66025", D("908.06")), ("HCM", "65010", D("350.00"))]


def test_price_variance_warns(runs):
    r = _find(runs[1]["A"], "SYN_A09")
    assert any(f.code == "WARN" and "43.00" in f.message for f in r.findings)


def test_credit_without_original_is_medium(runs):
    r = _find(runs[1]["A"], "SYN_A10")
    assert r.bill.doc_type == "Adjustment" and r.confidence == "Medium" and r.bill.total == D("-378.00")


def test_arithmetic_failure_is_low_confidence(runs):
    assert _find(runs[1]["A"], "SYN_A15").confidence == "Low"


def test_corrected_sterling_splits_two_entrata_rows(runs):
    r = _find(runs[1]["A"], "SYN_A20")
    assert [(e.entrata_gl, e.amount) for e in r.entrata_rows] == [("6200-0055", D("3150.00")), ("6200-0075", D("700.00"))]
    assert r.returns  # linked to the held APINBOX_0006


def test_waiver_on_file_clears_lien_but_coi_still_holds(runs):
    r = _find(runs[1]["B"], "SYN_B01")
    assert codes(r) == ["COI"] and any(f.code == "INFO" and "received separately" in f.message for f in r.findings)


def test_revised_payapp_entered_and_supersedes_original(runs):
    r = _find(runs[1]["B"], "SYN_B02")
    assert r.supersedes and lines(r) == [("51000", "HPC", "OPS", "2410315", "06100", "S", D("96200.00")),
                                         ("20500", "HPC", "OPS", "2410315", "06100", "S", D("-9620.00"))]
    assert not any("VP Construction" in a for a in r.approvers)
    assert r.bill.gl_posting_date == date(2026, 10, 1)
