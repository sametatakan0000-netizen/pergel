"""Procedural cosmetic rules (``#?#``): selectors CSS cannot express.

EasyList/uBO ship ``host#?#selector:has-text(text)`` rules. They need a
JS filter at document-start, not a stylesheet. The runtime is self-authored:
a base-selector match, then small pure tests (``:has-text``, ``:has``,
``:contains``) evaluated on each match, hidden via an inline ``display:none``.
"""
from __future__ import annotations

import json
from typing import Iterable


def compile_procedural(lines: Iterable[str]) -> list:
    """Parse ``host#?#selector`` rules into ``{base, tests, domains, exceptions}``."""
    rules: list = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("!", "[")):
            continue
        marker = None
        for m in ("#@?#", "#?#"):
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
        base, tests = _split_selector(selector)
        rule = {"base": base, "tests": tests,
                "domains": domains, "exceptions": []}
        if marker == "#@?#":
            rule["exceptions"] = list(domains) if domains else [""]
        rules.append(rule)
    return rules


def _split_selector(selector: str) -> tuple[str, list]:
    """Split ``.a:has-text(x)`` into base ``.a`` and test list ``[("has-text", "x")]``."""
    tests: list = []
    base = selector
    for fn in ("has-text", "contains", "has"):
        marker = f":{fn}("
        while True:
            idx = _find_marker(base, marker, fn)
            if idx is None:
                break
            open_idx = idx + len(marker)
            depth = 1
            j = open_idx
            while j < len(base) and depth:
                if base[j] == "(":
                    depth += 1
                elif base[j] == ")":
                    depth -= 1
                j += 1
            arg = base[open_idx:j - 1].strip()
            tests.append((fn, arg))
            base = base[:idx] + base[j:]
    return base.strip() or selector, tests


def _find_marker(base: str, marker: str, fn: str) -> int | None:
    """Index of ``:fn(`` that is not the prefix of a longer pseudo (``:has-text``)."""
    start = 0
    while True:
        idx = base.find(marker, start)
        if idx is None or idx == -1:
            return None
        after = idx + len(marker)
        if fn == "has" and after < len(base) and base[after].isalpha():
            start = idx + 1
            continue
        return idx


def _key(rule: dict) -> tuple:
    return (rule.get("base"), tuple(rule.get("tests") or []))


def procedural_js(rules: Iterable[dict], host: str) -> str:
    """JS source that hides elements matched by procedural rules on ``host``."""
    from .rule_engine import RuleEngine

    active: list[dict] = []
    # Pass 1: a matching #@?# exception cancels the rule it names, wherever the
    # hide rule came from (generic or scoped).
    cancelled: set = set()
    for rule in rules:
        for ex in rule.get("exceptions") or []:
            if ex == "" or RuleEngine.match_domain(host, ex):
                cancelled.add(_key(rule))
    for rule in rules:
        if rule.get("exceptions"):
            continue
        if _key(rule) in cancelled:
            continue
        domains = rule.get("domains") or []
        if domains and not any(RuleEngine.match_domain(host, d) for d in domains):
            continue
        active.append(rule)
    if not active:
        return ""
    payload = json.dumps([
        {"base": r["base"],
         "tests": [[fn, arg] for fn, arg in r.get("tests") or []]}
        for r in active
    ])
    return _RUNNER.replace("__RULES__", payload)


_RUNNER = """(() => {
const RULES = __RULES__;
const match = (el, test) => {
  const [fn, arg] = test;
  if (fn === 'has-text' || fn === 'contains') {
    try { return (el.textContent || '').toLowerCase().includes(String(arg).toLowerCase()); }
    catch (e) { return false; }
  }
  if (fn === 'has') { try { return el.querySelector(arg) !== null; } catch (e) { return false; } }
  return false;
};
const apply = () => {
  for (const rule of RULES) {
    let els = [];
    try { els = document.querySelectorAll(rule.base); } catch (e) { continue; }
    for (const el of els) {
      if (el.getAttribute('data-ab-proc') === '1') continue;
      el.setAttribute('data-ab-proc', '1');
      let hide = rule.tests.length > 0;
      for (const t of rule.tests) { if (!match(el, t)) { hide = false; break; } }
      if (hide) el.style.setProperty('display', 'none', 'important');
    }
  }
};
apply();
const start = () => {
  const root = document.documentElement;
  if (!root) return false;
  const mo = new MutationObserver(apply);
  mo.observe(root, { childList: true, subtree: true });
  apply();
  return true;
};
if (!start()) {
  const t = setInterval(() => { if (start()) clearInterval(t); }, 10);
}
document.addEventListener('DOMContentLoaded', apply);
window.addEventListener('load', apply);
setInterval(apply, 250);
})();"""
