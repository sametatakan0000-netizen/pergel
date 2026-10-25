"""A1 native capability: cookie/consent annoyance hiding rides the existing
cosmetic layer. Uses real public lists when present (live), else skips."""
import os
import unittest

from src.browser_engine.adblock_session import load_adblock_bundle

LIST_DIR = os.path.expanduser("~/.local/share/browser_farm/filterlists")
COOKIE_LISTS = [
    os.path.join(LIST_DIR, f)
    for f in ("annoyances-cookies.txt", "easylist_cookie_general_hide.txt",
              "easylist_cookie_specific_hide.txt")
]


@unittest.skipUnless(all(os.path.exists(p) for p in COOKIE_LISTS),
                     "cookie filter lists not downloaded")
class CookieAnnoyanceTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_adblock_bundle(COOKIE_LISTS)

    def test_cookie_lists_compile_into_cosmetic_layer(self):
        # RED before fix: stats showed cosmetic=0 when paths were wrong;
        # with real lists we must get thousands of hide rules.
        self.assertGreater(self.bundle.stats["cosmetic"], 10000)

    def test_known_consent_banner_selectors_present(self):
        selectors = {r["selector"] for r in self.bundle.cosmetic}
        for sel in ("#cookie-law", "#cmplz-cookiebanner-container"):
            self.assertIn(sel, selectors)

    def test_cookie_rules_apply_to_all_domains_when_unscoped(self):
        rule = next(r for r in self.bundle.cosmetic
                    if r["selector"] == "#cookie-law")
        self.assertEqual(rule["domains"], ["*"])


if __name__ == "__main__":
    unittest.main()
