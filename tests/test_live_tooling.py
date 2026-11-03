"""Live-session commands: what-if, snapshot/restore, diff, explain, doctor; extraction controls; fault isolation."""
from __future__ import annotations

import os
import json
import shutil
from types import SimpleNamespace

from typer.testing import CliRunner

from ap_automation.cli import app
from ap_automation.extract import CachedExtractor, ClaudeExtractor, ExtractionUnavailable, intake
from ap_automation.ledger import Ledger
from ap_automation.models import ExtractedDocument
import pytest

from conftest import B1, LABELS, by_file, codes, run_labels
from ap_automation.config import ROOT as ROOT_

cli = CliRunner()


def _args(cfg):
    return ["--state-dir", str(cfg.state_dir), "--out-dir", str(cfg.output_dir)] + sum((["--labels", str(p)] for p in LABELS), [])


def test_what_if_does_not_commit(make_cfg):
    cfg = make_cfg()
    rr = run_labels(cfg, B1, what_if=True)
    assert not rr.committed and Ledger(cfg.state_dir).runs() == []
    assert "_whatif" in rr.run_id and (rr.out_dir / "intacct_bill_import.csv").exists()


def test_rule_change_flow_restore_rerun_diff(make_cfg, monkeypatch):
    cfg = make_cfg()
    base = run_labels(cfg, B1)
    assert "pre-01_Invoice_Batch_01" in Ledger(cfg.state_dir).list_snapshots()
    Ledger(cfg.state_dir).restore("pre-01_Invoice_Batch_01")
    cfg.policy["overpo"]["tolerance"] = 1500
    new = run_labels(cfg, B1)
    assert by_file(new)["APINBOX_0001.pdf"].decision == "ENTERED"  # not ALREADY_PROCESSED: the restore worked
    monkeypatch.setattr("ap_automation.cli._cfg", lambda *a, **k: cfg)
    res = cli.invoke(app, ["diff", base.run_id, new.run_id], terminal_width=250)
    assert res.exit_code == 0, res.output
    assert "APINBOX_0001.pdf" in res.output and "OVERPO" in res.output and "1 document(s) changed" in res.output


def test_rerun_keeps_pre_folder_snapshot(make_cfg):
    cfg = make_cfg()
    run_labels(cfg, B1)
    run_labels(cfg, B1)  # rerun must not overwrite pre-<folder> with a ledger that already holds the batch
    Ledger(cfg.state_dir).restore("pre-01_Invoice_Batch_01")
    assert Ledger(cfg.state_dir).runs() == []
    assert by_file(run_labels(cfg, B1))["APINBOX_0003.pdf"].decision == "ENTERED"


def test_explain(make_cfg, monkeypatch):
    cfg = make_cfg()
    run_labels(cfg, B1)
    monkeypatch.setattr("ap_automation.cli._cfg", lambda *a, **k: cfg)
    res = cli.invoke(app, ["explain", "APINBOX_0003"], terminal_width=250)
    assert res.exit_code == 0, res.output
    for s in ("What the AI read", "Rule change_orders: pass", "51000", "20500", "VP Construction", "Confidence"):
        assert s in res.output, s


def test_cli_run_and_snapshot_commands(make_cfg):
    cfg = make_cfg()
    res = cli.invoke(app, ["run", str(B1)] + _args(cfg), terminal_width=250)
    assert res.exit_code == 0, res.output
    assert "Entered 6 · Entrata 1 · Held 8" in res.output
    res = cli.invoke(app, ["snapshot", "save", "after-b1", "--state-dir", str(cfg.state_dir)])
    assert res.exit_code == 0 and (cfg.state_dir / "snapshots/after-b1.db").exists()
    res = cli.invoke(app, ["snapshot", "restore", "nope", "--state-dir", str(cfg.state_dir)])
    assert res.exit_code == 1 and "no snapshot named" in res.output
    assert (cfg.state_dir / "processed_register.csv").read_text().count("\n") == 16


def test_run_missing_inbox_is_a_clear_error(make_cfg):
    cfg = make_cfg()
    res = cli.invoke(app, ["run", "/no/such/folder"] + _args(cfg))
    assert res.exit_code == 1 and "Inbox folder not found" in res.output


def test_doctor_without_key(make_cfg, monkeypatch):
    cfg = make_cfg()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    res = cli.invoke(app, ["doctor", "--state-dir", str(cfg.state_dir)], terminal_width=250)
    assert "policy.yaml valid" in res.output and "Import template: 19 Intacct columns, 14 Entrata columns" in res.output
    assert "Anthropic credentials found" in res.output and res.exit_code == 1


