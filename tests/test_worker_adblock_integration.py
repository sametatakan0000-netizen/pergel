"""Live e2e: the adblock engine plugs into the real ``BrowserWorker`` pipeline.

``make_adblock_driver`` adapts the enforced CDP session to the worker's sync
``driver_fn(engine, url, session_name) -> raw_html`` contract. The worker then
runs ``html_to_clean_markdown`` on the enforced HTML. This proves the product's
actual fetch path emits ad-free markdown — the integration the isolated layers
alone could not demonstrate.

Unscoped rules are used so enforcement does not depend on URL host derivation.
Skips cleanly without Chromium/websockets.
"""
import unittest

from tests.test_cdp_e2e_live import _find_chromium, websockets
from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import make_adblock_driver
from src.browser_engine.worker import html_to_clean_markdown

# Unscoped (## with no domain) => applies to every host; network rule is URL-matched.
LIST = [
    "||ads.example.com^",                        # network block
    "##.sponsored-ad",                           # cosmetic hide (all hosts)
    "#?#.slot:has-text(Sponsored)",              # procedural hide (all hosts)
]

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


class TestWorkerAdblockIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _find_chromium() is None or websockets is None:
            raise unittest.SkipTest("no chromium binary or websockets lib")

    def test_worker_pipeline_emits_adfree_markdown(self):
        bundle = compile_adblock(LIST)
        driver = make_adblock_driver(bundle)

        raw_html = driver("chromium-browser-use", "data:text/html," + PAGE,
                          "sess-integration")

        # the enforced raw HTML still carries the real article
        self.assertIn("genuine editorial content", raw_html)
        # and every hidden ad node has been removed from the DOM
        self.assertNotIn("BUY NOW", raw_html)                    # cosmetic-removed
        self.assertNotIn("Sponsored content you should not see",
                         raw_html)                               # procedural-removed
        self.assertIn("Organic content you should see", raw_html)  # organic kept

        # the worker's own markdown extraction is therefore ad-free
        md = html_to_clean_markdown(raw_html)
        self.assertIn("genuine editorial content", md)
        self.assertNotIn("BUY NOW", md)
        self.assertNotIn("Sponsored content you should not see", md)
        self.assertIn("Organic content you should see", md)


if __name__ == "__main__":
    unittest.main()
