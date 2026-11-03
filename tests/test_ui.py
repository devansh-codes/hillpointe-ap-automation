"""Web UI (`ap ui`): the API is a thin layer over the engine, so it must give the same answers as the CLI."""
from __future__ import annotations

import shutil
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import B1, LABELS, run_labels
from ap_automation.config import ROOT, load_config
from ap_automation.ui import server


@pytest.fixture
def client(make_cfg, tmp_path, monkeypatch):
    cfg = make_cfg()
    policy = tmp_path / "policy.yaml"
    shutil.copyfile(ROOT / "config/policy.yaml", policy)

    def fake_cfg(**kw):
        kw.setdefault("state_dir", cfg.state_dir)
        kw.setdefault("out_dir", cfg.output_dir)
        kw.setdefault("policy_path", policy)
        return load_config(**kw)

    monkeypatch.setattr(server, "_cfg", fake_cfg)
    monkeypatch.setattr(server, "POLICY", policy)
    monkeypatch.setattr(server, "RUN_KW", {"mode": "labels", "labels_dirs": LABELS})
    run_labels(cfg, B1)
    return TestClient(server.app), policy


def _wait(c, job):
    for _ in range(200):
        j = c.get(f"/api/jobs/{job['id']}").json()
        if j["status"] != "running":
            assert j["status"] == "done", j["error"]
            return j["result"]
        time.sleep(0.05)
    raise TimeoutError


def test_every_knob_edits_policy_text_without_losing_comments():
    text = (ROOT / "config/policy.yaml").read_text()
    new_values = {"number": 12345, "choice": None, "bool": False, "text": "2026-11"}
    for k in server.KNOBS:
        v = new_values[k["type"]] if k["type"] != "choice" else k["options"][-1]
        out = server.set_policy_value(text, k["path"], v)
        assert server._get(yaml.safe_load(out), k["path"]) == v, k["path"]
        assert out.count("#") == text.count("#") and len(out.splitlines()) == len(text.splitlines())


def test_runs_exceptions_and_document_source(client):
    c, _ = client
    runs = c.get("/api/runs").json()
    assert len(runs) == 1 and runs[0]["summary"]["by_decision"]["ENTERED"]["count"] == 6
    run_id = runs[0]["run_id"]
    exc = c.get("/api/exceptions").json()
    assert {e["file_name"] for e in exc} >= {"APINBOX_0001.pdf", "APINBOX_0006.pdf"} and len(exc) == 8
    assert all(e["findings"] for e in exc)
    assert c.get(f"/api/source/{run_id}/APINBOX_0001.pdf").headers["content-type"] == "application/pdf"
    assert c.get(f"/api/source/{run_id}/..%2F..%2Fpyproject.toml").status_code == 404
    assert c.get(f"/api/runs/{run_id}/file/..%2Fdecisions.jsonl").status_code == 404
    assert c.post("/api/run", json={"inbox": "../../"}).status_code == 400
    hits = c.get("/api/search", params={"q": "OVERPO"}).json()
    assert [h["file_name"] for h in hits] == ["APINBOX_0001.pdf"]


def test_rule_change_preview_then_save_and_apply(client):
    c, policy = client
    before = policy.read_text()
    d = c.post("/api/policy/draft", json={"changes": {"overpo.tolerance": 1500}}).json()
    assert d["ok"]
    res = _wait(c, c.post("/api/preview", json={"inbox": "01_Invoice_Batch_01", "policy_text": d["text"]}).json())
    assert [(x["file_name"], x["before"], x["after"]) for x in res["changes"]] == [("APINBOX_0001.pdf", "HELD OVERPO", "ENTERED")]
    assert policy.read_text() == before  # preview never saves
    assert len(c.get("/api/ledger").json()["runs"]) == 1  # ...and never records

    assert c.put("/api/policy", json={"text": "overpo: {tolerance: -1}"}).status_code == 400
    assert c.put("/api/policy", json={"text": d["text"]}).json()["ok"]
    res = _wait(c, c.post("/api/apply", json={"inbox": "01_Invoice_Batch_01"}).json())
    assert [x["file_name"] for x in res["changes"]] == ["APINBOX_0001.pdf"]
    hist = c.get("/api/policy").json()["history"]
    assert c.post(f"/api/policy/revert/{hist[0]['name']}").json()["ok"] and policy.read_text() == before


def test_upload_accepts_a_folder_or_zip_and_flattens_it(tmp_path, monkeypatch):
    import io
    import zipfile

    monkeypatch.setattr(server, "ROOT", tmp_path)
    c = TestClient(server.app)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("scans/inv-9.pdf", b"%PDF-z")
        z.writestr("__MACOSX/scans/._inv-9.pdf", b"junk")
        z.writestr("../../escape.pdf", b"%PDF-e")
    files = [("files", ("Nov/inv-1.pdf", b"%PDF-1")), ("files", ("Nov/vendorB/inv-1.pdf", b"%PDF-2")),
             ("files", ("Nov/.DS_Store", b"x")), ("files", ("Nov/Thumbs.db", b"x")), ("files", ("more.zip", buf.getvalue()))]
    res = c.post("/api/upload", files=files, data={"name": "Nov"}).json()
    inbox = tmp_path / res["path"]
    assert sorted(res["files"]) == ["inv-1.pdf", "inv-1_1.pdf", "inv-9.pdf"]  # "../" entries are dropped
    assert sorted(p.name for p in inbox.iterdir()) == sorted(res["files"]) and not (tmp_path / "escape.pdf").exists()
    assert c.post("/api/upload", files=[("files", (".DS_Store", b"x"))]).status_code == 400


def test_delete_run_needs_typed_confirmation_and_latest_only(client):
    c, _ = client
    b1 = c.get("/api/runs").json()[0]["run_id"]
    _wait(c, c.post("/api/run", json={"inbox": "07_Invoice_Batch_02_Rerun"}).json())
    b2 = c.get("/api/runs").json()[0]["run_id"]
    assert c.get(f"/api/runs/{b1}/delete-impact").json()["later_runs"] == [b2]
    assert c.request("DELETE", f"/api/runs/{b1}", json={"confirm": "DELETE"}).status_code == 409
    assert c.request("DELETE", f"/api/runs/{b2}", json={"confirm": "yes"}).status_code == 400
    assert c.request("DELETE", f"/api/runs/{b2}", json={"confirm": "DELETE"}).json()["ledger_snapshot"] == f"before-delete-{b2}"
    assert [r["run_id"] for r in c.get("/api/runs").json()] == [b1]
    assert c.request("DELETE", f"/api/runs/{b1}", json={"confirm": "DELETE"}).status_code == 200