def test_offline_mode_holds_uncached_docs_instead_of_crashing(make_cfg):
    cfg = make_cfg()
    rr = __import__("ap_automation.engine", fromlist=["run"]).run(cfg, B1, mode="offline")
    assert all(r.decision == "HELD" and r.confidence == "Low" for r in rr.results)
    assert "not in extraction cache" in rr.results[0].findings[0].message


def test_grounding_catches_a_misread_number(make_cfg, tmp_path):
    # Copy one real invoice + a label that misreads the invoice number; the text-layer cross-check must hold it.
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(B1 / "APINBOX_0005.pdf", inbox / "APINBOX_0005.pdf")
    lab = tmp_path / "labels"
    lab.mkdir()
    d = json.loads((LABELS[0] / "APINBOX_0005.json").read_text())
    d["document_number"], d["total"] = "CSS-88052", 1420.00
    (lab / "APINBOX_0005.json").write_text(json.dumps(d))
    from ap_automation.engine import run

    rr = run(make_cfg(), inbox, mode="labels", labels_dirs=[lab, LABELS[1]])
    r = rr.results[0]
    assert r.decision == "HELD" and r.confidence == "Low"
    msgs = " ".join(f.message for f in r.findings)
    assert "does not appear in the document text" in msgs and "≠ total" in msgs


# ------------------------------------------------------------------------------- Claude extractor (mocked API)
from ap_automation.extract import to_api  # noqa: E402


def _reply(stop, ex=None, text=None):
    body = text if text is not None else (json.dumps(to_api(ex)) if ex is not None else "")
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=body)],
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0, cache_creation_input_tokens=0))


