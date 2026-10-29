"""CDP Fetch bridge: applies rule-engine decisions to a real browser.

Turns the evaluator into an actual request interceptor via the Chrome DevTools
Protocol. ``decide_cdp_response`` is pure: given a ``Fetch.requestPaused`` event
payload it returns the JSON-RPC message the caller should send. No socket I/O
here — the transport lives in the caller (``CDPBridge``).
"""


from typing import Callable, Optional

from .rule_engine import Decision, RuleEngine

# CDP Fetch resource types (PascalCase) -> DNR resourceTypes (snake/lower).
_CDP_TO_DNR_TYPE = {
    "Document": "main_frame",
    "Stylesheet": "stylesheet",
    "Image": "image",
    "Media": "media",
    "Font": "font",
    "Script": "script",
    "TextTrack": "text_track",
    "XHR": "xmlhttprequest",
    "Fetch": "xmlhttprequest",
    "Preflight": "preflight",
    "EventSource": "event_source",
    "WebSocket": "websocket",
    "Manifest": "manifest",
    "SignedExchange": "signed_exchange",
    "Ping": "ping",
    "CSPViolationReport": "csp_violation_report",
    "Prefetch": "prefetch",
    "Other": "other",
}


def _dnr_type(cdp_resource_type: Optional[str]) -> str:
    return _CDP_TO_DNR_TYPE.get(cdp_resource_type or "", "other")


class CompositeEngine:
    """Aggregates several rule sources (ad-block bundle, extension host, ...).

    Each source only needs a ``check(url, resource_type) -> Decision`` — the
    same shape as :class:`RuleEngine` — so an ``ExtensionHost`` is drop-in.
    Lowest action rank wins, mirroring the rule engine's priority.
    """

    def __init__(self, *sources) -> None:
        self.sources = [s for s in sources if s is not None]

    def check(self, url: str, resource_type: str = "other"):
        best = None
        best_rank = _ACTION_RANK.get("allow", 3)
        for src in self.sources:
            d = src.check(url, resource_type)
            r = _ACTION_RANK.get(d.action, 3)
            if best is None or r < best_rank:
                best, best_rank = d, r
        return best if best is not None else Decision("allow")


_ACTION_RANK = {"block": 0, "redirect": 1, "modifyHeaders": 2, "allow": 3}


def decide_cdp_response(engine: RuleEngine, *, request_id: str, url: str,
                        resource_type: str,
                        request_headers: Optional[dict] = None,
                        ssrf_guard: Optional[Callable[[str], bool]] = None) -> dict:
    """Return the CDP message answering a ``Fetch.requestPaused`` event.

    Block  -> ``Fetch.failRequest`` with ``BlockedByClient``
    Redirect -> ``Fetch.continueRequest`` with the replacement ``url``
    modifyHeaders -> ``Fetch.continueRequest`` with rewritten ``headers``
    Allow / no match -> ``Fetch.continueRequest`` unmodified

    ``ssrf_guard(url) -> True`` marks an SSRF-risk target (private/loopback).
    When set, BOTH the request target and any redirect hop that would leave for
    a private host are refused — this is the enforcement-layer close of the
    redirect-to-private gap the fetch-time guard in ``server.py`` cannot cover,
    because the engine follows redirects itself.
    """
    decision = engine.check(url, resource_type=_dnr_type(resource_type))

    # SSRF: the target itself (a redirect hop reaches here as a fresh paused
    # request) and any policy redirect we would send the browser to.
    if ssrf_guard is not None:
        if ssrf_guard(url):
            return _blocked(request_id, rule_id=None)
        if (decision.action == "redirect" and decision.redirect_url
                and ssrf_guard(decision.redirect_url)):
            return _blocked(request_id, rule_id=decision.rule_id)

    if decision.action == "block":
        return {
            "method": "Fetch.failRequest",
            "params": {"requestId": request_id, "errorReason": "BlockedByClient",
                       "ruleId": decision.rule_id},
        }

    params: dict = {"requestId": request_id, "ruleId": decision.rule_id}

    if decision.action == "redirect" and decision.redirect_url:
        params["url"] = decision.redirect_url

    if decision.action == "modifyHeaders" and decision.request_header_ops:
        params["headers"] = _headers_to_cdp(
            decision.apply_to_headers(request_headers or {}, response=False))

    return {"method": "Fetch.continueRequest", "params": params}


def _blocked(request_id: str, rule_id=None) -> dict:
    return {"method": "Fetch.failRequest",
            "params": {"requestId": request_id, "errorReason": "BlockedByClient",
                       "ruleId": rule_id}}


def _headers_to_cdp(headers: dict) -> list:
    """CDP wants a list of {name, value} entries, not a dict."""
    return [{"name": k, "value": v} for k, v in headers.items()]


class CDPBridge:
    """Thin transport wrapper around a WebSocket connected to Chrome's CDP.

    Kept minimal and injectable so tests never open a socket. ``send`` is the
    only I/O seam; ``on_request_paused`` is pure message construction.
    """

    def __init__(self, engine, send, stats=None, ssrf_guard=None) -> None:
        # Accept a single rule source or several (ad-block bundle + extension
        # host); normalize to one object with a ``check`` method.
        self.engine = CompositeEngine(*engine) if isinstance(engine, tuple) \
            else engine
        self._send = send
        self._stats = stats
        self._ssrf_guard = ssrf_guard

    def on_request_paused(self, params: dict) -> dict:
        """Build and dispatch the response for a Fetch.requestPaused event."""
        msg = decide_cdp_response(
            self.engine,
            request_id=params["requestId"],
            url=params["request"]["url"],
            resource_type=params.get("resourceType", "Other"),
            request_headers=_cdp_headers_to_dict(
                params.get("request", {}).get("headers", {})),
            ssrf_guard=self._ssrf_guard,
        )
        if self._stats is not None:
            self._stats.record(_action_of(msg), rule_id=_rule_id_of(msg))
        # ruleId is our telemetry tag, not a real CDP field — strip before send.
        sendable = {**msg, "params": dict(msg.get("params", {}))}
        sendable["params"].pop("ruleId", None)
        self._send(sendable)
        return msg


def _action_of(msg: dict) -> str:
    """Map a dispatched CDP message back to a decision action label."""
    if msg["method"] == "Fetch.failRequest":
        return "block"
    if "url" in msg.get("params", {}):
        return "redirect"
    if "headers" in msg.get("params", {}):
        return "modifyHeaders"
    return "allow"


def _rule_id_of(msg: dict):
    return msg.get("params", {}).get("ruleId")


def _cdp_headers_to_dict(headers: dict) -> dict:
    """CDP header maps are {name: value} already in Fetch.requestPaused."""
    return dict(headers)
