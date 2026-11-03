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
        "inbox": str(ROOT / meta["inbox"]) if meta.get("inbox") and not Path(meta["inbox"]).is_absolute()
                 else meta.get("inbox") or str(resolve_inbox(inbox_name) or ""),
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


_LINE = ("acct", "loc", "dept", "project", "task", "cost_type", "amount")
_ENTRATA = ("gl", "amount", "post_month", "due_date", "approver")


def _detail_changes(x: dict, y: dict) -> list[str]:
    """What else a rule change can move besides the decision: bill header (terms, dates, doc type), each coded line,
    Entrata rows, the route. Fields that one of the runs didn't record (older runs) are not compared."""
    out = []
    hx, hy = x.get("bill_header") or {}, y.get("bill_header") or {}
    out += [f"{f.replace('_', ' ')} {hx[f]} → {hy[f]}" for f in hx if f in hy and hx[f] != hy[f]]
    if x["bill_lines"] and y["bill_lines"]:
        if [tuple(l.get(k) for k in _LINE) for l in x["bill_lines"]] != [tuple(l.get(k) for k in _LINE) for l in y["bill_lines"]]:
            out.append("coding lines changed")
    ex, ey = x["entrata_rows"], y["entrata_rows"]
    if ex and ey:
        keys = [k for k in _ENTRATA if all(k in e for e in ex + ey)]
        if [tuple(e[k] for k in keys) for e in ex] != [tuple(e[k] for k in keys) for e in ey]:
            out.append("Entrata " + ", ".join(dict.fromkeys(f"{k.replace('_', ' ')} {a[k]} → {b[k]}" for a, b in zip(ex, ey) for k in keys if a[k] != b[k]))
                       if len(ex) == len(ey) else "Entrata rows changed")
    if "route" in x and "route" in y and x["route"] != y["route"]:
        out.append(f"route '{x['route']}' → '{y['route']}'")
    return out


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
        detail = _detail_changes(x, y)
        if sx == sy and not detail:
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
        why += detail
        rows.append({"file_name": f, "before": f"{sx[0]} {sx[1]}".strip(), "after": f"{sy[0]} {sy[1]}".strip(), "why": why})
    return rows


# ---- deleting a run ------------------------------------------------------------------------
class RunDeleteRefused(RuntimeError):
    pass


def delete_impact(cfg: Config, run_id: str) -> dict:
    """What deleting this run would undo, and whether it is allowed (shown to the user before they confirm)."""
    from .ledger import Ledger

    p = find_run(cfg, run_id)
    info = run_info(p)
    recorded = [r["run_id"] for r in Ledger(cfg.state_dir).runs()]
    in_ledger = p.name in recorded
    later = recorded[recorded.index(p.name) + 1:] if in_ledger else []
    recs = load_records(p)
    entered = [r for r in recs if r["decision"] in ("ENTERED", "ENTRATA_HANDOFF")]
    return {
        "run_id": p.name, "inbox_name": info["inbox_name"], "what_if": info["what_if"], "recorded": in_ledger,
        "documents": len(recs), "entered": len(entered),
        "entered_amount": f"{sum(sum(float(l['amount']) for l in r['bill_lines']) for r in entered):.2f}",
        "held": sum(r["decision"] in ("HELD", "NOT_A_BILL") for r in recs),
        "later_runs": later,
        "blocked": (f"{len(later)} later run{'s were' if len(later) > 1 else ' was'} decided on top of this one. "
                    "Delete the later runs first, newest first, or restore a ledger snapshot.") if later else "",
    }


def delete_run(cfg: Config, run_id: str, actor: str = "") -> dict:
    """Remove a run: undo its ledger records and archive its output folder. Only the latest recorded run can go,
    because later runs' decisions (duplicates, PO balances, waivers on file) depended on it. Reversible: a ledger
    snapshot is taken first and the folder is moved to state/deleted_runs/, not erased. Every delete is audit-logged."""
    import shutil
    from datetime import datetime, timezone

    from .ledger import Ledger

    imp = delete_impact(cfg, run_id)
    if imp["blocked"]:
        raise RunDeleteRefused(imp["blocked"])
    ledger, src = Ledger(cfg.state_dir), find_run(cfg, run_id)
    snap = ""
    if imp["recorded"]:
        snap = f"before-delete-{src.name}"
        ledger.snapshot(snap)
        ledger.delete_run(src.name)
    archive = cfg.state_dir / "deleted_runs"
    archive.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), archive / src.name)
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": "delete_run", "actor": actor,
             **{k: imp[k] for k in ("run_id", "inbox_name", "what_if", "recorded", "documents", "entered", "entered_amount")},
             "ledger_snapshot": snap, "archived_to": str(archive / src.name)}
    with open(cfg.state_dir / "audit_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
