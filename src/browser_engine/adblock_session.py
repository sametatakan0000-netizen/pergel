"""Adblock integration: one filter list -> all four layers -> one injection.

The four enforcement layers each live in their own module and are verified in
isolation:

- ``abp_compiler.compile_abp_lines`` -> network rules for ``RuleEngine`` (DNR)
- ``abp_compiler.compile_cosmetic``   -> element-hiding selectors (CSS)
- ``scriptlets.compile_scriptlets``   -> ``##+js()`` page hooks (JS)
- ``procedural.compile_procedural``   -> ``#?#`` DOM filters (JS)

This module is the seam that composes them. ``compile_adblock`` routes one
filter list into every layer at once (keeping ``##+js()`` out of the cosmetic
bucket), and ``build_injection`` folds the three renderer-side layers into a
single ``document-start`` JS source ready for
``Page.addScriptToEvaluateOnNewDocument``.

Pure: no sockets, no browser. The live CDP fetch wiring is exercised in
``tests/test_adblock_live.py``.
"""


import json
from dataclasses import dataclass, field
from typing import Iterable

from .abp_compiler import compile_abp_lines, compile_cosmetic
from .cosmetic import cosmetic_css
from .procedural import compile_procedural, procedural_js
from .rule_engine import RuleEngine, compile_rules
from .scriptlets import compile_scriptlets, scriptlet_js

_SCRIPTLET_MARK = "##+js("
_PROCEDURAL_MARKS = ("#?#", "#@?#")


@dataclass
class AdblockBundle:
    """Everything one filter list contributes, split by enforcement layer."""
    network: RuleEngine = field(default_factory=RuleEngine)
    cosmetic: list = field(default_factory=list)
    scriptlets: list = field(default_factory=list)
    procedural: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _bucket(line: str) -> str:
    """Classify one raw filter line into its enforcement layer."""
    if _SCRIPTLET_MARK in line:
        return "scriptlet"
    if any(m in line for m in _PROCEDURAL_MARKS):
        return "procedural"
    if "##" in line or "#@#" in line:
        return "cosmetic"
    return "network"


def compile_adblock(lines: Iterable[str]) -> AdblockBundle:
    """Route one filter list into all four layers at once.

    Lines are partitioned first so a ``##+js()`` rule never reaches the
    cosmetic compiler as a bogus ``+js(...)`` selector (which would invalidate
    the whole stylesheet).
    """
    raw = list(lines)
    network_lines: list[str] = []
    cosmetic_lines: list[str] = []
    scriptlet_lines: list[str] = []
    procedural_lines: list[str] = []
    for line in raw:
        kind = _bucket(line.strip())
        if kind == "scriptlet":
            scriptlet_lines.append(line)
        elif kind == "procedural":
            procedural_lines.append(line)
        elif kind == "cosmetic":
            cosmetic_lines.append(line)
        else:
            network_lines.append(line)

    bundle = AdblockBundle()
    bundle.network = compile_rules(compile_abp_lines(network_lines).rules)
    bundle.cosmetic = compile_cosmetic(cosmetic_lines)
    bundle.scriptlets = compile_scriptlets(scriptlet_lines)
    bundle.procedural = compile_procedural(procedural_lines)
    bundle.stats = {
        "total": len(raw),
        "network": len(network_lines),
        "cosmetic": len(cosmetic_lines),
        "scriptlets": len(scriptlet_lines),
        "procedural": len(procedural_lines),
    }
    return bundle


def _css_inject_iife(css: str) -> str:
    """FOUC-safe ``<style>`` injection at document-start.

    The CSS text is embedded as a JSON string literal (never Python ``repr``,
    which breaks on embedded quotes) and the append target tolerates a null
    ``documentElement`` by deferring to ``DOMContentLoaded``.
    """
    return (
        "(() => { const s = document.createElement('style');"
        f" s.textContent = {json.dumps(css)};"
        " const d = document.documentElement || document.head;"
        " if (d) { d.appendChild(s); }"
        " else { document.addEventListener('DOMContentLoaded',"
        "   () => (document.head || document.documentElement).appendChild(s)); }"
        " })();"
    )


def build_injection(bundle: AdblockBundle, host: str) -> str:
    """One ``document-start`` JS source applying cosmetic + scriptlets + procedural.

    Empty string when no renderer-side layer applies to ``host``.
    """
    parts: list[str] = []
    css = cosmetic_css(bundle.cosmetic, host)
    if css:
        parts.append(_css_inject_iife(css))
    sjs = scriptlet_js(bundle.scriptlets, host)
    if sjs.strip():
        parts.append(sjs)
    pjs = procedural_js(bundle.procedural, host)
    if pjs.strip():
        parts.append(pjs)
    return "\n".join(parts)


def build_network_engine(bundle: AdblockBundle) -> RuleEngine:
    """Expose the network rule engine for CDP ``Fetch`` interception."""
    return bundle.network


def load_adblock_bundle(paths: Iterable[str]) -> AdblockBundle:
    """Compile one or more filter-list files (EasyList, uAssets, ...) into a bundle.

    Blank lines and ``!``/``[`` header comments are dropped before routing. This
    is the product hook: real public filter lists in, one enforceable bundle out.
    """
    lines: list[str] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for raw in f:
                    s = raw.strip()
                    if not s or s.startswith("!") or s.startswith("["):
                        continue
                    lines.append(s)
        except OSError:
            continue
    return compile_adblock(lines)
