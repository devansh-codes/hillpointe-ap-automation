"""Web UI for the AP team: `uv run ap ui`.

A thin layer over the same engine, ledger and policy code the CLI uses. It adds no business logic: every decision
shown here comes from `engine.run` and is read back from the run folders in output/ and the ledger in state/.
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import ROOT, PolicyError, load_config, validate_policy
from ..extract import keep_name, list_inbox, save_flat, unpack_zip
from ..ledger import Ledger
from ..runs import (RunDeleteRefused, RunNotFound, compare_runs, delete_impact, delete_run, find_run, hold_codes, load_records,
                    run_dirs, run_info)

STATIC = Path(__file__).parent / "static"
POLICY = ROOT / "config/policy.yaml"
OUTPUT_FILES = {"intacct_bill_import.csv", "entrata_handoff.csv", "exception_log.csv", "approvals.csv", "decisions.jsonl",
                "run_report.html", "run_report.md"}
DOC_SUFFIXES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# Prices per million tokens for the cost estimate shown in the sidebar (Opus 5.5).
PRICE = {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 6.25}

app = FastAPI(title="Hillpointe AP", docs_url=None, redoc_url=None)
_lock = threading.Lock()  # one engine run at a time: the ledger is single-writer
JOBS: dict[str, dict] = {}
RUN_KW: dict[str, Any] = {}  # tests set {"mode": "labels", "labels_dirs": [...]} so no API calls are made


def _cfg(**kw):
    try:
        return load_config(**kw)
    except PolicyError as e:
        raise HTTPException(400, f"policy.yaml has problems: {e}")


# ------------------------------------------------------------------------------------------------ runs
def _summary(recs: list[dict]) -> dict:
    by: dict[str, dict] = {}
    codes: dict[str, int] = {}
    for r in recs:
        b = by.setdefault(r["decision"], {"count": 0, "amount": 0.0})
        b["count"] += 1
        b["amount"] += float(r["amount"] or 0)
        for c in hold_codes(r):
            codes[c] = codes.get(c, 0) + 1
    conf = {k: sum(1 for r in recs if r["confidence"] == k) for k in ("High", "Medium", "Low")}
    sources: dict[str, int] = {}
    for r in recs:
        sources[r["extraction_source"] or "none"] = sources.get(r["extraction_source"] or "none", 0) + 1
    peek = [{"file_name": r["file_name"], "vendor_name": r["vendor_name"], "decision": r["decision"], "codes": hold_codes(r),
             "amount": r["amount"]} for r in recs[:4]]
    return {"docs": len(recs), "by_decision": by, "codes": codes, "confidence": conf, "sources": sources, "peek": peek}


def _run_card(p: Path) -> dict:
    recs = load_records(p)
    return run_info(p) | {"summary": _summary(recs), "files": sorted(f.name for f in p.iterdir() if f.is_file())}


@app.get("/api/runs")
def list_runs():
    cfg = _cfg()
    return [_run_card(p) for p in sorted(run_dirs(cfg), key=lambda q: q.name, reverse=True)]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    cfg = _cfg()
    try:
        p = find_run(cfg, run_id)
    except RunNotFound as e:
        raise HTTPException(404, str(e))
    recs = load_records(p)
    for r in recs:
        r["hold_codes"] = hold_codes(r)
    return _run_card(p) | {"records": recs}


@app.get("/api/runs/{run_id}/delete-impact")
def run_delete_impact(run_id: str):
    try:
        return delete_impact(_cfg(), run_id)
    except RunNotFound as e:
        raise HTTPException(404, str(e))


@app.delete("/api/runs/{run_id}")
def run_delete(run_id: str, body: dict = Body(...)):
    if body.get("confirm") != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm.')
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "A run is in progress. Wait for it to finish.")
    try:
        return delete_run(_cfg(), run_id, actor="web UI")
    except RunNotFound as e:
        raise HTTPException(404, str(e))
    except RunDeleteRefused as e:
        raise HTTPException(409, str(e))
    finally:
        _lock.release()


@app.get("/api/runs/{run_id}/file/{name}")
def run_file(run_id: str, name: str):
    p = find_run(_cfg(), run_id)
    f = p / name
    if not (name in OUTPUT_FILES or (name.startswith("AP_Bill_Import_") and name.endswith(".xlsx"))) or not f.exists():
        raise HTTPException(404, "no such output file")
    return FileResponse(f, filename=name if not name.endswith(".html") else None)


def _source_path(run_id: str, file_name: str) -> Path:
    info = run_info(find_run(_cfg(), run_id))
    inbox = Path(info["inbox"]) if info["inbox"] else None
    p = (inbox / file_name).resolve() if inbox else None
    if p and not p.is_file() and inbox.is_dir():  # documents in sub-folders of the inbox
        p = next((q.resolve() for q in list_inbox(inbox) if q.name == file_name), p)
    if not p or not p.is_file() or ROOT.resolve() not in p.parents:
        raise HTTPException(404, "source document not found")
    return p


@app.get("/api/source/{run_id}/{file_name}")
def source(run_id: str, file_name: str):
    p = _source_path(run_id, file_name)
    kind = DOC_SUFFIXES.get(p.suffix.lower())
    if kind:
        return FileResponse(p, media_type=kind, headers={"Content-Disposition": f'inline; filename="{p.name}"'})
    if p.suffix.lower() == ".docx":
        import docx

        d = docx.Document(str(p))
        text = [x.text for x in d.paragraphs if x.text.strip()]
        for t in d.tables:
            text += [" | ".join(c.text for c in row.cells) for row in t.rows]
        return JSONResponse({"kind": "text", "text": "\n".join(text)})
    return JSONResponse({"kind": "unsupported", "text": f"{p.suffix} files can't be previewed or read. The system holds them for a person."})


# ------------------------------------------------------------------------------------------------ inboxes & upload
def _inboxes() -> list[Path]:
    found = [p for p in ROOT.iterdir() if p.is_dir() and re.match(r"\d\d_.*(Batch|Rerun)", p.name)]
    for base in (ROOT / "inbox", ROOT / "tests/synthetic"):
        if base.is_dir():
            found += [p for p in base.iterdir() if p.is_dir() and not p.name.startswith(("_", "labels"))]
    return sorted(found, key=lambda p: (not p.parent == ROOT, p.parent.name, p.name))


@app.get("/api/inboxes")
def inboxes():
    cfg = _cfg()
    runs = Ledger(cfg.state_dir).runs()
    snaps = set(Ledger(cfg.state_dir).list_snapshots())
    out = []
    for p in _inboxes():
        docs = [f.name for f in list_inbox(p)]
        out.append({"name": p.name, "path": str(p.relative_to(ROOT)), "docs": len(docs), "files": docs,
                    "group": "Package" if p.parent == ROOT else ("Uploaded" if p.parent.name == "inbox" else "Test documents"),
                    "runs": sum(1 for r in runs if Path(r["inbox"]).name == p.name),
                    "has_pre_snapshot": f"pre-{p.name}" in snaps})
    return out


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...), name: str = Form("")):
    """Files, a whole folder (the browser sends each file with its relative path) or .zip archives -> one inbox."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "batch"
    dest = ROOT / "inbox" / f"{datetime.now():%Y%m%d-%H%M}_{slug}"
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        rel, data = f.filename or "document", await f.read()
        if not keep_name(rel):
            continue
        if rel.lower().endswith(".zip") and zipfile.is_zipfile(io.BytesIO(data)):
            saved += unpack_zip(data, dest)
        else:
            saved.append(save_flat(dest, rel, data))
    if not saved:
        dest.rmdir()
        raise HTTPException(400, "No documents found in what was uploaded.")
    return {"path": str(dest.relative_to(ROOT)), "name": dest.name, "files": saved}


