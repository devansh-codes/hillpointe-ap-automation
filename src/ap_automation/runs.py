"""Reading finished runs back from output/ (shared by the CLI `explain` / `diff` and the web UI)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .config import ROOT, Config

_RUN_RE = re.compile(r"^(\d{8})-(\d{9})_(.+?)(_whatif)?$")


class RunNotFound(LookupError):
    pass


def run_dirs(cfg: Config) -> list[Path]:
    out = cfg.output_dir
    return sorted(p for p in out.iterdir() if (p / "decisions.jsonl").exists()) if out.exists() else []


def find_run(cfg: Config, run_id: Optional[str]) -> Path:
    runs = run_dirs(cfg)
    if not runs:
        raise RunNotFound("No runs found.")
    if not run_id:
        return max(runs, key=lambda q: q.stat().st_mtime)
    cand = [p for p in runs if p.name == run_id or p.name.startswith(run_id)]
    if not cand:
        raise RunNotFound(f"Run {run_id} not found. Available: {', '.join(p.name for p in runs[-8:])}")
    return cand[-1]


def load_records(run_dir: Path) -> list[dict]:
    return [json.loads(l) for l in (run_dir / "decisions.jsonl").read_text().splitlines() if l.strip()]


def load_run(cfg: Config, run_id: Optional[str]) -> tuple[str, list[dict]]:
    p = find_run(cfg, run_id)
    return p.name, load_records(p)


def run_info(run_dir: Path) -> dict:
    """Run metadata: from run_meta.json when present, otherwise parsed from the folder name."""
    meta_p = run_dir / "run_meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    m = _RUN_RE.match(run_dir.name)
    inbox_name = meta.get("inbox_name") or (m.group(3) if m else run_dir.name)
    started = meta.get("started_at")
    if not started and m:
        d, t = m.group(1), m.group(2)
        started = f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:6]}"
    return {
        "run_id": run_dir.name,
        "inbox_name": inbox_name,
        "inbox": meta.get("inbox") or str(resolve_inbox(inbox_name) or ""),
        "what_if": bool(meta.get("what_if", run_dir.name.endswith("_whatif"))),
        "started_at": started,
        "extractor": meta.get("extractor", ""),
        "policy_hash": meta.get("policy_hash", ""),
        "note": meta.get("note", ""),
    }


def resolve_inbox(name: str) -> Optional[Path]:
    """Find an inbox folder by name in the usual places (for runs made before run_meta.json existed)."""
    for base in (ROOT, ROOT / "inbox", ROOT / "tests/synthetic"):
        p = base / name
        if p.is_dir():
            return p
    return None


def hold_codes(rec: dict) -> list[str]:
    return sorted({f["code"] for f in rec["findings"] if f["hold"]})


def _sig(r: dict):
    return (r["decision"], ",".join(hold_codes(r)), "; ".join(r["approvers"]),
            sum(float(l["amount"]) for l in r["bill_lines"]) if r["bill_lines"] else None)


def compare_runs(a: list[dict], b: list[dict]) -> list[dict]:
    """One row per document whose decision, hold codes, approvers or coded amount differ between two runs."""
    A, B = {r["file_name"]: r for r in a}, {r["file_name"]: r for r in b}
    rows = []
    for f in sorted(set(A) | set(B)):
        x, y = A.get(f), B.get(f)
        if x is None or y is None:
            rows.append({"file_name": f, "before": x and x["decision"] or "—", "after": y and y["decision"] or "—",
                         "why": ["only in one run"]})
            continue
        sx, sy = _sig(x), _sig(y)
        if sx == sy:
            continue
        why = []
        if sx[0] != sy[0]:
            why.append(f"decision {sx[0]} → {sy[0]}")
        if sx[1] != sy[1]:
            why.append(f"codes [{sx[1]}] → [{sy[1]}]")
        if sx[2] != sy[2]:
            why.append(f"approvers '{sx[2]}' → '{sy[2]}'")
        new = [fd["message"] for fd in y["findings"] if fd["hold"] and fd["code"] not in sx[1].split(",")]
        gone = [fd["message"] for fd in x["findings"] if fd["hold"] and fd["code"] not in sy[1].split(",")]
        if new:
            why.append("new: " + new[0][:160])
        if gone:
            why.append("cleared: " + gone[0][:160])
        rows.append({"file_name": f, "before": f"{sx[0]} {sx[1]}".strip(), "after": f"{sy[0]} {sy[1]}".strip(), "why": why})
    return rows
