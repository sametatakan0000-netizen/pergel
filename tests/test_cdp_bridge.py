"""CDP Fetch bridge: applies rule-engine decisions to a real browser via the
Chrome DevTools Protocol. This is the wiring that turns the evaluator into an
actual request interceptor. Pure logic + protocol-message construction; the
socket lives in the caller (or CDPBridge.send).
"""
import unittest

from src.browser_engine.cdp_bridge import decide_cdp_response
from src.browser_engine.rule_engine import compile_rules


class TestBlockProducesFailRequest(unittest.TestCase):
    def test_block_triggers_fetch_fail_request(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="1234.5",
            url="https://ad.doubleclick.net/x.gif",
            resource_type="Image",
            request_headers={"Referer": "https://news.example/"})
        self.assertEqual(msg["method"], "Fetch.failRequest")
        self.assertEqual(msg["params"]["requestId"], "1234.5")
        self.assertEqual(msg["params"]["errorReason"], "BlockedByClient")

    def test_allow_produces_continue_with_no_modification(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="1.2", url="https://example.org/main.css",
            resource_type="Stylesheet", request_headers={})
        self.assertEqual(msg["method"], "Fetch.continueRequest")
        self.assertEqual(msg["params"]["requestId"], "1.2")
        self.assertNotIn("headers", msg["params"])


class TestRedirectProducesContinueWithUrl(unittest.TestCase):
    def test_redirect_sets_new_url(self):
        engine = compile_rules([
            {"id": 7, "priority": 1,
             "action": {"type": "redirect", "redirect": {"url": "https://localhost/p.gif"}},
             "condition": {"requestDomains": ["tracker.io"], "resourceTypes": ["image"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="9.9", url="https://tracker.io/p.gif",
            resource_type="Image", request_headers={})
        self.assertEqual(msg["method"], "Fetch.continueRequest")
        self.assertEqual(msg["params"]["url"], "https://localhost/p.gif")


class TestModifyHeadersProducesContinueWithHeaders(unittest.TestCase):
    def test_header_ops_applied_to_request_headers(self):
        engine = compile_rules([
            {"id": 3, "priority": 1,
             "action": {"type": "modifyHeaders",
                        "requestHeaders": [{"header": "DNT", "operation": "set", "value": "1"},
                                           {"header": "Referer", "operation": "remove"}]},
             "condition": {"requestDomains": ["tracker.io"], "resourceTypes": ["image"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="3.3", url="https://tracker.io/p.gif",
            resource_type="Image",
            request_headers={"Referer": "https://news.example", "Accept": "image/*"})
        self.assertEqual(msg["method"], "Fetch.continueRequest")
        headers = {h["name"]: h["value"] for h in msg["params"]["headers"]}
        self.assertNotIn("Referer", headers)
        self.assertEqual(headers["DNT"], "1")
        self.assertEqual(headers["Accept"], "image/*")


class TestResourceTypeMapping(unittest.TestCase):
    """CDP uses PascalCase resource types; the engine uses DNR names."""

    def test_cdp_image_maps_to_dnr_image(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["x.io"], "resourceTypes": ["image"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="1", url="https://x.io/a.png",
            resource_type="Image", request_headers={})
        self.assertEqual(msg["method"], "Fetch.failRequest")

    def test_cdp_xhr_maps_to_xmlhttprequest(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["x.io"], "resourceTypes": ["xmlhttprequest"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="1", url="https://x.io/api",
            resource_type="XHR", request_headers={})
        self.assertEqual(msg["method"], "Fetch.failRequest")

    def test_cdp_document_maps_to_main_frame(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["x.io"], "resourceTypes": ["main_frame"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="1", url="https://x.io/",
            resource_type="Document", request_headers={})
        self.assertEqual(msg["method"], "Fetch.failRequest")


class TestAllowRuleWinsOverBlock(unittest.TestCase):
    def test_allow_overrides_block_and_continues(self):
        engine = compile_rules([
            {"id": 1, "priority": 100, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
            {"id": 2, "priority": 1, "action": {"type": "allow"},
             "condition": {"requestDomains": ["ad.doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        msg = decide_cdp_response(
            engine, request_id="1", url="https://ad.doubleclick.net/x.gif",
            resource_type="Image", request_headers={})
        self.assertEqual(msg["method"], "Fetch.continueRequest")


if __name__ == "__main__":
    unittest.main()
