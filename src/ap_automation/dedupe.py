"""Bill-number normalisation and duplicate keys (PLAN §4.1)."""
from __future__ import annotations

import re

REVISION_RE = re.compile(r"^(?P<base>.+?)[\s_-]*(?:R(?P<r>\d+)|REV(?P<rv>\d*)|REVISED)$", re.I)


def norm_bill_no(raw: str | None, prefixes: list[str] | tuple[str, ...] = ("INVOICE", "INV", "BILL", "NO")) -> str:
    """'INV-00417' -> '417', 'inv 123' -> '123', 'GCP-0303' -> 'GCP0303'.

    Prefixes are stripped only when what follows is numeric, so 'INVX-12' or 'NOVA-1' survive.
    """
    s = re.sub(r"[^A-Z0-9]", "", (raw or "").upper())
    prefixes = [str(p).upper() for p in prefixes if isinstance(p, str)]
    changed = True
    while changed:
        changed = False
        for p in sorted(prefixes, key=len, reverse=True):
            if s.startswith(p) and len(s) > len(p) and s[len(p)].isdigit():
                s, changed = s[len(p):], True
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


def numeric_core(raw: str | None) -> str:
    d = re.sub(r"\D", "", raw or "")
    return d.lstrip("0") or ("0" if d else "")


def split_revision(raw: str | None) -> tuple[str, str]:
    """'INV-123-R1' -> ('INV-123', 'R1'); 'HPA-31877' -> ('HPA-31877', '')."""
    s = (raw or "").strip()
    m = REVISION_RE.match(s)
    if m and re.search(r"\d", m.group("base")):
        rev = m.group("r") and f"R{m.group('r')}" or (m.group("rv") is not None and f"REV{m.group('rv')}") or "REVISED"
        return m.group("base"), rev
    return s, ""
