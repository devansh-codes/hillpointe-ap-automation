"""The registry of processed documents (PLAN §4.6, ADR-0004).

SQLite file `state/ap_ledger.db`. A run reads it into a `LedgerView`, adds this run's
entries in memory (so later documents in the same run see them), and commits everything
in ONE transaction after all outputs are written. `UNIQUE(vendor_id, bill_no_norm)` on
entered_bills is the database-level "never entered twice" control.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .util import money, parse_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, inbox TEXT, extractor TEXT, model TEXT, prompt_version TEXT,
  policy_hash TEXT, git_commit TEXT, docs INTEGER, entered INTEGER, entrata INTEGER, held INTEGER,
  already_processed INTEGER, amount_in TEXT, amount_entered TEXT, amount_entrata TEXT, amount_held TEXT
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, sha256 TEXT, file_name TEXT, doc_kind TEXT, vendor_id TEXT,
  vendor_name TEXT, bill_no_raw TEXT, bill_no_norm TEXT, base_no TEXT, revision TEXT, total TEXT, bill_date TEXT,
  service_period TEXT, decision TEXT, primary_code TEXT, secondary_codes TEXT, route TEXT, confidence TEXT,
  confidence_reason TEXT, returns_sha TEXT, supersedes_sha TEXT, superseded INTEGER DEFAULT 0, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS entered_bills (
  vendor_id TEXT NOT NULL, bill_no_norm TEXT NOT NULL, bill_no_raw TEXT, system TEXT, doc_type TEXT, amount TEXT,
  bill_date TEXT, service_period TEXT, reference TEXT, sha256 TEXT, file_name TEXT, run_id TEXT,
  UNIQUE(vendor_id, bill_no_norm)
);
CREATE TABLE IF NOT EXISTS po_consumption (
  reference TEXT, line_no TEXT, amount TEXT, vendor_id TEXT, bill_no_norm TEXT, sha256 TEXT, run_id TEXT
);
CREATE TABLE IF NOT EXISTS waivers_on_file (
  vendor_id TEXT, project_text TEXT, amount TEXT, through_date TEXT, waiver_type TEXT, sha256 TEXT, file_name TEXT, run_id TEXT
);
"""


@dataclass
class EnteredBill:
    vendor_id: str
    bill_no_norm: str
    bill_no_raw: str
    system: str
    doc_type: str
    amount: Decimal
    bill_date: Optional[date]
    service_period: str
    reference: str
    sha256: str
    file_name: str
    run_id: str
    source: str = "ledger"  # ledger | history


@dataclass
class DocRecord:
    sha256: str
    file_name: str
    vendor_id: str
    bill_no_norm: str
    base_no: str
    decision: str
    primary_code: str
    run_id: str
    superseded: bool = False


@dataclass
class LedgerView:
    entered: list[EnteredBill] = field(default_factory=list)
    documents: list[DocRecord] = field(default_factory=list)
    po_used: list[tuple[str, str, Decimal, str, str]] = field(default_factory=list)  # (reference, line_no, amount, source, bill_no_norm)
    waivers: list[dict] = field(default_factory=list)
    # pending (this run)
    new_entered: list[EnteredBill] = field(default_factory=list)
    new_docs: list[dict] = field(default_factory=list)
    new_po: list[dict] = field(default_factory=list)
    new_waivers: list[dict] = field(default_factory=list)
    supersede_shas: set[str] = field(default_factory=set)

    def all_entered(self) -> list[EnteredBill]:
        return self.entered + self.new_entered

    def prior_doc(self, sha: str, file_name: str | None = None) -> Optional[DocRecord]:
        hits = [d for d in self.documents if d.sha256 == sha and (file_name is None or d.file_name == file_name)]
        return hits[-1] if hits else None

    def held_with_key(self, vendor_id: str, norm: str) -> list[DocRecord]:
        latest: dict[str, DocRecord] = {}
        for d in self.documents:
            latest[d.sha256] = d
        return [d for d in latest.values() if d.vendor_id == vendor_id and norm and (d.bill_no_norm == norm or d.base_no == norm)
                and d.decision == "HELD" and not d.superseded]


