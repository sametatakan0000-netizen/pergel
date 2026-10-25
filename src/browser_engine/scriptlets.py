"""Scriptlet injection: ``##+js(name, args...)`` rules to an early IIFE.

uBO/AdGuard lists ship thousands of scriptlet rules that pure CSS cannot
express (abort an anti-adb script, neutralise a timer, ...). Each rule maps to
a tiny self-authored helper that runs at document-start and only touches the
page's own JS environment — never the network and never the browser shell.

Rules whose scriptlet is not in the allowlist (``trusted-`` helpers that
rewrite traffic, etc.) are skipped and counted, never guessed at.
"""
from __future__ import annotations

import json
from typing import Iterable


def _split_args(args: str) -> list[str]:
    """Split a scriptlet arg list on commas not inside quotes or a regex."""
    out, buf, quote = [], "", ""
    for ch in args:
        if quote:
            buf += ch
            if ch == quote and (len(buf) < 2 or buf[-2] != "\\"):
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            buf += ch
            continue
        if ch == ",":
            out.append(buf.strip())
            buf = ""
            continue
        buf += ch
    if buf.strip():
        out.append(buf.strip())
    return [a for a in out if a != ""]


def compile_scriptlets(lines: Iterable[str]) -> list:
    """Parse ``host##+js(name,arg)`` / ``host#@#+js(name)`` into dicts.

    Each result is ``{name, args, domains, exceptions}``.
    """
    rules: list = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("!", "[")):
            continue
        if line.startswith(("#$#", "#?#", "#@#.", "#@?#")):
            continue
        marker = None
        for m in ("#@#+js(", "##+js("):
            if m in line:
                marker = m
                break
        if marker is None:
            continue
        prefix, rest = line.split(marker, 1)
        name_args = rest.rstrip(")")
        name, _, args_raw = name_args.partition(",")
        name = name.strip()
        if not name:
            continue
        domains = [d.lstrip("~").lstrip(".").lower()
                   for d in prefix.split(",") if d.strip()]
        rule = {"name": name, "args": _split_args(args_raw),
                "domains": domains, "exceptions": []}
        if marker.startswith("#@#"):
            rule["exceptions"] = list(domains) if domains else [""]
        rules.append(rule)
    return rules


# ---------------------------------------------------------------------------
# Self-authored scriptlet helpers. Each is a small, idempotent function that
# wraps one page primitive. No uBO/AdGuard code is copied; these are simple,
# read-only-of-the-page behaviours.
# ---------------------------------------------------------------------------
_HELPERS = {
    "abort-on-property-read": """
function aopr(prop){
  const parts = prop.split('.'); const last = parts.pop();
  let obj = window; for (const p of parts) { if (obj == null) return; obj = obj[p]; }
  if (obj == null) return;
  try { Object.defineProperty(obj, last, { get(){ throw new ReferenceError(prop); }, configurable: true }); } catch(e){}
}""",
    "abort-on-property-write": """
function aopw(prop, val){
  const parts = prop.split('.'); const last = parts.pop();
  let obj = window; for (const p of parts) { if (obj == null) return; obj = obj[p]; }
  if (obj == null) return;
  try { Object.defineProperty(obj, last, {
    set(){ throw new ReferenceError('aborted'); },
    get(){ return val; }, configurable: true }); } catch(e){}
}""",
    "set-constant": """
function setc(prop, val){
  const parts = prop.split('.'); const last = parts.pop();
  let obj = window; for (const p of parts) { if (obj == null) return; obj = obj[p]; }
  if (obj == null) return;
  let out = val;
  if (val === 'true') out = true; else if (val === 'false') out = false;
  else if (val === 'null') out = null; else if (val === 'undefined') out = undefined;
  else if (val === 'noopFunc') out = function(){}; else if (val === 'trueFunc') out = function(){ return true; };
  else if (val === 'falseFunc') out = function(){ return false; };
  try { Object.defineProperty(obj, last, { get(){ return out; }, set(){}, configurable: true }); } catch(e){}
}""",
    "abort-current-script": """
function acs(needle){
  const test = (el) => { try { return (el.textContent||'').includes(needle); } catch(e){ return false; } };
  const kill = () => { for (const s of document.querySelectorAll('script:not([data-ab-kill])')) { if (test(s)) { s.setAttribute('data-ab-kill','1'); s.remove(); } } };
  kill();
  const mo = new MutationObserver(kill); mo.observe(document.documentElement, { childList: true, subtree: true });
}""",
    "addEventListener-defuser": """
function aeld(name){
  const orig = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, fn, opts){
    if (type === name) return;
    return orig.call(this, type, fn, opts);
  };
}""",
    "no-setInterval-if": """
function nostif(needle){
  const orig = window.setInterval;
  window.setInterval = function(fn, ms, ...rest){
    if (typeof fn === 'function' && String(fn).includes(needle)) return 0;
    return orig.call(window, fn, ms, ...rest);
  };
}""",
    "nano-setInterval-booster": """
function nsib(){
  const orig = window.setInterval;
  window.setInterval = function(fn, ms, ...rest){ return orig.call(window, fn, Math.min(ms||16, 16), ...rest); };
}""",
    "no-setTimeout-if": """
function nosto(needle){
  const orig = window.setTimeout;
  window.setTimeout = function(fn, ms, ...rest){
    if ((typeof fn === 'function' && String(fn).includes(needle)) ||
        (typeof fn === 'string' && fn.includes(needle))) return 0;
    return orig.call(window, fn, ms, ...rest);
  };
}""",
    "nowoif": """
function nowoif(){
  const orig = window.open;
  window.open = function(){ return null; };
}""",
    "remove-node-text": """
function rmnt(needle, selector){
  const sel = selector || 'script, style';
  const kill = () => { for (const el of document.querySelectorAll(sel)) {
    try { if ((el.textContent||'').includes(needle)) el.remove(); } catch(e){} } };
  kill();
  const mo = new MutationObserver(kill); mo.observe(document.documentElement, { childList: true, subtree: true });
}""",
    "no-webrtc": """
function nowebrtc(){
  const neuter = (o) => { for (const p of ['RTCPeerConnection','webkitRTCPeerConnection','mozRTCPeerConnection']) {
    if (o[p]) { try { o[p] = function(){ throw new ReferenceError('WebRTC disabled'); }; } catch(e){} } } };
  neuter(window);
}""",
    "nano-setTimeout-booster": """
function nstb(){
  const orig = window.setTimeout;
  window.setTimeout = function(fn, ms, ...rest){ return orig.call(window, fn, Math.min(ms||16, 16), ...rest); };
}""",
    "no-requestAnimationFrame-if": """
function nora(needle){
  const orig = window.requestAnimationFrame;
  window.requestAnimationFrame = function(fn){
    if (typeof fn === 'function' && String(fn).includes(needle)) return 0;
    return orig.call(window, fn);
  };
}""",
    "no-fetch-if": """
function nofi(needle){
  const orig = window.fetch;
  window.fetch = function(input, init){
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.includes(needle)) return Promise.reject(new ReferenceError(needle));
    return orig.call(this, input, init);
  };
}""",
    "no-xhr-if": """
function noxi(needle){
  const orig = window.XMLHttpRequest.prototype.open;
  window.XMLHttpRequest.prototype.open = function(method, url, ...rest){
    if (String(url).includes(needle)) return;
    return orig.call(this, method, url, ...rest);
  };
}""",
    "no-eval": """
function noeval(){
  try { window.eval = function(){ throw new ReferenceError('eval disabled'); }; } catch(e){}
  try { window.Function = function(){ throw new ReferenceError('Function disabled'); }; } catch(e){}
}""",
}