class _FakeMessages:
    def __init__(self, script):
        self.calls, self.script = [], list(script)

    def create(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _fake_claude(cfg, script):
    ce = ClaudeExtractor.__new__(ClaudeExtractor)
    import anthropic

    ce.anthropic, ce.model, ce.fallback = anthropic, "claude-opus-5-5", "claude-sonnet-5-5"
    ce.effort, ce.max_tokens, ce.base_prompt = "medium", 16000, "PROMPT"
    ce.mode, ce._systems = {"bill": "validated_json", "reference": "grammar"}, {}
    ce.client = SimpleNamespace(messages=_FakeMessages(script))
    return ce


def _truth():
    return ExtractedDocument.model_validate_json((LABELS[0] / "APINBOX_0005.json").read_text())


def test_claude_request_shape_and_cache(make_cfg):
    cfg = make_cfg()
    ce = _fake_claude(cfg, [_reply("end_turn", _truth())])
    cached = CachedExtractor(cfg, ce)
    doc = intake(B1 / "APINBOX_0005.pdf")
    ex, src = cached.extract(doc)
    call = ce.client.messages.calls[0]
    assert ex == _truth() and src == "claude:claude-opus-5-5"
    assert call["model"] == "claude-opus-5-5" and call["output_config"] == {"effort": "medium"} and "temperature" not in call
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"} and '"document_number"' in call["system"][0]["text"]
    block = call["messages"][0]["content"][0]
    assert block["type"] == "document" and block["source"]["media_type"] == "application/pdf"
    # second call is served from the hash-keyed cache: no API call, identical result
    ex2, src2 = cached.extract(doc)
    assert len(ce.client.messages.calls) == 1 and src2.startswith("cache:") and ex2 == ex
    files = list((cfg.state_dir / "extractions").glob(f"{doc.sha256}.v2.bill.claude-opus-5-5.json"))
    assert len(files) == 1 and json.loads(files[0].read_text())["meta"]["file_name"] == "APINBOX_0005.pdf"


def test_reference_docs_use_grammar_schema(make_cfg):
    ce = _fake_claude(make_cfg(), [_reply("end_turn", ExtractedDocument(doc_kind="purchase_order", document_number="PO2410315-011"))])
    ce.extract_with_meta(intake(ROOT_ / "03_Purchase_Orders_and_Subcontracts/PO2410315-011.pdf", role="reference"))
    fmt = ce.client.messages.calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and "change_orders" in fmt["schema"]["properties"] and "line_items" not in fmt["schema"]["properties"]


def test_invalid_json_gets_one_repair_turn(make_cfg):
    ce = _fake_claude(make_cfg(), [_reply("end_turn", text='{"doc_kind": "invoice", "total": "abc"}'), _reply("end_turn", _truth())])
    ex, src, meta = ce.extract_with_meta(intake(B1 / "APINBOX_0005.pdf"))
    assert meta["repaired"] and ex == _truth()
    repair = ce.client.messages.calls[1]["messages"]
    assert repair[-2]["role"] == "assistant" and "failed validation" in repair[-1]["content"]


def test_refusal_falls_back_then_gives_up(make_cfg):
    ce = _fake_claude(make_cfg(), [_reply("refusal"), _reply("end_turn", _truth())])
    ex, src, meta = ce.extract_with_meta(intake(B1 / "APINBOX_0005.pdf"))
    assert src == "claude:claude-sonnet-5-5" and meta["model"] == "claude-sonnet-5-5"
    ce = _fake_claude(make_cfg(), [_reply("refusal"), _reply("max_tokens")])
    try:
        ce.extract_with_meta(intake(B1 / "APINBOX_0005.pdf"))
        raise AssertionError("expected ExtractionUnavailable")
    except ExtractionUnavailable as e:
        assert "refusal" in str(e) and "truncated" in str(e)


def test_grammar_too_large_self_heals(make_cfg):
    import anthropic

    err = anthropic.BadRequestError.__new__(anthropic.BadRequestError)
    Exception.__init__(err, "The compiled grammar is too large, which would cause performance issues.")
    ce = _fake_claude(make_cfg(), [err, _reply("end_turn", ExtractedDocument(doc_kind="purchase_order", document_number="PO2410315-011"))])
    ce.extract_with_meta(intake(ROOT_ / "03_Purchase_Orders_and_Subcontracts/PO2410315-011.pdf", role="reference"))
    assert ce.mode["reference"] == "validated_json" and "format" not in ce.client.messages.calls[1]["output_config"]


def test_api_schema_has_no_unions_or_optionals():
    from ap_automation.extract import api_schema, from_api

    for role in ("bill", "reference"):
        s = json.dumps(api_schema(role))
        assert "anyOf" not in s and '"null"' not in s
    assert from_api(to_api(_truth())) == _truth().model_dump(mode="json") or ExtractedDocument.model_validate(from_api(to_api(_truth()))) == _truth()


def test_image_and_docx_content_blocks(make_cfg):
    ce = _fake_claude(make_cfg(), [])
    png = ce._content(intake(ROOT_ / "tests/synthetic/holdout_A/SYN_A12_scanned_image_png.png"))[0]
    docx = ce._content(intake(ROOT_ / "tests/synthetic/holdout_A/SYN_A13_word_docx_software.docx"))[0]
    assert png["type"] == "image" and png["source"]["media_type"] == "image/png"
    assert docx["type"] == "document" and docx["source"]["type"] == "text" and "LL-2026-1201" in docx["source"]["data"]


def test_cli_loads_dotenv_without_overriding(tmp_path, monkeypatch):
    from ap_automation import cli as cli_mod

    (tmp_path / ".env").write_text("# comment\nAP_TEST_A='from-file'\nexport AP_TEST_B=file\n")
    monkeypatch.setattr("ap_automation.config.ROOT", tmp_path)
    monkeypatch.delenv("AP_NO_DOTENV")
    monkeypatch.delenv("AP_TEST_A", raising=False)
    monkeypatch.setenv("AP_TEST_B", "shell")
    cli_mod._load_dotenv()
    assert os.environ["AP_TEST_A"] == "from-file" and os.environ["AP_TEST_B"] == "shell"
    monkeypatch.delenv("AP_TEST_A")


def test_delete_latest_run_restores_ledger_and_is_reversible(make_cfg):
    """Deleting a run undoes exactly what it recorded; only the latest recorded run may go; it is snapshotted,
    archived and audit-logged."""
    import json
    import sqlite3

    import pytest

    from conftest import B2
    from ap_automation.ledger import Ledger
    from ap_automation.runs import RunDeleteRefused, delete_impact, delete_run, run_dirs

    cfg = make_cfg()
    db = cfg.state_dir / "ap_ledger.db"
    dump = lambda: {t: sorted(map(tuple, sqlite3.connect(db).execute(f"SELECT * FROM {t}")))  # noqa: E731
                    for t in ("entered_bills", "po_consumption", "waivers_on_file", "runs")} | {
        "docs": sorted(sqlite3.connect(db).execute("SELECT run_id, file_name, decision, superseded FROM documents"))}
    run_labels(cfg, B1)
    before = dump()
    first_b2 = run_labels(cfg, B2)
    b1_id, b2_id = [p.name for p in run_dirs(cfg)]

    imp = delete_impact(cfg, b1_id)
    assert imp["blocked"] and imp["later_runs"] == [b2_id]
    with pytest.raises(RunDeleteRefused):
        delete_run(cfg, b1_id)

    imp = delete_impact(cfg, b2_id)
    assert (imp["recorded"], imp["documents"], imp["entered"], imp["entered_amount"]) == (True, 5, 2, "19128.80")
    entry = delete_run(cfg, b2_id, actor="test")
    assert dump() == before  # incl. APINBOX_0012 no longer superseded by 0018
    assert [p.name for p in run_dirs(cfg)] == [b1_id] and (cfg.state_dir / "deleted_runs" / b2_id / "decisions.jsonl").exists()
    assert json.loads((cfg.state_dir / "audit_log.jsonl").read_text().splitlines()[-1])["run_id"] == b2_id
    assert entry["ledger_snapshot"] in Ledger(cfg.state_dir).list_snapshots()

    again = run_labels(cfg, B2)
    assert {f: (r.decision, codes(r)) for f, r in by_file(again).items()} == \
           {f: (r.decision, codes(r)) for f, r in by_file(first_b2).items()}


@pytest.mark.parametrize("override, file, expect", [
    ({"vendor_overrides__V1003__terms": "Net 45"}, "APINBOX_0005.pdf", "term name Net 15 → Net 45"),
    ({"periods__open_period_override": "2026-11"}, "APINBOX_0008.pdf", "Entrata post month 10/2026 → 11/2026"),
    ({"exception_codes__OVERPO__route": "Supply Chain"}, "APINBOX_0001.pdf", "route 'Project Manager and Supply Chain' → 'Supply Chain'"),
])
def test_diff_reports_changes_beyond_the_decision(make_cfg, override, file, expect):
    """A rule change that moves terms, dates, Entrata post month or a route (not the decision) must show in diff/preview."""
    from ap_automation.runs import compare_runs, load_records

    base = run_labels(make_cfg(), B1, what_if=True)
    new = run_labels(make_cfg(**override), B1, what_if=True)
    rows = {r["file_name"]: r for r in compare_runs(load_records(base.out_dir), load_records(new.out_dir))}
    assert file in rows and any(expect in w for w in rows[file]["why"]), rows.get(file)


def test_damaged_files_are_held_and_the_batch_continues(make_cfg, tmp_path):
    import shutil

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "BAD.docx").write_text("not a zip")
    (inbox / "BAD.pdf").write_bytes(b"%PDF-1.4 truncated")
    shutil.copyfile(B1 / "APINBOX_0005.pdf", inbox / "APINBOX_0005.pdf")
    res = by_file(run_labels(make_cfg(), inbox))
    for f in ("BAD.docx", "BAD.pdf"):
        assert res[f].decision == "HELD" and "damaged" in res[f].findings[0].message
    assert res["APINBOX_0005.pdf"].decision == "ENTERED"


