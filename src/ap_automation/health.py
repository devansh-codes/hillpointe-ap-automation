"""Pre-flight checks (shared by `ap doctor` and the web UI's System check)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from .config import PolicyError, load_config


def run_checks(state_dir: Optional[Path] = None, ping: bool = True) -> list[dict]:
    out: list[dict] = []

    def line(passed: bool, msg: str, fix: str = "") -> None:
        out.append({"ok": bool(passed), "message": msg, "fix": fix})

    line(sys.version_info >= (3, 12), f"Python {sys.version.split()[0]}", "install Python 3.12+ (uv does this: uv sync)")
    try:
        cfg = load_config(state_dir=state_dir)
        line(True, f"policy.yaml valid (hash {cfg.policy_hash})")
    except PolicyError as e:
        line(False, f"policy.yaml invalid: {e}", "fix the listed keys")
        return out
    from .reference import load_master_data
    try:
        md = load_master_data(cfg.path("master_data"), cfg.path("history"))
        line(True, f"Master data: {len(md.vendors)} vendors, {len(md.projects)} projects, open period(s) {md.open_periods((cfg.policy.get('periods') or {}).get('open_period_override'))}, {len(md.history)} history bills")
        line(abs(sum(md.allocation.values()) - 1) < 1e-9, f"Allocation_Table sums to {sum(md.allocation.values()):.2f}")
    except Exception as e:  # noqa: BLE001
        line(False, f"Master data / history failed to load: {e}")
    from .emit import _template_cols
    try:
        imp, ent = _template_cols(cfg)
        line(len(imp) == 19 and len(ent) == 14, f"Import template: {len(imp)} Intacct columns, {len(ent)} Entrata columns")
    except Exception as e:  # noqa: BLE001
        line(False, f"Template failed to load: {e}")
    refs = [p for d in cfg.reference_dirs for p in d.glob("*") if p.is_file()]
    line(bool(refs), f"{len(refs)} reference documents (POs / subcontracts / agreements)")
    from .extract import CacheStore, intake
    cache = CacheStore(cfg)
    missing = [p.name for p in refs if not cache.get(intake(p).sha256, "reference")]
    line(True, f"Reference docs cached: {len(refs) - len(missing)}/{len(refs)}" + (f" (will be read on first run: {', '.join(missing)})" if missing else ""))
    from .ledger import Ledger
    led = Ledger(cfg.state_dir)
    runs = led.runs()
    view = led.load_view()
    line(True, f"Ledger {led.path}: {len(runs)} runs, {len(view.entered)} entered bills, snapshots: {', '.join(led.list_snapshots()) or 'none'}")
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    line(bool(key), "Anthropic credentials found", "export ANTHROPIC_API_KEY=... (needed for documents not in the cache)")
    if key and ping:
        try:
            import anthropic

            r = anthropic.Anthropic(max_retries=1).messages.create(model=cfg.settings["extraction"]["model"], max_tokens=16,
                                                                    messages=[{"role": "user", "content": "Reply OK"}])
            line(True, f"Model {cfg.settings['extraction']['model']} reachable (stop_reason={r.stop_reason})")
        except Exception as e:  # noqa: BLE001
            line(False, f"Model call failed: {type(e).__name__}: {str(e)[:150]}", "check key / network / model name")
    return out
