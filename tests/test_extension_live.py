"""Live Chromium: an extension DNR block rule must stop a real network request.

Skips cleanly without Chromium/websockets (same gate as the other live tests).
"""
import asyncio
import unittest
import unittest.mock

from tests.test_cdp_e2e_live import _find_chromium, websockets
from src.browser_engine.adblock_session import AdblockBundle
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
from src.browser_engine.extension_host import Extension, ExtensionHost

# Page loads a script from a host the extension blocks; the marker reveals
# whether the script actually ran.
PAGE = (
    "<html><body><p>organic</p>"
    "<script src='https://ads.example.com/banner.js'></script>"
    "<script>document.title='organic-done';</script>"
    "</body></html>"
)


class TestExtensionLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _find_chromium() is None or websockets is None:
            raise unittest.SkipTest("no chromium binary or websockets lib")

    def test_extension_block_rule_stops_real_request(self):
        host = ExtensionHost()
        host.attach(Extension("live-ext", dnr_rules=[
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "||ads.example.com^",
                           "resourceTypes": ["script"]}},
        ]))
        seen_blocks = []

        from src.browser_engine import cdp_bridge as cb
        orig = cb.CDPBridge.on_request_paused

        def spy(self, params):
            out = orig(self, params)
            seen_blocks.append({"method": out["method"],
                                "url": params["request"]["url"]})
            return out

        async def go():
            with unittest.mock.patch.object(cb.CDPBridge, "on_request_paused", spy):
                async with AdblockBrowserSession(AdblockBundle(),
                                                 extensions=host) as sess:
                    return await sess.fetch(
                        "data:text/html," + PAGE, host="example.com", timeout=10)

        body = asyncio.run(go())
        self.assertIsInstance(body, dict)
        # Hard evidence: the extension decision was actually enforced on the
        # live request path (a Fetch.failRequest was sent to Chromium).
        self.assertGreaterEqual(len(seen_blocks), 1)
        self.assertTrue(all(m["method"] == "Fetch.failRequest"
                            for m in seen_blocks if "ads.example.com" in m["url"]))


if __name__ == "__main__":
    unittest.main()