def test_cli_runs_a_zip_or_a_folder_of_folders(tmp_path, monkeypatch):
    import shutil
    import zipfile

    from typer.testing import CliRunner

    from ap_automation import cli

    nested = tmp_path / "batch" / "vendor_a"
    nested.mkdir(parents=True)
    shutil.copyfile(B1 / "APINBOX_0005.pdf", nested / "APINBOX_0005.pdf")
    common = ["--labels", str(LABELS[0]), "--labels", str(LABELS[1]), "--state-dir", str(tmp_path / "s"), "--out-dir", str(tmp_path / "o")]
    r = CliRunner().invoke(cli.app, ["run", str(tmp_path / "batch"), *common])
    assert r.exit_code == 0 and "Entered 1" in r.output, r.output
    with zipfile.ZipFile(tmp_path / "drop.zip", "w") as z:
        z.write(B1 / "APINBOX_0010.pdf", "Invoices/APINBOX_0010.pdf")
        z.writestr("__MACOSX/Invoices/._APINBOX_0010.pdf", b"junk")
    r = CliRunner().invoke(cli.app, ["run", str(tmp_path / "drop.zip"), *common])
    assert r.exit_code == 0 and "Unpacked 1 files" in r.output and "Entered 1" in r.output, r.output
    (tmp_path / "empty").mkdir()
    assert CliRunner().invoke(cli.app, ["run", str(tmp_path / "empty"), *common]).exit_code == 1
