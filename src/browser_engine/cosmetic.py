"""Cosmetic (element-hiding) rules → host-scoped CSS.

EasyList's ``##`` / ``#@#`` selectors are element-hiding rules, not network
rules — MV3 declarativeNetRequest can't express them, so they have to reach the
renderer as CSS. ``cosmetic_css`` turns a compiled cosmetic rule set into one
stylesheet for a single host: domain-scoped rules contribute only when the host
is in scope, and a matching ``#@#`` exception removes the selector entirely.
"""


import re
from typing import Iterable

from .rule_engine import RuleEngine


# ABP-only extended syntax. Not valid CSS: one bad selector invalidates the
# whole comma-joined rule, so these are dropped before they reach the sheet.
_ABP_ONLY = re.compile(r":(-abp-[a-z-]+|has-text|matches-[a-z-]+|xpath|upward"
                       r"|nth-ancestor|watch-attr|min-text-length|remove)\b|:has-text\(")


def _is_plain_css(selector: str) -> bool:
    return not _ABP_ONLY.search(selector)


def cosmetic_css(rules: Iterable[dict], host: str) -> str:
    """CSS that hides every applicable element on ``host`` (empty if none)."""
    rules = [r for r in rules if _is_plain_css(r["selector"])]
    # Pass 1: which selectors does a #@# exception cancel on this host?
    # An exception cancels the selector itself, regardless of which hide rule
    # introduced it (a scoped exception still cancels a generic hide rule).
    cancelled: set = set()
    for rule in rules:
        for ex in rule.get("exceptions") or []:
            if ex == "" or RuleEngine.match_domain(host, ex):
                cancelled.add(rule["selector"])
    # Pass 2: keep the hide rules the host is in scope for, minus cancellations.
    hidden: list[str] = []
    for rule in rules:
        domains = rule.get("domains") or []
        if domains and not any(RuleEngine.match_domain(host, d) for d in domains):
            continue
        if rule["selector"] in cancelled:
            continue
        hidden.append(rule["selector"])
    if not hidden:
        return ""
    return ",\n".join(hidden) + " {\n  display: none !important;\n}\n"
