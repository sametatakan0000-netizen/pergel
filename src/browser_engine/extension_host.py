"""B series: the safe extension-attachment seam (isolation + stable contract).

Extensions/tools attach later in the product's life; the risk is that they
tangle the core modules. The ``ExtensionHost`` prevents that structurally: an
extension never reaches into the core — it hands the host its declarative DNR
rules (and later, content scripts / background hooks) and the host alone
decides enforcement.

Isolation guarantees (proven in tests):
- each extension lives in its own capsule; none can see another's state,
- a failing extension is contained (its engine errors are caught and it is
  treated as inert), never taking down the host or a sibling,
- attach / detach / enable / disable only ever affect that one extension.

Decisions aggregate every enabled extension's rules through our existing rule
engine, so enforcement reuses the proven path rather than a parallel one.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .rule_engine import Decision, RuleEngine, compile_rules

__all__ = ["ExtensionError", "Extension", "ExtensionHost"]


class ExtensionError(Exception):
    """Raised for invalid host operations (e.g. duplicate extension name)."""


class Extension:
    """One attachable extension's declarative footprint.

    Subclasses may override :meth:`engine` to supply their own rule engine; the
    host wraps that call so a buggy extension cannot propagate its failure.
    """

    def __init__(self, name: str, dnr_rules: Optional[Iterable[dict]] = None,
                 content_scripts: Optional[list] = None) -> None:
        self.name = name
        self.dnr_rules = list(dnr_rules or [])
        self.content_scripts = list(content_scripts or [])

    def engine(self) -> RuleEngine:
        """Compile this extension's DNR rules into a rule engine."""
        return compile_rules(self.dnr_rules)


class _Capsule:
    """Private per-extension container — the isolation boundary."""

    __slots__ = ("ext", "enabled", "_engine")

    def __init__(self, ext: Extension) -> None:
        self.ext = ext
        self.enabled = True
        self._engine: Optional[RuleEngine] = None

    def engine(self) -> Optional[RuleEngine]:
        if self._engine is None:
            try:
                self._engine = self.ext.engine()
            except Exception:
                # Contained: a broken extension is inert, not fatal.
                self._engine = None
        return self._engine


class ExtensionHost:
    """The single stable seam extensions plug into.

    The core talks to the host; the host isolates and aggregates extensions.
    Adding or removing an extension is always a local, side-effect-free change.
    """

    def __init__(self) -> None:
        self._capsules: Dict[str, _Capsule] = {}

    # --- lifecycle ------------------------------------------------------
    def attach(self, ext: Extension) -> None:
        if ext.name in self._capsules:
            raise ExtensionError(f"extension already attached: {ext.name!r}")
        self._capsules[ext.name] = _Capsule(ext)

    def detach(self, name: str) -> None:
        self._capsules.pop(name, None)

    def set_enabled(self, name: str, enabled: bool) -> None:
        cap = self._capsules.get(name)
        if cap is not None:
            cap.enabled = bool(enabled)

    def list_extensions(self) -> List[str]:
        return sorted(self._capsules)

    # --- enforcement ----------------------------------------------------
    def check(self, url: str, resource_type: str = "other") -> Decision:
        """Decide using every enabled extension's rules; default ``allow``.

        An extension whose engine fails to build contributes nothing (it is
        inert) rather than breaking the decision for the rest.
        """
        best: Optional[Decision] = None
        for cap in self._capsules.values():
            if not cap.enabled:
                continue
            engine = cap.engine()
            if engine is None:
                continue
            decision = engine.check(url, resource_type)
            if best is None or _rank(decision) < _rank(best):
                best = decision
        return best if best is not None else Decision("allow")


def _rank(decision: Decision) -> int:
    """Lower rank wins, mirroring the rule engine's action priority."""
    return {"block": 0, "redirect": 1, "modifyHeaders": 2, "allow": 3}.get(
        decision.action, 3)
