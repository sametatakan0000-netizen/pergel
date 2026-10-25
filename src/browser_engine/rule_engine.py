"""MV3-style declarative rule engine with a rule-quota-breaking domain index.

Product decisions (docs/rea/positioning-synthesis.md §7, #2 and #9): MV3's
declarativeNetRequest caps static rules at 30k/extension (330k global) — large
blocklists do not fit. This engine compiles an unbounded rule list into a
per-domain index so matching is O(candidates) instead of O(all rules), and it
carries the blocking/redirect/header actions we need for the super-extension
layer.

This is a pure data-plane evaluator: it decides what to do with a request. It
does not intercept traffic and performs no network I/O of its own.

Action precedence (matching DNR semantics): ``allow`` beats ``block`` beats
``redirect``/``modifyHeaders``, regardless of numeric priority; within the same
action class the higher ``priority`` wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# Action-class rank for precedence: lower number = higher precedence.
_ACTION_RANK = {"allow": 0, "block": 1, "modifyHeaders": 2, "redirect": 2}


@dataclass
class Decision:
    action: str
    rule_id: Optional[int] = None
    priority: int = 0
    redirect_url: Optional[str] = None

    def __post_init__(self) -> None:
        if self.action not in _ACTION_RANK:
            raise ValueError(f"unknown action: {self.action!r}")


class RuleEngine:
    """Matches request hosts against subdomain patterns.

    A pattern matches a request host when the pattern is the host itself or a
    parent domain of the host (``ad.doubleclick.net`` matches pattern
    ``doubleclick.net``). A more specific pattern never matches a broader host.
    """

    @staticmethod
    def match_domain(host: str, pattern: str) -> bool:
        host = host.lower().rstrip(".")
        pattern = pattern.lower().rstrip(".")
        return host == pattern or host.endswith("." + pattern)

    def __init__(self, rules: Optional[Iterable[dict]] = None) -> None:
        self._rules: list[dict] = []
        # Domain index: request-domain pattern -> list of rules mentioning it.
        self._by_domain: dict[str, list[dict]] = {}
        # Rules with no requestDomains restriction (match any host).
        self._global: list[dict] = []
        # Diagnostics: how many candidate rules the last check() actually walked.
        self.last_candidate_count: int = 0
        for rule in rules or ():
            self._add(rule)

    def _add(self, rule: dict) -> None:
        self._rules.append(rule)
        domains = (rule.get("condition") or {}).get("requestDomains") or []
        if not domains:
            self._global.append(rule)
            return
        for dom in domains:
            self._by_domain.setdefault(dom.lower().rstrip("."), []).append(rule)

    def check(self, url: str, resource_type: str = "other") -> Decision:
        host = _host_of(url)
        candidates = list(self._global)
        seen: set[int] = {id(r) for r in candidates}
        # Only index lookups along the host's suffix chain (host, parent,
        # grandparent, ...) can match a requestDomains pattern — this keeps the
        # walk O(labels) instead of O(index size).
        labels = host.split(".") if host else []
        for i in range(len(labels)):
            dom = ".".join(labels[i:])
            for rule in self._by_domain.get(dom, ()):
                if id(rule) not in seen:
                    seen.add(id(rule))
                    candidates.append(rule)
        self.last_candidate_count = len(candidates)

        best: Optional[dict] = None
        best_rank = 99
        best_prio = -1
        for rule in candidates:
            if not _type_matches(rule, resource_type):
                continue
            action = (rule.get("action") or {}).get("type", "block")
            rank = _ACTION_RANK.get(action, 1)
            prio = int(rule.get("priority", 0))
            if best is None or (rank, -prio) < (best_rank, -best_prio):
                best = rule
                best_rank = rank
                best_prio = prio

        if best is None:
            return Decision("allow")
        action = (best.get("action") or {}).get("type", "block")
        redirect_url = ((best.get("action") or {}).get("redirect") or {}).get("url")
        return Decision(action, rule_id=best.get("id"), priority=int(best.get("priority", 0)),
                        redirect_url=redirect_url)


def compile_rules(rules: Iterable[dict]) -> RuleEngine:
    """Compile a rule list into a queryable engine (the expensive index build)."""
    return RuleEngine(rules)


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def _type_matches(rule: dict, resource_type: str) -> bool:
    types = (rule.get("condition") or {}).get("resourceTypes") or []
    return not types or resource_type in types
