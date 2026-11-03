"""Small pure helpers: money, dates, text normalisation."""
from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CENT = Decimal("0.01")


def money(x) -> Decimal:
    """Convert a number/str to Decimal cents. Floats go through repr to avoid binary noise."""
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        d = x
    elif isinstance(x, float):
        d = Decimal(repr(x))
    else:
        s = str(x).replace("$", "").replace(",", "").strip()
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()")
        d = Decimal(s) if s else Decimal("0")
        if neg:
            d = -d
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(d: Decimal | None) -> str:
    return "" if d is None else f"{d:,.2f}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(s) -> date | None:
    if s is None or s == "":
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def us_date(d: date | None) -> str:
    return "" if d is None else d.strftime("%m/%d/%Y")


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def norm_text(s: str | None) -> str:
    """Lower-case, '&'→'and', collapse whitespace and punctuation."""
    if not s:
        return ""
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_LEGAL_SUFFIXES = {"llc", "inc", "lp", "llp", "co", "corp", "corporation", "company", "ltd", "the"}


def norm_company(s: str | None) -> str:
    return " ".join(w for w in norm_text(s).split() if w not in _LEGAL_SUFFIXES)


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def norm_phone(s: str | None) -> str:
    d = digits(s)
    return d[-10:] if len(d) >= 10 else d


def compact(s: str | None) -> str:
    """Alphanumeric-only upper-case form used for grounding lookups."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def truncate(s: str, n: int = 80) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def project_path(path) -> str:
    """Paths inside the project are stored and shown relative to it, so outputs are the same on every machine."""
    from .config import ROOT

    p = Path(path).resolve()
    return str(p.relative_to(ROOT.resolve())) if p.is_relative_to(ROOT.resolve()) else str(p)
