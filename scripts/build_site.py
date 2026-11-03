"""Build the read-only public demo of the web UI (GitHub Pages).

Exports every GET answer of the local API for the SUBMITTED state (the three evidence runs in output/ and the
`submitted` ledger snapshot) as static files, so the same app.js runs with no server. Writes are disabled in the page.
Local paths are scrubbed; no keys, .env or extraction cache are copied.

  uv run python scripts/build_site.py [out_dir]      (default: site/)
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from itertools import permutations
from pathlib import Path

from fastapi.testclient import TestClient

from ap_automation.config import ROOT, load_config
from ap_automation.runs import hold_codes, load_records, run_info
from ap_automation.ui import server

HOME = str(Path.home())
SCRUB: list[tuple[str, str]] = [(str(ROOT) + "/", ""), (str(ROOT), ".")]


def scrub(text: str) -> str:
    for a, b in SCRUB:
        text = text.replace(a, b)
    return text.replace(HOME, "~")


def main() -> None:
    site = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "site").resolve()
    shutil.rmtree(site, ignore_errors=True)
    api = site / "api"
    api.mkdir(parents=True)

    snap = sqlite3.connect(ROOT / "state/snapshots/submitted.db")  # the submitted runs are the ones in the submitted ledger
    tracked = sorted(r[0] for r in snap.execute("SELECT run_id FROM runs"))
    snap.close()
    tmp = Path(tempfile.mkdtemp())
    SCRUB[:0] = [(str(tmp.resolve()) + "/", ""), (str(tmp) + "/", "")]
    (tmp / "state").mkdir()
    shutil.copyfile(ROOT / "state/snapshots/submitted.db", tmp / "state/ap_ledger.db")
    os.symlink(ROOT / "state/extractions", tmp / "state/extractions")  # read only, for the AI-usage totals
    for r in tracked:
        shutil.copytree(ROOT / "output" / r, tmp / "out" / r)
    policy = tmp / "policy.yaml"
    shutil.copyfile(ROOT / "config/policy.yaml", policy)

    def cfg(**kw):
        kw.setdefault("state_dir", tmp / "state")
        kw.setdefault("out_dir", tmp / "out")
        kw.setdefault("policy_path", policy)
        return load_config(**kw)

    server._cfg = cfg
    server.POLICY = policy
    c = TestClient(server.app)

    def save(rel: str, data) -> None:
        p = api / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(scrub(json.dumps(data)))

    def get(path: str):
        r = c.get(path)
        r.raise_for_status()
        return r

    for name in ("runs", "inboxes", "exceptions", "ledger", "policy", "usage"):
        save(f"{name}.json", get(f"/api/{name}").json())
    from ap_automation.health import run_checks
    from ap_automation.ledger import Ledger

    Ledger(tmp / "state").export_csv()
    status = {"checks": run_checks(state_dir=tmp / "state", ping=False)}
    status["checks"] = [ch for ch in status["checks"] if "credential" not in ch["message"].lower()]
    status["checks"].append({"ok": True, "message": "Read-only demo: showing the submitted runs. The AI and the rules run in the local app.", "fix": ""})
    status["ok"] = all(ch["ok"] for ch in status["checks"])
    save("status.json", status)
    (api / "ledger").mkdir(exist_ok=True)
    (api / "ledger/register.csv").write_text(scrub(get("/api/ledger/register.csv").text))

    index = []
    for run in get("/api/runs").json():
        rid = run["run_id"]
        save(f"runs/{rid}.json", get(f"/api/runs/{rid}").json())
        for f in run["files"]:
            r = c.get(f"/api/runs/{rid}/file/{f}")
            if r.status_code == 404:  # not a download (e.g. run_meta.json)
                continue
            r.raise_for_status()
            dst = api / "runs" / rid / "file" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            body = r.content
            dst.write_bytes(scrub(body.decode()).encode() if f.endswith((".csv", ".html", ".md", ".jsonl")) else body)
        rdir = tmp / "out" / rid
        info = run_info(rdir)
        for rec in load_records(rdir):
            fn = rec["file_name"]
            r = c.get(f"/api/source/{rid}/{fn}")
            if r.status_code == 200:
                dst = api / "source" / rid / fn
                dst.parent.mkdir(parents=True, exist_ok=True)
                if "json" in r.headers.get("content-type", ""):
                    dst.with_name(fn + ".json").write_text(scrub(r.text))
                else:
                    dst.write_bytes(r.content)
            if not info["what_if"] and rec["decision"] != "ALREADY_PROCESSED":
                index.append({"run_id": rid, "inbox_name": info["inbox_name"], "file_name": fn, "vendor_name": rec["vendor_name"],
                              "bill_no": rec["bill_no"], "amount": rec["amount"], "decision": rec["decision"], "codes": hold_codes(rec),
                              "hay": " ".join(str(x or "") for x in (fn, rec["vendor_name"], rec["vendor_id"], rec["bill_no"], rec["project_id"],
                                                                        rec["reference_no"], rec["decision"], " ".join(hold_codes(rec)))).lower()})
    seen, dedup = set(), []
    for h in index:  # newest run first, one hit per file (as the server's search does)
        if h["file_name"] not in seen:
            seen.add(h["file_name"])
            dedup.append(h)
    save("search_index.json", dedup)
    for a, b in permutations(tracked, 2):
        save(f"diff/{a}__{b}.json", get(f"/api/diff?a={a}&b={b}").json())

    static = Path(server.__file__).parent / "static"
    for f in ("app.css", "app.js"):
        shutil.copyfile(static / f, site / f)
    html = (static / "index.html").read_text().replace('<script src="app.js"></script>',
                                                       '<script>window.AP_STATIC = true;</script>\n  <script src="app.js"></script>')
    (site / "index.html").write_text(html)
    (site / ".nojekyll").write_text("")
    shutil.rmtree(tmp)

    leaks = [p for p in site.rglob("*") if p.is_file() and p.suffix not in (".pdf", ".xlsx", ".png", ".jpg")
             and any(s in p.read_text(errors="ignore") for s in (HOME, "sk-ant", "/var/folders", "/private/"))]
    if leaks:
        raise SystemExit(f"refusing: local paths or key-like text in {leaks}")
    n = sum(1 for p in site.rglob("*") if p.is_file())
    print(f"built {site} ({n} files)")


if __name__ == "__main__":
    main()