class Ledger:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.path = state_dir / "ap_ledger.db"
        self.snap_dir = state_dir / "snapshots"
        state_dir.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    # ---- read -----------------------------------------------------------------------
    def load_view(self) -> LedgerView:
        v = LedgerView()
        with self._conn() as c:
            for r in c.execute("SELECT * FROM entered_bills"):
                v.entered.append(EnteredBill(r["vendor_id"], r["bill_no_norm"], r["bill_no_raw"], r["system"], r["doc_type"],
                                             money(r["amount"]), parse_date(r["bill_date"]), r["service_period"] or "",
                                             r["reference"] or "", r["sha256"], r["file_name"], r["run_id"]))
            for r in c.execute("SELECT * FROM documents ORDER BY id"):
                v.documents.append(DocRecord(r["sha256"], r["file_name"], r["vendor_id"] or "", r["bill_no_norm"] or "",
                                             r["base_no"] or "", r["decision"], r["primary_code"] or "", r["run_id"],
                                             bool(r["superseded"])))
            for r in c.execute("SELECT * FROM po_consumption"):
                v.po_used.append((r["reference"], r["line_no"] or "", money(r["amount"]), f"ledger:{r['run_id']}", r["bill_no_norm"] or ""))
            v.waivers = [dict(r) for r in c.execute("SELECT * FROM waivers_on_file")]
        return v

    def runs(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY started_at")]

    # ---- write (one transaction) -------------------------------------------------------
    def commit(self, view: LedgerView, run_row: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        c = self._conn()
        try:
            c.execute("BEGIN")
            c.execute(f"INSERT INTO runs ({','.join(run_row)}) VALUES ({','.join('?' * len(run_row))})", list(run_row.values()))
            for d in view.new_docs:
                d = {**d, "decided_at": now}
                c.execute(f"INSERT INTO documents ({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
            for e in view.new_entered:
                c.execute("INSERT INTO entered_bills VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (e.vendor_id, e.bill_no_norm, e.bill_no_raw, e.system, e.doc_type, str(e.amount),
                           e.bill_date.isoformat() if e.bill_date else None, e.service_period, e.reference, e.sha256,
                           e.file_name, e.run_id))
            for p in view.new_po:
                c.execute(f"INSERT INTO po_consumption ({','.join(p)}) VALUES ({','.join('?' * len(p))})", list(p.values()))
            for w in view.new_waivers:
                c.execute(f"INSERT INTO waivers_on_file ({','.join(w)}) VALUES ({','.join('?' * len(w))})", list(w.values()))
            for sha in view.supersede_shas:
                c.execute("UPDATE documents SET superseded = 1 WHERE sha256 = ?", (sha,))
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()
        self.export_csv()

    def delete_run(self, run_id: str) -> None:
        """Undo everything one run recorded (one transaction). Callers must only remove the latest run, see runs.delete_run."""
        c = self._conn()
        try:
            c.execute("BEGIN")
            freed = [r[0] for r in c.execute("SELECT supersedes_sha FROM documents WHERE run_id = ? AND supersedes_sha IS NOT NULL "
                                             "AND supersedes_sha != ''", (run_id,))]
            for table in ("documents", "entered_bills", "po_consumption", "waivers_on_file", "runs"):
                c.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
            for sha in freed:
                if not c.execute("SELECT 1 FROM documents WHERE supersedes_sha = ?", (sha,)).fetchone():
                    c.execute("UPDATE documents SET superseded = 0 WHERE sha256 = ?", (sha,))
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()
        self.export_csv()

    def export_csv(self) -> Path:
        out = self.state_dir / "processed_register.csv"
        with self._conn() as c, open(out, "w", newline="") as f:
            rows = list(c.execute("""SELECT d.run_id, d.file_name, d.sha256, d.doc_kind, d.vendor_id, d.vendor_name, d.bill_no_raw,
                d.bill_no_norm, d.total, d.bill_date, d.decision, d.primary_code, d.secondary_codes, d.route, d.confidence,
                d.superseded, d.decided_at FROM documents d ORDER BY d.id"""))
            w = csv.writer(f)
            w.writerow(["run_id", "file_name", "sha256", "doc_kind", "vendor_id", "vendor_name", "bill_no", "dup_key",
                        "amount", "bill_date", "decision", "primary_code", "secondary_codes", "route", "confidence",
                        "superseded", "decided_at"])
            for r in rows:
                w.writerow(list(r))
        return out

    # ---- snapshots ------------------------------------------------------------------------
    def snapshot(self, name: str) -> Path:
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        dst = self.snap_dir / f"{name}.db"
        src = sqlite3.connect(self.path)
        dst_c = sqlite3.connect(dst)
        with dst_c:
            src.backup(dst_c)
        src.close()
        dst_c.close()
        return dst

    def restore(self, name: str) -> None:
        src = self.snap_dir / f"{name}.db"
        if not src.exists():
            raise FileNotFoundError(f"no snapshot named '{name}' (have: {', '.join(self.list_snapshots()) or 'none'})")
        shutil.copyfile(src, self.path)
        self.export_csv()

    def list_snapshots(self) -> list[str]:
        return sorted(p.stem for p in self.snap_dir.glob("*.db")) if self.snap_dir.exists() else []

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
        with self._conn() as c:
            c.executescript(SCHEMA)
        self.export_csv()
