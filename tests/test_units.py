from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal as D

import pytest

from ap_automation.coding import prorate, split_by_pct
from ap_automation.dedupe import norm_bill_no, numeric_core, split_revision
from ap_automation.refdocs import find_references
from ap_automation.util import money


@pytest.mark.parametrize("raw,norm", [
    ("INV-20417", "20417"), ("20417", "20417"), ("inv 00123", "123"), ("Invoice #0042", "42"), ("GCP-0303", "GCP0303"),
    ("CM-PBS-604102", "CMPBS604102"), ("NOVA-1", "NOVA1"), ("No. 555", "555"), ("SFG-2410-05", "SFG241005"),
])
def test_norm_bill_no(raw, norm):
    assert norm_bill_no(raw) == norm


def test_numeric_core():
    assert numeric_core("INV-00417") == numeric_core("417") == "417"


@pytest.mark.parametrize("raw,base,rev", [("INV-123-R1", "INV-123", "R1"), ("55700-R1", "55700", "R1"), ("HPA-31877", "HPA-31877", ""),
                                          ("CSS-88611 REV2", "CSS-88611", "REV2"), ("R1", "R1", "")])
def test_split_revision(raw, base, rev):
    assert split_revision(raw) == (base, rev)


def test_prorate_penny_goes_to_largest_line():
    # 10.00 over three equal-ish lines: 3.33 + 3.33 + 3.33 = 9.99 → the extra cent lands on the largest weight
    assert prorate(D("10.00"), [D("100"), D("100.01"), D("99.99")]) == [D("3.33"), D("3.34"), D("3.33")]
    assert sum(prorate(D("147.55"), [D("1211.11"), D("633.32"), D("0.01")])) == D("147.55")


def test_allocation_rounding_to_hcm():
    split = split_by_pct(D("100.01"), OrderedDict([("HCM", D("0.4")), ("HPC", D("0.35")), ("HPM", D("0.25"))]), "HCM")
    assert sum(split.values()) == D("100.01")
    assert split["HPC"] == D("35.00") and split["HPM"] == D("25.00") and split["HCM"] == D("40.01")


def test_money_parsing():
    assert money("(2,160.00)") == D("-2160.00") and money(1118.67) == D("1118.67") and money("$1,240") == D("1240.00")


def test_find_references():
    assert find_references("Subcontract SC2410315-03") == ["SC2410315-03"]
    assert find_references("Order Form OF-2024-0332", "PO 2410315-008") == ["OF-2024-0332", "PO2410315-008"]
    assert find_references("SA-PGSIM-2026") == ["SA-PGSIM-2026"]


def test_bill_to_entity_outside_intacct_and_entrata(make_cfg, tmp_path):
    """Entities tab: OZF1 pays through Juniper Square. Without a project tying the bill elsewhere, hold for a person."""
    import json
    import shutil

    from conftest import B1, LABELS, by_file, codes
    from ap_automation.engine import run

    inbox, lab = tmp_path / "inbox", tmp_path / "labels"
    inbox.mkdir(), lab.mkdir()
    for stem in ("APINBOX_0002", "APINBOX_0014"):  # corporate (no project) and construction (PO identifies the project)
        shutil.copy(B1 / f"{stem}.pdf", inbox)
        d = json.loads((LABELS[0] / f"{stem}.json").read_text())
        d["bill_to_name"], d["bill_to_block"] = "Hillpointe Opportunity Zone Fund I, LP", "Hillpointe Opportunity Zone Fund I, LP"
        (lab / f"{stem}.json").write_text(json.dumps(d))
    rr = by_file(run(make_cfg(), inbox, mode="labels", labels_dirs=[lab, *LABELS]))
    corp, cons = rr["APINBOX_0002.pdf"], rr["APINBOX_0014.pdf"]
    assert corp.decision == "HELD" and codes(corp) == ["OTHER"] and "Juniper Square" in corp.holds[0].message
    assert cons.decision == "ENTERED" and any("Bill-to correction" in f.message for f in cons.infos)