def _helper_key(name: str) -> str | None:
    return _ALIASES.get(name) or (name if name in _HELPERS else None)


# uBO/AdGuard lists use short names; the helpers above use long ones.
_ALIASES = {
    "aopr": "abort-on-property-read",
    "aopw": "abort-on-property-write",
    "aost": "abort-on-property-write",
    "set": "set-constant",
    "acs": "abort-current-script",
    "aeld": "addEventListener-defuser",
    "nostif": "no-setInterval-if",
    "nosto": "no-setTimeout-if",
    "nsib": "nano-setInterval-booster",
    "nano-sib": "nano-setInterval-booster",
    "rmnt": "remove-node-text",
    "nowebrtc": "no-webrtc",
    "no-webrtc": "no-webrtc",
    "nano-stb": "nano-setTimeout-booster",
    "ra": "no-requestAnimationFrame-if",
    "nosiif": "no-requestAnimationFrame-if",
    "no-fetch-if": "no-fetch-if",
    "no-xhr-if": "no-xhr-if",
    "noeval": "no-eval",
    "noeval-if": "no-eval",
}


def scriptlet_js(rules: Iterable[dict], host: str) -> str:
    """IIFE source that installs every scriptlet in scope for ``host``.

    Unsupported scriptlets are skipped silently — the browser never sees a
    guessed at or half-implemented helper.
    """
    from .rule_engine import RuleEngine

    calls: list[str] = []
    needed: set = set()
    for rule in rules:
        if rule.get("exceptions"):
            if any(ex == "" or RuleEngine.match_domain(host, ex)
                   for ex in rule["exceptions"]):
                continue
        domains = rule.get("domains") or []
        if domains and not any(RuleEngine.match_domain(host, d) for d in domains):
            continue
        key = _helper_key(rule["name"])
        if key is None:
            continue
        needed.add(key)
        args = ", ".join(json.dumps(a) for a in rule.get("args") or [])
        calls.append(f"  {_FUN[key]}({args});")
    if not calls:
        return ""
    body = "\n".join(_HELPERS[k] for k in sorted(needed))
    return "(() => {\n" + body + "\n" + "\n".join(calls) + "\n})();"


_FUN = {
    "abort-on-property-read": "aopr",
    "abort-on-property-write": "aopw",
    "set-constant": "setc",
    "abort-current-script": "acs",
    "addEventListener-defuser": "aeld",
    "no-setInterval-if": "nostif",
    "nano-setInterval-booster": "nsib",
    "no-setTimeout-if": "nosto",
    "nowoif": "nowoif",
    "remove-node-text": "rmnt",
    "no-webrtc": "nowebrtc",
    "nano-setTimeout-booster": "nstb",
    "no-requestAnimationFrame-if": "nora",
    "no-fetch-if": "nofi",
    "no-xhr-if": "noxi",
    "no-eval": "noeval",
}


def supported_scriptlets() -> set:
    return set(_HELPERS)