# ------------------------------------------------------------------------------------------------ jobs (engine runs)
def _inbox_path(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if ROOT.resolve() not in p.parents or not p.is_dir():
        raise HTTPException(400, f"inbox folder not found: {rel}")
    return p


def _start(kind: str, fn) -> dict:
    if _lock.locked():
        raise HTTPException(409, "Another run is in progress. Wait for it to finish.")
    job = {"id": uuid.uuid4().hex[:10], "kind": kind, "status": "running", "done": 0, "total": 0, "current": "",
           "run_id": None, "error": None, "result": None}
    JOBS[job["id"]] = job

    def progress(name: str, done: int, total: int) -> None:
        job.update(current=name, done=done, total=total)

    def work():
        with _lock:
            try:
                job["result"] = fn(progress)
                job["run_id"] = (job["result"] or {}).get("run_id")
                job["status"] = "done"
            except Exception as e:  # noqa: BLE001 - surfaced to the UI
                job.update(status="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=work, daemon=True).start()
    return job


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    return JOBS[job_id]


def _run_kw(offline: bool) -> dict:
    return {"mode": "offline" if offline else "auto"} | RUN_KW


@app.post("/api/run")
def start_run(body: dict = Body(...)):
    """Process a folder for real (or as a what-if preview that doesn't touch the ledger)."""
    from ..engine import run

    inbox = _inbox_path(body["inbox"])
    what_if, offline = bool(body.get("what_if")), bool(body.get("offline"))

    def fn(progress):
        rr = run(_cfg(), inbox, what_if=what_if, progress=progress, **_run_kw(offline))
        return {"run_id": rr.run_id}

    return _start("run", fn)


def _baseline(cfg, inbox_name: str) -> Optional[Path]:
    """Default comparison run for a batch: the committed run that decided the most documents (not 'already processed')."""
    cands = [p for p in run_dirs(cfg) if (i := run_info(p))["inbox_name"] == inbox_name and not i["what_if"]]
    if not cands:
        return None
    return min(reversed(cands), key=lambda p: sum(1 for r in load_records(p) if r["decision"] == "ALREADY_PROCESSED"))


@app.post("/api/preview")
def preview(body: dict = Body(...)):
    """Rule-change impact: re-decide a batch under a DRAFT policy, starting from the ledger as it was before that batch.

    Runs in a throw-away copy of the ledger with what_if=True, so nothing real changes. AI readings come from the shared
    cache, so a preview of an already-read batch costs no tokens.
    """
    from ..engine import run

    inbox = _inbox_path(body["inbox"])
    draft = body.get("policy_text")
    offline = bool(body.get("offline", False))
    base_cfg = _cfg()
    baseline = body.get("baseline") or (b.name if (b := _baseline(base_cfg, inbox.name)) else None)

    def fn(progress):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            state = tmp / "state"
            state.mkdir()
            led = Ledger(base_cfg.state_dir)
            src = led.snap_dir / f"pre-{inbox.name}.db"
            shutil.copyfile(src if src.exists() else led.path, state / "ap_ledger.db")
            (state / "extractions").symlink_to(base_cfg.state_dir / "extractions", target_is_directory=True)
            policy_path = None
            if draft:
                policy_path = tmp / "policy.yaml"
                policy_path.write_text(draft)
            cfg = _cfg(policy_path=policy_path, state_dir=state)
            rr = run(cfg, inbox, what_if=True, progress=progress, **_run_kw(offline))
        meta_p = rr.out_dir / "run_meta.json"
        meta = json.loads(meta_p.read_text())
        meta["note"] = "Rule-change preview" + (" (draft policy)" if draft else "") + (f" vs {baseline}" if baseline else "")
        meta["baseline"] = baseline
        meta_p.write_text(json.dumps(meta, indent=2))
        rows = compare_runs(load_records(find_run(base_cfg, baseline)), load_records(rr.out_dir)) if baseline else []
        return {"run_id": rr.run_id, "baseline": baseline, "changes": rows, "docs": len(rr.results),
                "source": "pre-batch snapshot" if src.exists() else "current ledger"}

    return _start("preview", fn)


@app.post("/api/apply")
def apply_batch(body: dict = Body(...)):
    """Re-decide a batch for real under the saved policy: restore pre-<batch>, then run it (the CLI's restore → run flow)."""
    from ..engine import run

    inbox = _inbox_path(body["inbox"])
    cfg = _cfg()
    led = Ledger(cfg.state_dir)
    if f"pre-{inbox.name}" not in led.list_snapshots():
        raise HTTPException(400, f"No 'pre-{inbox.name}' snapshot: this batch hasn't been processed yet. Use Run instead.")
    baseline = b.name if (b := _baseline(cfg, inbox.name)) else None

    def fn(progress):
        led.restore(f"pre-{inbox.name}")
        rr = run(_cfg(), inbox, progress=progress, **_run_kw(bool(body.get("offline"))))
        rows = compare_runs(load_records(find_run(cfg, baseline)), load_records(rr.out_dir)) if baseline else []
        return {"run_id": rr.run_id, "baseline": baseline, "changes": rows}

    return _start("apply", fn)


@app.get("/api/diff")
def diff(a: str, b: str):
    cfg = _cfg()
    ra, rb = find_run(cfg, a), find_run(cfg, b)
    ka, kb = load_records(ra), load_records(rb)
    rows = compare_runs(ka, kb)
    return {"a": ra.name, "b": rb.name, "changes": rows,
            "unchanged": len({r["file_name"] for r in ka} | {r["file_name"] for r in kb}) - len(rows)}


# ------------------------------------------------------------------------------------------------ exceptions & ledger
def _db(cfg) -> sqlite3.Connection:
    c = sqlite3.connect(Ledger(cfg.state_dir).path)
    c.row_factory = sqlite3.Row
    return c


@app.get("/api/exceptions")
def exceptions():
    """Open holds in the ledger: latest decision per document, still HELD / NOT A BILL, not superseded by a revision."""
    cfg = _cfg()
    with _db(cfg) as c:
        rows = [dict(r) for r in c.execute(
            """SELECT d.* FROM documents d JOIN (SELECT sha256, MAX(id) AS id FROM documents GROUP BY sha256) l ON d.id = l.id
               WHERE d.decision IN ('HELD', 'NOT_A_BILL') AND d.superseded = 0 ORDER BY d.id""")]
    cache: dict[str, dict] = {}
    for r in rows:
        if r["run_id"] not in cache:
            try:
                cache[r["run_id"]] = {x["sha256"]: x for x in load_records(find_run(cfg, r["run_id"]))}
            except RunNotFound:
                cache[r["run_id"]] = {}
        rec = cache[r["run_id"]].get(r["sha256"], {})
        r["findings"] = [f for f in rec.get("findings", []) if f["hold"]]
        r["codes"] = [c for c in [r["primary_code"], *(r["secondary_codes"] or "").split(",")] if c]
    return rows


@app.get("/api/ledger")
def ledger():
    cfg = _cfg()
    led = Ledger(cfg.state_dir)
    with _db(cfg) as c:
        entered = [dict(r) for r in c.execute("SELECT * FROM entered_bills ORDER BY rowid")]
        docs = [dict(r) for r in c.execute("SELECT * FROM documents ORDER BY id")]
    snaps = []
    for s in led.list_snapshots():
        p = led.snap_dir / f"{s}.db"
        with sqlite3.connect(p) as c:
            n_runs = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] if c.execute(
                "SELECT name FROM sqlite_master WHERE name='runs'").fetchone() else 0
            n_bills = c.execute("SELECT COUNT(*) FROM entered_bills").fetchone()[0] if n_runs else 0
        snaps.append({"name": s, "runs": n_runs, "entered": n_bills,
                      "saved_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    return {"runs": led.runs(), "entered": entered, "documents": docs, "snapshots": snaps, "path": str(led.path.relative_to(ROOT) if led.path.is_relative_to(ROOT) else led.path)}


@app.get("/api/ledger/register.csv")
def register_csv():
    p = Ledger(_cfg().state_dir).state_dir / "processed_register.csv"
    return FileResponse(p, filename="processed_register.csv")


@app.post("/api/snapshots/{name}/restore")
def restore(name: str):
    if _lock.locked():
        raise HTTPException(409, "A run is in progress.")
    led = Ledger(_cfg().state_dir)
    try:
        led.restore(name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "runs": len(led.runs())}


@app.post("/api/snapshots")
def save_snapshot(body: dict = Body(...)):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", body.get("name", "")).strip("-")
    if not name:
        raise HTTPException(400, "name required")
    Ledger(_cfg().state_dir).snapshot(name)
    return {"ok": True, "name": name}


# ------------------------------------------------------------------------------------------------ policy
KNOBS = [
    {"path": "overpo.tolerance", "label": "Over-PO tolerance", "unit": "$", "type": "number", "section": "§6 PO matching",
     "help": "Hold (OVERPO) when billed-to-date would exceed the PO by more than this."},
    {"path": "price_variance.action", "label": "Unit price differs from PO", "type": "choice", "options": ["warn", "hold"],
     "section": "§6 PO matching", "help": "warn = enter it with a Check reading note; hold = hold as OTHER for the AP Manager."},
    {"path": "price_variance.tolerance_pct", "label": "Price variance allowed", "unit": "%", "type": "number", "section": "§6 PO matching",
     "help": "Unit-rate difference ignored below this percentage."},
    {"path": "approvals.construction.additional.when_gross_work_over", "label": "VP Construction approval above", "unit": "$",
     "type": "number", "section": "§13 Approvals", "help": "Construction bills with gross work above this also need the VP Construction."},
    {"path": "approvals.stabilized.additional.when_invoice_over", "label": "Regional Property Manager above", "unit": "$",
     "type": "number", "section": "§13 Approvals", "help": "Stabilized-community invoices above this also need the RPM."},
    {"path": "approvals.corporate.additional.when_bill_over", "label": "CFO approval above", "unit": "$", "type": "number",
     "section": "§13 Approvals", "help": "Corporate bills above this also need the CFO."},
    {"path": "coi.grace_days", "label": "COI grace period", "unit": "days", "type": "number", "section": "§5 Pay applications",
     "help": "Insurance certificate may be expired by up to this many days before holding (COI)."},
    {"path": "lien.accept_waiver_on_file", "label": "Accept a waiver already on file", "type": "bool", "section": "§5 Pay applications",
     "help": "A matching conditional waiver received earlier satisfies the lien-waiver requirement."},
    {"path": "periods.open_period_override", "label": "Force open period", "type": "text", "placeholder": "e.g. 2026-11",
     "section": "§7 Dates", "help": "Leave empty to use the Periods tab in the master data."},
    {"path": "dup.near_date_days", "label": "Possible-duplicate window", "unit": "days", "type": "number", "section": "§10 Duplicates",
     "help": "Same vendor + same amount within this many days is flagged for a person."},
    {"path": "dup.revision_after_entered_code", "label": "Revision of an entered bill", "type": "choice", "options": ["DUP", "OTHER"],
     "section": "§10 Duplicates", "help": "Exception code when a revised invoice arrives after the original was entered."},
]


def _get(d: Any, path: str):
    for k in path.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _scalar(v: Any) -> str:
    if v is None or v == "":
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    s = str(v)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", s) and s.lower() not in {"yes", "no", "on", "off", "true", "false", "null", "y", "n"}:
        return s
    return json.dumps(s)


def set_policy_value(text: str, path: str, value: Any) -> str:
    """Change one value in policy.yaml text without losing comments or layout (block keys and inline {flow} maps)."""
    keys = path.split(".")
    lines = text.splitlines(keepends=True)
    start, end, parent_indent = 0, len(lines), -1
    for depth, key in enumerate(keys):
        child_indent, hit = None, None
        for i in range(start, end):
            raw = lines[i]
            body = raw.lstrip(" ")
            if not body.strip() or body.startswith("#"):
                continue
            ind = len(raw) - len(body)
            if ind <= parent_indent:
                end = i
                break
            child_indent = ind if child_indent is None else child_indent
            if ind != child_indent:
                continue
            m = re.match(rf'"?{re.escape(key)}"?:(\s*)(.*)$', body.rstrip("\n"))
            if m:
                hit = i
                break
        if hit is None:
            raise KeyError(path)
        rest = keys[depth + 1:]
        line = lines[hit]
        if rest and "{" in line:  # inline map: replace inside the braces
            k = rest[-1]
            new, n = re.subn(rf"(\b{re.escape(k)}:\s*)([^,}}]+)", lambda m: m.group(1) + _scalar(value), line, count=1)
            if not n:
                raise KeyError(path)
            lines[hit] = new
            break
        if not rest:
            m = re.match(rf'(\s*"?{re.escape(key)}"?:\s*)([^#\n]*?)(\s*#.*)?(\n?)$', line)
            lines[hit] = m.group(1) + _scalar(value) + (("   " + m.group(3).lstrip()) if m.group(3) else "") + m.group(4)
            break
        start, parent_indent = hit + 1, child_indent
        end = len(lines)
    out = "".join(lines)
    got = _get(yaml.safe_load(out), path)
    want = None if value in ("", None) else value
    if (got != want) and not (isinstance(want, (int, float)) and isinstance(got, (int, float)) and float(got) == float(want)):
        raise ValueError(f"could not set {path}")
    return out


def _check_text(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
        validate_policy(data)
    except (PolicyError, yaml.YAMLError) as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "error": None}


@app.get("/api/policy")
def get_policy():
    text = POLICY.read_text()
    data = yaml.safe_load(text)
    return {"text": text, "hash": _cfg().policy_hash, "knobs": [k | {"value": _get(data, k["path"])} for k in KNOBS],
            "rules": data.get("rules", []), "codes": data.get("exception_codes", {}), "history": _history()}


@app.post("/api/policy/draft")
def draft(body: dict = Body(...)):
    text = body.get("text") or POLICY.read_text()
    try:
        for path, value in (body.get("changes") or {}).items():
            text = set_policy_value(text, path, value)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"Couldn't change {e}")
    return {"text": text} | _check_text(text)


@app.post("/api/policy/validate")
def validate(body: dict = Body(...)):
    return _check_text(body.get("text", ""))


def _hist_dir() -> Path:
    return _cfg().state_dir / "policy_history"


def _history() -> list[dict]:
    d = _hist_dir()
    return [{"name": p.name, "saved_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(d.glob("*.yaml"), reverse=True)] if d.exists() else []


@app.put("/api/policy")
def save_policy(body: dict = Body(...)):
    text = body.get("text", "")
    chk = _check_text(text)
    if not chk["ok"]:
        raise HTTPException(400, chk["error"])
    d = _hist_dir()
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(POLICY, d / f"{datetime.now():%Y%m%d-%H%M%S}_before.yaml")
    POLICY.write_text(text)
    return {"ok": True, "hash": _cfg().policy_hash}


@app.post("/api/policy/revert/{name}")
def revert_policy(name: str):
    p = _hist_dir() / Path(name).name
    if not p.exists():
        raise HTTPException(404, "no such saved version")
    return save_policy({"text": p.read_text()})


# ------------------------------------------------------------------------------------------------ status, usage, search
@app.get("/api/status")
def status(ping: bool = False):
    from ..health import run_checks

    checks = run_checks(ping=ping)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


@app.get("/api/usage")
def usage():
    cfg = _cfg()
    tot = {"reads": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "seconds": 0.0}
    for p in (cfg.state_dir / "extractions").glob("*.json"):
        m = (json.loads(p.read_text()).get("meta") or {})
        if not m.get("input_tokens"):
            continue
        tot["reads"] += 1
        tot["input"] += m.get("input_tokens") or 0
        tot["output"] += m.get("output_tokens") or 0
        tot["cache_read"] += m.get("cache_read_input_tokens") or 0
        tot["cache_write"] += m.get("cache_creation_input_tokens") or 0
        tot["seconds"] += m.get("seconds") or 0
    tot["cost"] = round(sum(tot[k] * PRICE[k] for k in PRICE) / 1e6, 2)
    tot["model"] = cfg.settings["extraction"]["model"]
    tot["effort"] = cfg.settings["extraction"].get("effort")
    return tot


@app.get("/api/search")
def search(q: str):
    cfg = _cfg()
    t = q.lower().strip()
    if not t:
        return []
    seen, hits = set(), []
    for p in sorted(run_dirs(cfg), key=lambda x: x.name, reverse=True):
        info = run_info(p)
        if info["what_if"]:
            continue
        for r in load_records(p):
            hay = " ".join(str(x or "") for x in (r["file_name"], r["vendor_name"], r["vendor_id"], r["bill_no"], r["project_id"],
                                                  r["reference_no"], r["decision"], " ".join(hold_codes(r)))).lower()
            if t in hay and r["file_name"] not in seen and r["decision"] != "ALREADY_PROCESSED":
                seen.add(r["file_name"])
                hits.append({"run_id": p.name, "inbox_name": info["inbox_name"], "file_name": r["file_name"],
                             "vendor_name": r["vendor_name"], "bill_no": r["bill_no"], "amount": r["amount"],
                             "decision": r["decision"], "codes": hold_codes(r)})
    return hits[:25]


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def serve(port: int = 8765, open_browser: bool = True) -> None:
    import webbrowser

    import uvicorn

    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Hillpointe AP is running at {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
