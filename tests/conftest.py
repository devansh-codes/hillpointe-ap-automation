from __future__ import annotations

import copy
import os
from decimal import Decimal
from pathlib import Path

import pytest

from ap_automation.config import ROOT, load_config
from ap_automation.engine import run

# Tests never read the real .env (no accidental API calls or spend).
os.environ["AP_NO_DOTENV"] = "1"

LABELS = [ROOT / "tests/fixtures/labels", ROOT / "tests/fixtures/labels/refs", ROOT / "tests/synthetic/labels"]
B1 = ROOT / "01_Invoice_Batch_01"
B2 = ROOT / "07_Invoice_Batch_02_Rerun"


@pytest.fixture
def make_cfg(tmp_path):
    def _make(**policy_overrides):
        cfg = load_config(state_dir=tmp_path / "state", out_dir=tmp_path / "out")
        cfg.policy = copy.deepcopy(cfg.policy)
        for dotted, value in policy_overrides.items():
            node = cfg.policy
            keys = dotted.split("__")
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
        return cfg
    return _make


def run_labels(cfg, inbox: Path, **kw):
    return run(cfg, inbox, mode="labels", labels_dirs=LABELS, **kw)


def by_file(rr) -> dict:
    return {r.file_name: r for r in rr.results}


def codes(r) -> list[str]:
    return [f.code for f in r.holds]


def lines(r) -> list[tuple]:
    return [(l.acct_no, l.location_id, l.department_id, l.project_id, l.task_id, l.cost_type_id, l.amount) for l in r.bill.lines]


D = Decimal
