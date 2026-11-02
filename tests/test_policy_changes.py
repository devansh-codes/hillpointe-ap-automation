"""Live-session rule-change drills (PLAN §8.4): each change is ONE config edit and changes only what it should."""
from __future__ import annotations

from datetime import date

import pytest

from ap_automation.config import PolicyError, load_config, validate_policy
from conftest import B1, D, by_file, codes, run_labels


def test_overpo_tolerance_raised_enters_0001(make_cfg):
    r = by_file(run_labels(make_cfg(overpo__tolerance=1500), B1))
    assert r["APINBOX_0001.pdf"].decision == "ENTERED"


def test_overpo_tolerance_250_keeps_0001_held(make_cfg):
    r = by_file(run_labels(make_cfg(overpo__tolerance=250), B1))
    assert codes(r["APINBOX_0001.pdf"]) == ["OVERPO"]


def test_net45_for_one_vendor(make_cfg):
    cfg = make_cfg(vendor_overrides={"V1003": {"terms": "Net 45"}})
    b = by_file(run_labels(cfg, B1))["APINBOX_0005.pdf"].bill
    assert b.term_name == "Net 45" and b.due_date == date(2026, 11, 15)


def test_vp_threshold_lowered(make_cfg):
    cfg = make_cfg()
    cfg.policy["approvals"]["construction"]["additional"]["when_gross_work_over"] = 5000
    r = by_file(run_labels(cfg, B1))
    assert any("VP Construction" in a for a in r["APINBOX_0010.pdf"].approvers)


def test_rpm_threshold_lowered(make_cfg):
    cfg = make_cfg()
    cfg.policy["approvals"]["stabilized"]["additional"]["when_invoice_over"] = 1000
    assert any("Regional Property Manager" in a for a in by_file(run_labels(cfg, B1))["APINBOX_0008.pdf"].approvers)


def test_open_period_override_moves_posting_date(make_cfg):
    cfg = make_cfg(periods={"open_period_override": "2026-11"})
    b = by_file(run_labels(cfg, B1))["APINBOX_0010.pdf"].bill
    assert b.gl_posting_date == date(2026, 11, 1) and b.bill_date == date(2026, 10, 5)


def test_coi_grace_period_releases_coi_only(make_cfg):
    r = by_file(run_labels(make_cfg(coi={"grace_days": 30}), B1))["APINBOX_0013.pdf"]
    assert codes(r) == ["LIEN"]


def test_disable_a_rule(make_cfg):
    cfg = make_cfg()
    cfg.policy["rules"] = [x for x in cfg.policy["rules"] if x != "coi"]
    assert codes(by_file(run_labels(cfg, B1))["APINBOX_0013.pdf"]) == ["LIEN"]


def test_exception_route_change(make_cfg):
    cfg = make_cfg()
    cfg.policy["exception_codes"]["DUP"]["route"] = "AP Supervisor"
    rr = run_labels(cfg, B1)
    text = (rr.out_dir / "exception_log.csv").read_text()
    assert "AP Supervisor" in text


def test_new_rule_from_template(make_cfg):
    from ap_automation.rules import RULES
    import ap_automation.rules._TEMPLATE  # noqa: F401  registers example_corporate_needs_po

    cfg = make_cfg(example={"corporate_po_over": 1000})
    cfg.policy["rules"].append("example_corporate_needs_po")
    assert "example_corporate_needs_po" in RULES
    r = by_file(run_labels(cfg, B1))["APINBOX_0002.pdf"]
    assert r.decision == "ENTERED"  # LedgerLoop has an order form reference, so the new rule passes it


def test_validate_rejects_bad_edits():
    cfg = load_config()
    bad = dict(cfg.policy, overpo={"tolerance": "five hundred"})
    with pytest.raises(PolicyError, match="overpo.tolerance"):
        validate_policy(bad)
    bad = dict(cfg.policy, rules=cfg.policy["rules"] + ["no_such_rule"])
    with pytest.raises(PolicyError, match="unknown rule"):
        validate_policy(bad)
    bad = dict(cfg.policy, dup=dict(cfg.policy["dup"], strip_prefixes=["INV", False]))
    with pytest.raises(PolicyError, match="quoted"):
        validate_policy(bad)
