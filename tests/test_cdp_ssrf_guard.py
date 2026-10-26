"""SSRF at the CDP enforcement layer: every redirect hop is re-validated.

The fetch-time guard in server.py checks only the first URL. The engine
(over CDP) follows redirects itself, so a redirect to a private host was not
covered. These tests pin the enforcement-layer fix: the CDP bridge re-validates
every paused request's target (including redirect hops) and blocks private
targets, while a policy engine 'redirect' action to a private host is refused.

RED first (ssrf_guard arg absent), then GREEN.
"""
import unittest

from src.browser_engine.cdp_bridge import CDPBridge, decide_cdp_response
from src.browser_engine.rule_engine import compile_rules


def _private_guard(url: str) -> bool:
    """Return True when the URL is an SSRF risk (private/loopback host)."""
    import ipaddress
    import socket
    import urllib.parse

    host = urllib.parse.urlsplit(url).hostname or ""
    if host in ("localhost",):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # unresolvable -> not reachable, engine will fail naturally
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return True
    return False


def _block_rule(rule_id, host, redirect=None):
    action = {"type": "redirect", "redirect": {"url": redirect}} if redirect \
        else {"type": "block"}
    return [{"id": rule_id, "priority": 1, "action": action,
             "condition": {"urlFilter": f"||{host}^",
                           "resourceTypes": ["main_frame"]}}]


class SsrfOnRedirectTests(unittest.TestCase):
    def _paused(self, url, rid="r1"):
        return {"requestId": rid,
                "request": {"url": url, "headers": {}},
                "resourceType": "Document"}

    def test_private_redirect_hop_is_blocked(self):
        sent = []
        engine = compile_rules(_block_rule(1, "ads.example"))  # allows everything
        bridge = CDPBridge(engine, sent.append, ssrf_guard=_private_guard)
        msg = bridge.on_request_paused(self._paused("http://127.0.0.1:8080/x"))
        self.assertEqual(msg["method"], "Fetch.failRequest")

    def test_public_hop_passes(self):
        sent = []
        engine = compile_rules(_block_rule(1, "ads.example"))
        bridge = CDPBridge(engine, sent.append, ssrf_guard=_private_guard)
        msg = bridge.on_request_paused(self._paused("https://example.com/ok"))
        self.assertEqual(msg["method"], "Fetch.continueRequest")

    def test_policy_redirect_to_private_is_refused(self):
        # A rule tries to redirect a request to a private host: refuse it.
        engine = compile_rules(_block_rule(1, "ads.example",
                                           redirect="http://192.168.1.10/steal"))
        msg = decide_cdp_response(
            engine, request_id="r1", url="https://ads.example/x",
            resource_type="Document", ssrf_guard=_private_guard)
        self.assertEqual(msg["method"], "Fetch.failRequest")

    def test_no_guard_keeps_prior_behaviour(self):
        engine = compile_rules(_block_rule(1, "ads.example"))
        bridge = CDPBridge(engine, lambda _msg: None)
        msg = bridge.on_request_paused(self._paused("http://127.0.0.1:8080/x"))
        self.assertEqual(msg["method"], "Fetch.continueRequest")


if __name__ == "__main__":
    unittest.main()
