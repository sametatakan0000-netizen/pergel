"""Extension rules must reach the REAL enforcement path (CDP Fetch), not just
a test-only seam. TDD: before this wiring existed, an extension's block rule
only decided inside ``ExtensionHost.check`` — ``decide_cdp_response`` never saw
it, so the request actually flowed through the browser unblocked.

These tests pin the real bridge path: an extension's DNR rule yields
``Fetch.failRequest`` from ``decide_cdp_response``, which is the message CDP
uses to stop the request in Chromium.
"""
import unittest

from src.browser_engine.cdp_bridge import decide_cdp_response
from src.browser_engine.extension_host import Extension, ExtensionHost


class ExtensionCdpWiringTests(unittest.TestCase):
    def setUp(self):
        self.host = ExtensionHost()
        self.host.attach(Extension("uBlock-like", dnr_rules=[
            {"id": 1, "priority": 1,
             "action": {"type": "block"},
             "condition": {"urlFilter": "||ads.example.com^",
                           "resourceTypes": ["script"]}},
        ]))

    def test_extension_block_becomes_fail_request_on_cdp_path(self):
        # resource_type is the CDP Fetch value (PascalCase), e.g. "Script".
        msg = decide_cdp_response(
            self.host,
            request_id="42",
            url="https://ads.example.com/banner.js",
            resource_type="Script",
        )
        self.assertEqual(msg["method"], "Fetch.failRequest")
        self.assertEqual(msg["params"]["errorReason"], "BlockedByClient")

    def test_extension_allows_unmatched_on_cdp_path(self):
        msg = decide_cdp_response(
            self.host,
            request_id="43",
            url="https://cdn.example.org/app.js",
            resource_type="Script",
        )
        self.assertEqual(msg["method"], "Fetch.continueRequest")

    def test_disabled_extension_does_not_block_on_cdp_path(self):
        self.host.set_enabled("uBlock-like", False)
        msg = decide_cdp_response(
            self.host,
            request_id="44",
            url="https://ads.example.com/banner.js",
            resource_type="Script",
        )
        self.assertEqual(msg["method"], "Fetch.continueRequest")

    def test_extension_rules_reach_the_bridge_enforcement_path(self):
        """The live session path: CDPBridge with an extension host attached.

        Before this, AdblockBrowserSession built its bridge only from
        bundle.network — extension rules never reached enforcement.
        """
        from src.browser_engine.cdp_bridge import CDPBridge
        sent = []
        bridge = CDPBridge(self.host, send=sent.append)
        msg = bridge.on_request_paused({
            "requestId": "50",
            "request": {"url": "https://ads.example.com/banner.js"},
            "resourceType": "Script",
        })
        self.assertEqual(msg["method"], "Fetch.failRequest")
        self.assertEqual(sent[0]["method"], "Fetch.failRequest")

    def test_extension_rules_aggregate_with_adblock_network_rules(self):
        """Ad-list rules AND extension rules both decide on one request."""
        from src.browser_engine.adblock_session import compile_adblock
        from src.browser_engine.cdp_bridge import CDPBridge
        bundle = compile_adblock(["||tracker.example.net^"])
        self.host.attach(Extension("second", dnr_rules=[
            {"id": 2, "priority": 1,
             "action": {"type": "block"},
             "condition": {"urlFilter": "||ads.example.com^",
                           "resourceTypes": ["script"]}},
        ]))
        bridge = CDPBridge((bundle.network, self.host), send=lambda m: None)
        for url, rid in (("https://tracker.example.net/x.js", "60"),
                         ("https://ads.example.com/banner.js", "61")):
            msg = bridge.on_request_paused({
                "requestId": rid, "request": {"url": url},
                "resourceType": "Script"})
            self.assertEqual(msg["method"], "Fetch.failRequest", url)


if __name__ == "__main__":
    unittest.main()
