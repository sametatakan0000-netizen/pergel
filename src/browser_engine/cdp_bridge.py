"""CDP Fetch bridge: applies rule-engine decisions to a real browser.

Turns the evaluator into an actual request interceptor via the Chrome DevTools
Protocol. ``decide_cdp_response`` is pure: given a ``Fetch.requestPaused`` event
payload it returns the JSON-RPC message the caller should send. No socket I/O
here — the transport lives in the caller (``CDPBridge``).
"""
from __future__ import annotations

from typing import Optional

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


def decide_cdp_response(engine: RuleEngine, *, request_id: str, url: str,
                        resource_type: str,
                        request_headers: Optional[dict] = None) -> dict:
    """Return the CDP message answering a ``Fetch.requestPaused`` event.

    Block  -> ``Fetch.failRequest`` with ``BlockedByClient``
    Redirect -> ``Fetch.continueRequest`` with the replacement ``url``
    modifyHeaders -> ``Fetch.continueRequest`` with rewritten ``headers``
    Allow / no match -> ``Fetch.continueRequest`` unmodified
    """
    decision = engine.check(url, resource_type=_dnr_type(resource_type))

    if decision.action == "block":
        return {
            "method": "Fetch.failRequest",
            "params": {"requestId": request_id, "errorReason": "BlockedByClient"},
        }

    params: dict = {"requestId": request_id}

    if decision.action == "redirect" and decision.redirect_url:
        params["url"] = decision.redirect_url

    if decision.action == "modifyHeaders" and decision.request_header_ops:
        params["headers"] = _headers_to_cdp(
            decision.apply_to_headers(request_headers or {}, response=False))

    return {"method": "Fetch.continueRequest", "params": params}


def _headers_to_cdp(headers: dict) -> list:
    """CDP wants a list of {name, value} entries, not a dict."""
    return [{"name": k, "value": v} for k, v in headers.items()]


class CDPBridge:
    """Thin transport wrapper around a WebSocket connected to Chrome's CDP.

    Kept minimal and injectable so tests never open a socket. ``send`` is the
    only I/O seam; ``on_request_paused`` is pure message construction.
    """

    def __init__(self, engine: RuleEngine, send) -> None:
        self.engine = engine
        self._send = send

    def on_request_paused(self, params: dict) -> dict:
        """Build and dispatch the response for a Fetch.requestPaused event."""
        msg = decide_cdp_response(
            self.engine,
            request_id=params["requestId"],
            url=params["request"]["url"],
            resource_type=params.get("resourceType", "Other"),
            request_headers=_cdp_headers_to_dict(
                params.get("request", {}).get("headers", {})),
        )
        self._send(msg)
        return msg


def _cdp_headers_to_dict(headers: dict) -> dict:
    """CDP header maps are {name: value} already in Fetch.requestPaused."""
    return dict(headers)
