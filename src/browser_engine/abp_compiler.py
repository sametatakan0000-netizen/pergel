"""EasyList / Adblock Plus network-filter -> MV3 declarativeNetRequest compiler.

Converts ABP network filters into rule dicts consumable by
``browser_engine.rule_engine.compile_rules``. Cosmetic filters (``##``,
``#@#``, ``#?#``) and unsupported options are skipped and counted, never
silently mis-compiled. Pure function: no I/O, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# ABP resource-type option -> DNR resourceTypes value.
_TYPE_MAP = {
    "script": "script",
    "image": "image",
    "stylesheet": "stylesheet",
    "css": "stylesheet",
    "font": "font",
    "media": "media",
    "xmlhttprequest": "xmlhttprequest",
    "xhr": "xmlhttprequest",
    "subdocument": "sub_frame",
    "document": "main_frame",
    "ping": "ping",
    "websocket": "websocket",
    "object": "object",
    "other": "other",
}

# Options we understand but cannot faithfully express in MV3 DNR: skip the rule.
_UNSUPPORTED_OPTIONS = {"domain", "redirect", "redirect-rule", "csp", "removeparam",
                        "replace", "rewrite", "inline-script", "popup", "generichide",
                        "genericblock", "specifichide", "urlskip", "denyallow", "to"}


@dataclass
class AbpStats:
    total: int = 0
    compiled: int = 0
    skipped_comment: int = 0
    skipped_cosmetic: int = 0
    skipped_unsupported: int = 0


@dataclass
class AbpResult:
    rules: list = field(default_factory=list)
    stats: AbpStats = field(default_factory=AbpStats)


def _split_options(line: str) -> tuple[str, list[str]]:
    # The option separator is the LAST '$' (patterns may contain '$' rarely).
    if "$" in line:
        idx = line.rfind("$")
        return line[:idx], [o.strip() for o in line[idx + 1:].split(",") if o.strip()]
    return line, []


def _compile_one(line: str, rule_id: int) -> dict | None:
    allow = line.startswith("@@")
    if allow:
        line = line[2:]
    pattern, options = _split_options(line)

    cond: dict = {}
    if pattern.startswith("||"):
        body = pattern[2:]
        # Pure domain anchor like "||host^" or "||host^*" -> requestDomains.
        # Exact "||host^" form only; anything with a path or wildcard stays a urlFilter.
        host_part = body[:-1]
        if body.endswith("^") and host_part and all(c not in host_part for c in "/*^|"):
            cond["requestDomains"] = [host_part.lower()]
        else:
            cond["urlFilter"] = pattern
    elif pattern:
        cond["urlFilter"] = pattern
    # Empty pattern with options only: match every request of those types.

    include: list[str] = []
    exclude: list[str] = []
    for opt in options:
        negated = opt.startswith("~")
        name = opt[1:] if negated else opt
        if name in _UNSUPPORTED_OPTIONS or name.startswith("domain="):
            return None
        if name in ("third-party", "~third-party", "first-party"):
            return None  # needs initiator analysis; not expressible safely here
        if name in ("match-case", "important"):
            continue
        mapped = _TYPE_MAP.get(name)
        if mapped is None:
            return None
        (exclude if negated else include).append(mapped)
    if include:
        cond["resourceTypes"] = sorted(set(include))
    if exclude:
        cond["excludedResourceTypes"] = sorted(set(exclude))

    return {
        "id": rule_id,
        "priority": 2 if allow else 1,
        "action": {"type": "allow" if allow else "block"},
        "condition": cond,
    }


def compile_abp_lines(lines: Iterable[str]) -> AbpResult:
    result = AbpResult()
    stats = result.stats
    for raw in lines:
        stats.total += 1
        line = raw.strip()
        if not line or line.startswith("!") or line.startswith("["):
            stats.skipped_comment += 1
            continue
        if "##" in line or "#@#" in line or "#?#" in line or "#$#" in line:
            stats.skipped_cosmetic += 1
            continue
        rule = _compile_one(line, len(result.rules) + 1)
        if rule is None:
            stats.skipped_unsupported += 1
            continue
        result.rules.append(rule)
        stats.compiled += 1
    return result


def compile_cosmetic(lines: Iterable[str]) -> list:
    """Parse EasyList element-hiding rules (``##``/``#@#``) into dicts.

    Network filters, comments, and scriptlet/HTML filters are skipped. Each
    returned dict is ``{selector, domains, exceptions}``; an exception rule
    (``#@#``) contributes to ``exceptions`` so ``cosmetic_css`` can cancel the
    matching hide rule on the hosts it names.
    """
    rules = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("!", "[", "#$#", "#?#")):
            continue
        marker = None
        for m in ("#@#", "##"):
            if m in line:
                marker = m
                break
        if marker is None:
            continue
        prefix, selector = line.split(marker, 1)
        selector = selector.strip()
        if not selector:
            continue
        domains = [d.lstrip("~").lstrip(".").lower()
                   for d in prefix.split(",") if d.strip()]
        rule = {"selector": selector, "domains": domains, "exceptions": []}
        if marker == "#@#":
            rule["exceptions"] = list(domains) if domains else [""]
        rules.append(rule)
    return rules
