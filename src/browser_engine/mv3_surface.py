"""B series: the MV3 extension surface (platform-agnostic).

This is what lets a third-party MV3 extension (Bitwarden, Grammarly, or any
other) run unchanged on our engine. There is no vendor lock-in here: the
contract is the open Manifest V3 + ``declarativeNetRequest`` shape that every
Chromium-extension already targets.

The bridge is thin on purpose — our ``rule_engine`` already understands DNR
rules, so the surface just:

- parses/validates a manifest (``load_manifest``),
- surfaces its declarativeNetRequest rules in engine form (``manifest_dnr_rules``),
- compiles those rules straight onto our existing engine (``build_extension_engine``),
- reports its content-script injection points (``content_script_sources``).

Service-worker/background and messaging layers are the follow-on work; this is
the parsing + network-rule core they hang off.
"""


from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

from .rule_engine import RuleEngine, compile_rules

__all__ = [
    "MV3Manifest",
    "load_manifest",
    "manifest_dnr_rules",
    "build_extension_engine",
    "content_script_sources",
]


@dataclass
class MV3Manifest:
    name: str
    version: str
    manifest_version: int
    permissions: List[str] = field(default_factory=list)
    host_permissions: List[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def uses_dnr(self) -> bool:
        return "declarativeNetRequest" in self.permissions or (
            "declarativeNetRequest" in self.raw
        )


def load_manifest(data: dict) -> MV3Manifest:
    """Parse and validate an MV3 manifest dict into :class:`MV3Manifest`."""
    if not isinstance(data, dict):
        raise ValueError("manifest must be a dict")
    mv = data.get("manifest_version")
    if mv != 3:
        raise ValueError(f"unsupported manifest_version: {mv!r} (need 3)")
    return MV3Manifest(
        name=str(data.get("name", "")),
        version=str(data.get("version", "")),
        manifest_version=3,
        permissions=list(data.get("permissions", []) or []),
        host_permissions=list(data.get("host_permissions", []) or []),
        raw=data,
    )


def manifest_dnr_rules(rules: Iterable[dict]) -> List[dict]:
    """Normalize an extension's DNR rules into our engine's rule shape.

    MV3 DNR rules already use the ``{id, priority, action{type}, condition{...}}``
    form our engine compiles, so this validates minimally and passes through.
    """
    out: List[dict] = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("each DNR rule must be a dict")
        action = rule.get("action") or {}
        cond = rule.get("condition") or {}
        out.append({
            "id": rule.get("id"),
            "priority": int(rule.get("priority", 0)),
            "action": {"type": action.get("type", "block"),
                       "redirect": action.get("redirect")},
            "condition": {
                "urlFilter": cond.get("urlFilter"),
                "regexFilter": cond.get("regexFilter"),
                "resourceTypes": list(cond.get("resourceTypes", []) or []),
                "requestDomains": list(cond.get("requestDomains", []) or []),
            },
        })
    return out


def build_extension_engine(rules: Iterable[dict]) -> RuleEngine:
    """Compile an extension's DNR rules onto our existing rule engine."""
    return compile_rules(manifest_dnr_rules(rules))


def content_script_sources(manifest: MV3Manifest) -> List[Tuple[List[str], List[str], str]]:
    """Return each content-script block as ``(css, js, run_at)``.

    This is the injection plan the CDP layer applies at the matching document
    phase. ``run_at`` defaults to ``document_idle`` per MV3 semantics.
    """
    out: List[Tuple[List[str], List[str], str]] = []
    for block in (manifest.raw.get("content_scripts", []) or []):
        out.append((
            list(block.get("css", []) or []),
            list(block.get("js", []) or []),
            block.get("run_at", "document_idle"),
        ))
    return out
