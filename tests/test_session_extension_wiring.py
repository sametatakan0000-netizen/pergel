"""TDD: extension rules must reach the real session path (AdblockBrowserSession).

Before this, the session built its CDPBridge only from ``bundle.network`` —
an ``ExtensionHost`` passed by the caller was silently ignored, so extension
rules never reached enforcement in the live browser.
"""
import unittest

from src.browser_engine.adblock_session import AdblockBundle
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
from src.browser_engine.extension_host import Extension, ExtensionHost


class SessionExtensionWiringTests(unittest.TestCase):
    def test_session_accepts_extension_host(self):
        host = ExtensionHost()
        host.attach(Extension("ext", dnr_rules=[
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "||ads.example.com^",
                           "resourceTypes": ["script"]}},
        ]))
        sess = AdblockBrowserSession(AdblockBundle(), extensions=host)
        msg = sess._bridge.on_request_paused({
            "requestId": "1", "request": {"url": "https://ads.example.com/b.js"},
            "resourceType": "Script"})
        self.assertEqual(msg["method"], "Fetch.failRequest")

    def test_session_without_extensions_still_blocks_adlist(self):
        bundle = AdblockBundle()
        from src.browser_engine.adblock_session import compile_adblock
        bundle = compile_adblock(["||tracker.example.net^"])
        sess = AdblockBrowserSession(bundle)
        msg = sess._bridge.on_request_paused({
            "requestId": "2", "request": {"url": "https://tracker.example.net/x.js"},
            "resourceType": "Script"})
        self.assertEqual(msg["method"], "Fetch.failRequest")


if __name__ == "__main__":
    unittest.main()
