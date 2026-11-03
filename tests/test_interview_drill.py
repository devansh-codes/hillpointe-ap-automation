"""Interview-day drill pack (tests/synthetic/generate_drill.py): 33 blind documents of every kind, processed on top of
Batch 01 + Batch 02. Hand labels stand in for the model so this checks the rules, not the reading."""
from __future__ import annotations

import sys

import pytest

from conftest import B1, B2, LABELS, codes, run_labels
from ap_automation.config import ROOT

sys.path.insert(0, str(ROOT / "tests/synthetic"))
from generate_drill import EXPECTED, LABELS as DRILL_LABELS, OUT  # noqa: E402


@pytest.fixture(scope="module")
def drill(tmp_path_factory):
    from ap_automation.config import load_config

    tmp = tmp_path_factory.mktemp("drill")
    cfg = load_config(state_dir=tmp / "state", out_dir=tmp / "out")
    run_labels(cfg, B1)
    run_labels(cfg, B2)
    from ap_automation.engine import run

    return {r.file_name.rsplit(".", 1)[0]: r for r in run(cfg, OUT, mode="labels", labels_dirs=[DRILL_LABELS, *LABELS]).results}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_drill_outcome(drill, name):
    r = drill[name]
    assert (r.decision, sorted(codes(r))) == (EXPECTED[name][0], sorted(EXPECTED[name][1])), [f.message for f in r.findings]


def test_drill_details(drill):
    assert "APINBOX_0101" in drill["APINBOX_0118"].findings[0].message  # same file twice: points at the first copy
    assert "CSS-88920" in drill["APINBOX_0126"].findings[0].message and "CSS-88921" in drill["APINBOX_0126"].findings[0].message
    assert str(drill["APINBOX_0110"].bill.gl_posting_date) == "2026-10-01"
    assert any(f.code == "WARN" and "future period" in f.message for f in drill["APINBOX_0111"].findings)
    assert drill["APINBOX_0108"].bill.doc_type == "Adjustment"
    assert "damaged" in drill["APINBOX_0133"].findings[0].message


@pytest.mark.parametrize("text, n", [
    ("Invoice No. CSS-88920\n...\nInvoice No. CSS-88921", 2),                                   # two invoices in one file
    ("Credit Memo No. CM-PBS-700001\nApplies to Invoice No. PBS-603977", 1),                   # credit naming its original
    ("Invoice No: HPA-40001-R1\nThis replaces Invoice No. HPA-40001", 1),                     # revision naming its original
    ("Invoice No. 55801\nPrevious balance: Invoice No. 55388", 1),                            # statement-style mention
    ("Invoice No. 55801\nPlease reference invoice number on your remittance", 1),             # footer phrase
])
def test_more_than_one_invoice_detection(text, n):
    from ap_automation.dedupe import norm_bill_no
    from ap_automation.rules.core import _INVOICE_NO

    assert len({norm_bill_no(m) for m in _INVOICE_NO.findall(text)}) == n
