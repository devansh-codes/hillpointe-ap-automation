"""Load and validate settings.yaml and policy.yaml."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

KNOWN_CODES = {"DUP", "NOPO", "OVERPO", "UNAPPCO", "LIEN", "COI", "NEWVEND", "BANKCHG", "OTHER"}


class PolicyError(ValueError):
    pass


@dataclass
class Config:
    root: Path
    settings: dict[str, Any]
    policy: dict[str, Any]
    policy_hash: str

    def path(self, key: str) -> Path:
        return self.root / self.settings["paths"][key]

    @property
    def reference_dirs(self) -> list[Path]:
        return [self.root / p for p in self.settings["paths"]["reference_docs"]]

    @property
    def state_dir(self) -> Path:
        return self.root / self.settings["paths"]["state_dir"]

    @property
    def output_dir(self) -> Path:
        return self.root / self.settings["paths"]["output_dir"]

    def route(self, code: str) -> str:
        return self.policy["exception_codes"].get(code, {}).get("route", "AP Manager")


def load_config(root: Path | None = None, policy_path: Path | None = None, state_dir: Path | None = None,
                out_dir: Path | None = None) -> Config:
    root = root or ROOT
    settings = yaml.safe_load((root / "config/settings.yaml").read_text())
    ppath = policy_path or (root / "config/policy.yaml")
    raw = ppath.read_bytes()
    policy = yaml.safe_load(raw)
    if state_dir is not None:
        settings["paths"]["state_dir"] = str(state_dir)
    if out_dir is not None:
        settings["paths"]["output_dir"] = str(out_dir)
    validate_policy(policy)
    return Config(root=root, settings=settings, policy=policy, policy_hash=hashlib.sha256(raw).hexdigest()[:12])


def validate_policy(p: dict[str, Any]) -> list[str]:
    """Raise PolicyError with every problem found (so a live edit gets one clear message)."""
    from .rules import RULES  # local import to avoid a cycle

    errors: list[str] = []

    def num(path: str, value: Any, minimum: float | None = 0) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path} must be a number (got {value!r})")
        elif minimum is not None and value < minimum:
            errors.append(f"{path} must be >= {minimum} (got {value})")

    for key in ("routing", "exception_codes", "exception_precedence", "approvals", "rules", "overpo", "dup"):
        if key not in p:
            errors.append(f"missing top-level key: {key}")
    if errors:
        raise PolicyError("\n".join(errors))

    num("overpo.tolerance", p["overpo"].get("tolerance"))
    num("coi.grace_days", p.get("coi", {}).get("grace_days", 0))
    num("dup.near_date_days", p["dup"].get("near_date_days", 7))
    num("price_variance.tolerance_pct", p.get("price_variance", {}).get("tolerance_pct", 0.5))
    if p.get("price_variance", {}).get("action", "warn") not in ("warn", "hold"):
        errors.append("price_variance.action must be 'warn' or 'hold'")
    if not all(isinstance(x, str) for x in p["dup"].get("strip_prefixes", [])):
        errors.append("dup.strip_prefixes must be quoted strings (YAML reads bare NO/YES/ON/OFF as booleans)")
    if p["dup"].get("revision_after_entered_code", "DUP") not in KNOWN_CODES | set(p["exception_codes"]):
        errors.append("dup.revision_after_entered_code must be an exception code")

    a = p["approvals"]
    for cat, key in (("construction", "when_gross_work_over"), ("stabilized", "when_invoice_over"), ("corporate", "when_bill_over")):
        if cat not in a:
            errors.append(f"approvals.{cat} missing")
            continue
        add = a[cat].get("additional")
        if add:
            num(f"approvals.{cat}.additional.{key}", add.get(key))

    for code, spec in p["exception_codes"].items():
        if not isinstance(spec, dict) or "route" not in spec:
            errors.append(f"exception_codes.{code} needs a 'route'")
    for code in p["exception_precedence"]:
        if code not in p["exception_codes"]:
            errors.append(f"exception_precedence lists unknown code {code}")
    for code in p["exception_codes"]:
        if code not in p["exception_precedence"]:
            errors.append(f"exception code {code} is missing from exception_precedence")

    for name in p["rules"]:
        if name not in RULES:
            errors.append(f"rules: unknown rule '{name}' (known: {', '.join(sorted(RULES))})")

    for status, r in p["routing"].items():
        if r.get("category") not in ("construction", "stabilized", "corporate"):
            errors.append(f"routing['{status}'].category must be construction|stabilized|corporate")

    for vid, ov in (p.get("vendor_overrides") or {}).items():
        if "terms" in ov and not str(ov["terms"]).lower().startswith("net "):
            errors.append(f"vendor_overrides.{vid}.terms must look like 'Net 30'")

    opo = (p.get("periods") or {}).get("open_period_override")
    if opo is not None:
        import re

        if not re.fullmatch(r"\d{4}-\d{2}", str(opo)):
            errors.append("periods.open_period_override must be YYYY-MM or null")

    if errors:
        raise PolicyError("\n".join(errors))
    return []
