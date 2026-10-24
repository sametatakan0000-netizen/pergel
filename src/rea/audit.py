"""Static risk audit of a Chrome extension manifest.json (pure function, no network)."""
from typing import Dict, List

BROAD_HOSTS = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*", "*://*/"}


def _finding(fid: str, severity: str, detail: str) -> Dict[str, str]:
    return {"id": fid, "severity": severity, "detail": detail}


COMPONENT_NAMES = {"mei preload", "widevinecdm", "hyphens-data", "privacy sandbox attestations",
                   "crowd deny", "origin trials", "first party sets", "trust token keys"}


def is_component_manifest(m: dict) -> bool:
    """Chromium ships data/CDM 'components' with MV2-shaped manifests that run no extension code:
    no scripts, no permissions. They must not generate an MV2 finding."""
    if m.get("background") or m.get("content_scripts") or m.get("permissions") or m.get("host_permissions"):
        return False
    return str(m.get("name", "")).strip().lower() in COMPONENT_NAMES or "x-cdm-codecs" in m


def audit_manifest(m: dict) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if m.get("manifest_version") == 2 and not is_component_manifest(m):
        out.append(_finding("mv2", "medium", "Manifest V2 is deprecated; persistent background pages and remote code are possible"))
    perms = set(m.get("permissions", [])) | set(m.get("optional_permissions", []))
    hosts = set(m.get("host_permissions", [])) | {p for p in m.get("permissions", []) if "://" in p or p == "<all_urls>"}
    if hosts & BROAD_HOSTS:
        out.append(_finding("broad-host", "high", f"access to all sites: {sorted(hosts & BROAD_HOSTS)}"))
    if "debugger" in perms:
        out.append(_finding("debugger", "high", "chrome.debugger can drive any tab via CDP"))
    if "nativeMessaging" in perms:
        out.append(_finding("native-messaging", "medium", "can talk to a native host binary on the machine"))
    if "webRequestBlocking" in perms:
        out.append(_finding("web-request-blocking", "medium", "can block/modify every request"))
    ec = m.get("externally_connectable", {}).get("matches", [])
    if any(p in BROAD_HOSTS or p.startswith("*://*") for p in ec):
        out.append(_finding("ext-connectable-wildcard", "high", "any website may message this extension"))
    csp = m.get("content_security_policy")
    csp_text = " ".join(csp.values()) if isinstance(csp, dict) else str(csp or "")
    if "unsafe-eval" in csp_text:
        out.append(_finding("unsafe-eval", "high", "CSP allows eval-style code execution"))
    return out
