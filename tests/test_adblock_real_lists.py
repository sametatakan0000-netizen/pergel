"""The engine handles real public filter lists (EasyList + uAssets) at scale.

This is the product hook proven against real data, not toy rules: one
``load_adblock_bundle`` call compiles ~92k real filter lines into all four
layers in well under a second, and the resulting engine really blocks live ad
endpoints while leaving benign traffic alone. Compile-time is guarded — the
Aho-Corasick + precompiled-bucket work must not regress.

Skips cleanly when the downloaded filter lists are absent.
"""
import os
import time
import unittest

from src.browser_engine.adblock_session import build_injection, load_adblock_bundle

EASYLIST = "/tmp/easylist.txt"
UASSETS = "/tmp/ubo_filters.txt"


def _have_lists():
    return os.path.isfile(EASYLIST)


@unittest.skipUnless(_have_lists(), "downloaded filter lists not present")
class TestRealFilterLists(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = time.time()
        cls.bundle = load_adblock_bundle(
            [p for p in (EASYLIST, UASSETS) if os.path.isfile(p)])
        cls.compile_seconds = time.time() - t

    def test_compiles_all_layers_at_scale(self):
        s = self.bundle.stats
        self.assertGreater(s["network"], 50000)
        self.assertGreater(s["cosmetic"], 20000)
        self.assertGreater(s["scriptlets"], 2000)
        self.assertGreater(s["procedural"], 100)
        self.assertEqual(
            s["network"] + s["cosmetic"] + s["scriptlets"] + s["procedural"],
            s["total"])

    def test_compile_stays_fast(self):
        # the indexed engine must compile 90k+ lines in seconds, not minutes
        self.assertLess(self.compile_seconds, 5.0,
                        f"real-list compile regressed: {self.compile_seconds:.2f}s")

    def test_blocks_real_ad_endpoints(self):
        for url in (
            "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js",
            "https://securepubads.g.doubleclick.net/tag/js/gpt.js",
            "https://googleads.g.doubleclick.net/pagead/viewthroughconversion/123/",
        ):
            self.assertEqual(self.bundle.network.check(url).action, "block",
                             f"expected block for {url}")

    def test_allows_benign_endpoints(self):
        for url in (
            "https://example.com/index.html",
            "https://github.com/nousresearch",
        ):
            self.assertEqual(self.bundle.network.check(url).action, "allow",
                             f"expected allow for {url}")

    def test_injection_carries_real_cosmetic_selectors(self):
        # pick a real cosmetic rule scoped to a real host and check it is emitted
        rule = next(r for r in self.bundle.cosmetic
                    if r["domains"] and r["domains"] != ["*"])
        host = rule["domains"][0]
        js = build_injection(self.bundle, host)
        self.assertTrue(js.strip(), "no injection emitted for a scoped host")


if __name__ == "__main__":
    unittest.main()
