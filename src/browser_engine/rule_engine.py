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

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .aho_corasick import AhoCorasick

# Action-class rank for precedence: lower number = higher precedence.
_ACTION_RANK = {"allow": 0, "block": 1, "modifyHeaders": 2, "redirect": 2}

_HEADER_OPS = {"set", "remove", "append"}


@dataclass
class Decision:
    action: str
    rule_id: Optional[int] = None
    priority: int = 0
    redirect_url: Optional[str] = None
    request_header_ops: list = field(default_factory=list)
    response_header_ops: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.action not in _ACTION_RANK:
            raise ValueError(f"unknown action: {self.action!r}")

    def apply_to_headers(self, headers: dict, *, response: bool) -> dict:
        """Return a new dict with this decision's header ops applied.

        ``headers`` is left untouched. ``append`` joins with ``", "``.
        """
        out = dict(headers)
        ops = self.response_header_ops if response else self.request_header_ops
        for op in ops:
            name = op["header"]
            operation = op["operation"]
            if operation == "remove":
                out.pop(name, None)
            elif operation == "set":
                out[name] = op.get("value", "")
            elif operation == "append":
                value = op.get("value", "")
                out[name] = f"{out[name]}, {value}" if name in out else value
        return out


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
        # Build-time-compiled matchers, keyed by id(rule) (dicts are unhashable).
        self._compiled_regex: dict[int, "re.Pattern"] = {}
        # Literal-only global filters, matched in one Aho-Corasick pass.
        self._literal: list[tuple[str, dict]] = []
        self._literal_by_pattern: dict[str, list[dict]] = {}
        self._literal_matcher: Optional[AhoCorasick] = None
        self._literal_dirty = False
        # Diagnostics: how many candidate rules the last check() actually walked.
        self.last_candidate_count: int = 0
        for rule in rules or ():
            self._add(rule)

    def _add(self, rule: dict) -> None:
        action = rule.get("action") or {}
        _validate_header_ops(action.get("requestHeaders"), rule.get("id"))
        _validate_header_ops(action.get("responseHeaders"), rule.get("id"))
        cond = rule.get("condition") or {}
        regex = cond.get("regexFilter")
        url_filter = cond.get("urlFilter")
        anchor = _url_filter_anchor(url_filter)
        if regex is not None:
            _regex_is_safe(regex)
            self._compiled_regex[id(rule)] = re.compile(regex)
        elif url_filter is not None:
            self._compiled_regex[id(rule)] = re.compile(_url_filter_to_regex(url_filter))
        self._rules.append(rule)
        domains = list(cond.get("requestDomains") or [])
        if anchor and not domains:
            domains = [anchor]
        if domains:
            for dom in domains:
                self._by_domain.setdefault(dom.lower().rstrip("."), []).append(rule)
        elif url_filter is not None and anchor is None and _is_literal_filter(url_filter):
            # Pure substring, no wildcard/anchor: one Aho-Corasick pass covers all.
            self._literal.append((url_filter, rule))
            self._literal_by_pattern.setdefault(url_filter, []).append(rule)
            self._literal_dirty = True
        else:
            self._global.append(rule)

    def check(self, url: str, resource_type: str = "other") -> Decision:
        best = self._best_candidate(url, _host_of(url), resource_type)
        if best is None:
            return Decision("allow")
        action = (best.get("action") or {}).get("type", "block")
        redirect_url = ((best.get("action") or {}).get("redirect") or {}).get("url")
        return Decision(
            action,
            rule_id=best.get("id"),
            priority=int(best.get("priority", 0)),
            redirect_url=redirect_url,
            request_header_ops=list((best.get("action") or {}).get("requestHeaders") or []),
            response_header_ops=list((best.get("action") or {}).get("responseHeaders") or []),
        )

    def _best_candidate(self, url: str, host: str,
                        resource_type: str) -> Optional[dict]:
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
            if not self._matches(rule, url, host, resource_type):
                continue
            best, best_rank, best_prio = self._prefer(best, best_rank, best_prio, rule)
        # Literal-only filters: one Aho-Corasick pass finds every pattern.
        if self._literal_by_pattern:
            if self._literal_dirty:
                self._literal_matcher = AhoCorasick(self._literal_by_pattern)
                self._literal_dirty = False
            for pattern in self._literal_matcher.find(url):
                for rule in self._literal_by_pattern[pattern]:
                    if _type_matches(rule, resource_type):
                        best, best_rank, best_prio = self._prefer(best, best_rank, best_prio, rule)
        return best

    @staticmethod
    def _prefer(best, best_rank, best_prio, rule):
        action = (rule.get("action") or {}).get("type", "block")
        rank = _ACTION_RANK.get(action, 1)
        prio = int(rule.get("priority", 0))
        if best is None or (rank, -prio) < (best_rank, -best_prio):
            return rule, rank, prio
        return best, best_rank, best_prio

    def _matches(self, rule: dict, url: str, host: str, resource_type: str) -> bool:
        cond = rule.get("condition") or {}
        if not _type_matches(rule, resource_type):
            return False
        domains = cond.get("requestDomains") or []
        if domains and not any(RuleEngine.match_domain(host, d) for d in domains):
            return False
        if cond.get("urlFilter") is None and cond.get("regexFilter") is None:
            return True
        matcher = self._compiled_regex.get(id(rule))
        return matcher is not None and matcher.search(url) is not None


