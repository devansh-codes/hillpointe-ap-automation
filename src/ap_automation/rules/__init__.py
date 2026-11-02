"""Rule registry (ADR-0005). Each rule: (ctx) -> list[Finding]. Order and on/off come from policy.yaml `rules:`.

To add a rule: copy _TEMPLATE.py, give it a name with @rule("name"), import it below, and add the name to
policy.yaml `rules:`. Run `uv run ap policy validate`.
"""
from __future__ import annotations

from typing import Callable

RULES: dict[str, Callable] = {}


def rule(name: str):
    def deco(fn):
        RULES[name] = fn
        fn.rule_name = name
        return fn
    return deco


from . import core  # noqa: E402,F401  (registers the built-in rules)
from . import custom  # noqa: E402,F401  (registers rules added for local policy changes)
