"""Live Chromium e2e: the CDP adblock driver fetches a real page through the engine.

The driver is the product's fetch/browse seam: it owns a Chromium, wires CDP
``Fetch`` interception to the network rule engine, and registers the combined
``document-start`` injection (cosmetic + scriptlets + procedural) before the
page renders. The extracted text is what the enforcement produced — so an ad
that is blocked/hidden/removed must NOT appear in the driver's output.

Skips cleanly without Chromium/websockets.
"""
import asyncio
import json
import unittest

from tests.test_cdp_e2e_live import _find_chromium, websockets
from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession

LIST = [
    "||ads.example.com^",                                   # network block
    "test.com##.sponsored-ad",                              # cosmetic hide
    "test.com#?#.slot:has-text(Sponsored)",                 # procedural hide
]

# A page whose "real" content and ads are distinguishable in the text.
PAGE = (
    "<html><head><title>Real Article</title></head><body>"
    "<h1>Real Article</h1>"
    "<p>This is the genuine editorial content of the page.</p>"
    "<div class='sponsored-ad'>BUY NOW - great product</div>"
    "<div class='slot'>Sponsored content you should not see</div>"
    "<div class='slot'>Organic content you should see</div>"
    "<img src='https://ads.example.com/pixel.gif'>"
    "</body></html>"
)


class TestAdblockDriverLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _find_chromium() is None or websockets is None:
            raise unittest.SkipTest("no chromium binary or websockets lib")

    def test_fetch_returns_filtered_content(self):
        bundle = compile_adblock(LIST)

        async def go():
            async with AdblockBrowserSession(bundle) as sess:
                # serve the page over a data: URL; host scope is passed explicitly
                body = await sess.fetch(
                    "data:text/html," + PAGE, host="test.com", timeout=10)
                return body

        body = asyncio.run(go())
        # shape: scrape body the worker can canonicalize
        self.assertIsInstance(body, dict)
        # the enforced content extraction is innerText (cosmetic/procedural-hidden
        # elements are excluded from rendered text). That is what the reader
        # pipeline consumes — assert enforcement on it.
        text = body["text"][0]

        # the genuine article survives enforcement
        self.assertIn("genuine editorial content", text)
        # every ad shape is gone from the extracted content
        self.assertNotIn("BUY NOW", text)                       # cosmetic-hidden
        self.assertNotIn("Sponsored content you should not see",
                         text)                                  # procedural-hidden
        # the organic slot is NOT hidden and still present
        self.assertIn("Organic content you should see", text)

    def test_browse_returns_markdown_without_ads(self):
        bundle = compile_adblock(LIST)

        async def go():
            async with AdblockBrowserSession(bundle) as sess:
                return await sess.browse(
                    "data:text/html," + PAGE, host="test.com", timeout=10)

        body = asyncio.run(go())
        self.assertIn("markdown", body)
        text = "\n".join(body["markdown"])
        self.assertIn("genuine editorial content", text)
        self.assertNotIn("BUY NOW", text)
        self.assertNotIn("Sponsored content you should not see", text)
        self.assertIn("Organic content you should see", text)

    def test_network_blocked_pixel_never_reaches_dom_text(self):
        # the tracking pixel is blocked at the CDP Fetch seam, so its subresource
        # never loads; the page text stays clean and the img stays unloaded.
        bundle = compile_adblock(LIST)

        async def go():
            async with AdblockBrowserSession(bundle) as sess:
                return await sess.browse(
                    "data:text/html," + PAGE, host="test.com", timeout=10)

        body = asyncio.run(go())
        self.assertNotIn("ads.example.com/pixel.gif",
                         "\n".join(body["markdown"]))


if __name__ == "__main__":
    unittest.main()