def compile_rules(rules: Iterable[dict]) -> RuleEngine:
    """Compile a rule list into a queryable engine (the expensive index build)."""
    return RuleEngine(rules)


def _validate_header_ops(ops: Optional[list], rule_id) -> None:
    if not ops:
        return
    for op in ops:
        operation = op.get("operation")
        if operation not in _HEADER_OPS:
            raise ValueError(
                f"rule {rule_id}: unknown header operation {operation!r} "
                f"(expected one of {sorted(_HEADER_OPS)})")


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit
    return (urlsplit(url).hostname or "").lower().rstrip(".")


_UNSAFE_REGEX_PATTERNS = (
    re.compile(r"\([^()]*[*+][^()]*\)[*+{]"),   # nested quantifier: (a+)+
    re.compile(r"\([^()]*\|[^()]*\)[*+{]"),     # quantified alternation: (a|a)*
)


def _regex_is_safe(pattern: str) -> None:
    """Reject regexes prone to catastrophic backtracking (MV3 'unsafe regex')."""
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regexFilter {pattern!r}: {exc}") from exc
    for unsafe in _UNSAFE_REGEX_PATTERNS:
        if unsafe.search(pattern):
            raise ValueError(f"unsafe regexFilter {pattern!r}: nested or alternating quantifier")


def _url_filter_to_regex(pattern: str) -> str:
    """Translate an AdBlock-style urlFilter into a regex.

    ``*`` -> any run, ``^`` -> separator or end, leading ``||`` -> domain anchor,
    leading/trailing ``|`` -> string start/end. Everything else is literal.
    """
    out = []
    i = 0
    if pattern.startswith("||"):
        out.append(r"^[a-z][a-z0-9+.-]*://([^/]*\.)?")
        i = 2
    elif pattern.startswith("|"):
        out.append("^")
        i = 1
    end_anchor = pattern.endswith("|") and len(pattern) > i
    body = pattern[i:-1] if end_anchor else pattern[i:]
    for ch in body:
        if ch == "*":
            out.append(".*")
        elif ch == "^":
            out.append(r"(?:[^\w\d_.%-]|$)")
        else:
            out.append(re.escape(ch))
    if end_anchor:
        out.append("$")
    return "".join(out)


def _url_filter_anchor(pattern: Optional[str]) -> Optional[str]:
    """Extract the host anchor from a domain-anchored urlFilter ("||host/...").

    Returns the host so the rule can be indexed by domain instead of joining a
    per-request global scan. ``None`` when the pattern is not domain-anchored.
    """
    if not pattern or not pattern.startswith("||"):
        return None
    body = pattern[2:]
    # Host runs until the first path/query/anchor separator or wildcard.
    for i, ch in enumerate(body):
        if ch in "/?#^|*+":
            return body[:i].lower() or None
    return body.lower() or None


def _is_literal_filter(pattern: str) -> bool:
    """True when the pattern is a plain substring (no wildcard/anchor/meta)."""
    return not any(c in pattern for c in "*^|+$?()[]{}.\\")


def _type_matches(rule: dict, resource_type: str) -> bool:
    types = (rule.get("condition") or {}).get("resourceTypes") or []
    return not types or resource_type in types
