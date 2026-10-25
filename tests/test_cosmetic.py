import unittest

from src.browser_engine.abp_compiler import compile_cosmetic
from src.browser_engine.cosmetic import cosmetic_css


class TestCosmeticCompiler(unittest.TestCase):
    def test_unscoped_rule(self):
        rules = compile_cosmetic(["##.sponsored-ad"])
        self.assertEqual(rules, [{"selector": ".sponsored-ad", "domains": [],
                                  "exceptions": []}])

    def test_domain_scoped_rule(self):
        rules = compile_cosmetic(["example.com##.banner"])
        self.assertEqual(rules, [{"selector": ".banner", "domains": ["example.com"],
                                  "exceptions": []}])

    def test_multiple_domains_comma_separated(self):
        rules = compile_cosmetic(["a.com,b.com##.x"])
        self.assertEqual(rules[0]["domains"], ["a.com", "b.com"])

    def test_exception_rule_flags_exclusion(self):
        rules = compile_cosmetic(["example.com#@#.banner"])
        self.assertEqual(rules, [{"selector": ".banner", "domains": ["example.com"],
                                  "exceptions": ["example.com"]}])

    def test_comments_and_blank_lines_skipped(self):
        self.assertEqual(compile_cosmetic(["! comment", "", "##.real"]), [
            {"selector": ".real", "domains": [], "exceptions": []}])

    def test_network_rule_is_not_cosmetic(self):
        self.assertEqual(compile_cosmetic(["||ads.example.com^", "/banner/*/img.gif"]), [])


class TestCosmeticCss(unittest.TestCase):
    def test_unscoped_selector_matches_any_host(self):
        css = cosmetic_css([{"selector": ".ad", "domains": [], "exceptions": []}],
                           host="anything.example")
        self.assertIn(".ad", css)

    def test_scoped_selector_only_for_matching_host(self):
        rules = [{"selector": ".ad", "domains": ["example.com"], "exceptions": []}]
        self.assertIn(".ad", cosmetic_css(rules, host="www.example.com"))
        self.assertEqual(cosmetic_css(rules, host="other.example").strip(), "")

    def test_exception_removes_selector(self):
        rules = [
            {"selector": ".ad", "domains": [], "exceptions": []},
            {"selector": ".ad", "domains": ["ok.example"], "exceptions": ["ok.example"]},
        ]
        self.assertEqual(cosmetic_css(rules, host="ok.example").strip(), "")
        self.assertIn(".ad", cosmetic_css(rules, host="else.example"))

    def test_output_is_valid_css_block(self):
        css = cosmetic_css([{"selector": ".ad, #x", "domains": [], "exceptions": []}],
                           host="h.example")
        self.assertRegex(css, r"\{[^}]*display:\s*none")


if __name__ == "__main__":
    unittest.main()
