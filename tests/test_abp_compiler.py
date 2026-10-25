import unittest

from src.browser_engine.abp_compiler import compile_abp_lines
from src.browser_engine.rule_engine import compile_rules


class TestAbpLineClassification(unittest.TestCase):
    def test_comments_and_headers_skipped(self):
        result = compile_abp_lines(["[Adblock Plus 2.0]", "! Title: x", ""])
        self.assertEqual(result.rules, [])
        self.assertEqual(result.stats.skipped_comment, 3)

    def test_cosmetic_rules_skipped_and_counted(self):
        result = compile_abp_lines(["example.com##.ad-banner", "##.generic"])
        self.assertEqual(result.rules, [])
        self.assertEqual(result.stats.skipped_cosmetic, 2)


class TestAbpNetworkRules(unittest.TestCase):
    def test_domain_anchor_becomes_request_domain(self):
        result = compile_abp_lines(["||doubleclick.net^"])
        rule = result.rules[0]
        self.assertEqual(rule["action"]["type"], "block")
        self.assertEqual(rule["condition"]["requestDomains"], ["doubleclick.net"])

    def test_plain_pattern_becomes_url_filter(self):
        result = compile_abp_lines(["/banners/ad_"])
        self.assertEqual(result.rules[0]["condition"]["urlFilter"], "/banners/ad_")

    def test_exception_becomes_allow_rule(self):
        result = compile_abp_lines(["||doubleclick.net^", "@@||doubleclick.net/safe.js"])
        types = [r["action"]["type"] for r in result.rules]
        self.assertEqual(types, ["block", "allow"])

    def test_resource_type_options_mapped(self):
        result = compile_abp_lines(["||ads.io^$script,image"])
        self.assertEqual(sorted(result.rules[0]["condition"]["resourceTypes"]),
                         ["image", "script"])

    def test_document_option_maps_to_main_frame(self):
        result = compile_abp_lines(["||1asb.com^$document"])
        self.assertEqual(result.rules[0]["condition"]["resourceTypes"], ["main_frame"])

    def test_unsupported_options_skip_rule_and_count(self):
        result = compile_abp_lines([
            "||a.io^$domain=example.com",
            "||b.io^$redirect=noop.js",
            "||c.io^$csp=script-src 'none'",
        ])
        self.assertEqual(result.rules, [])
        self.assertEqual(result.stats.skipped_unsupported, 3)

    def test_negated_resource_type_maps_to_exclusion(self):
        result = compile_abp_lines(["||ads.io^$~image"])
        rc = result.rules[0]["condition"]["excludedResourceTypes"]
        self.assertEqual(rc, ["image"])

    def test_compiled_rules_are_loadable_by_engine(self):
        result = compile_abp_lines(["||tracker.io^$image", "@@||tracker.io/ok.gif"])
        engine = compile_rules(result.rules)
        self.assertEqual(
            engine.check("https://tracker.io/x.gif", resource_type="image").action, "block")
        self.assertEqual(
            engine.check("https://tracker.io/ok.gif", resource_type="image").action, "allow")


class TestAbpScaleAndStats(unittest.TestCase):
    def test_stats_add_up(self):
        lines = ["! c", "##.x", "||a.io^", "@@||a.io/ok", "||b.io^$domain=x", "/plain"]
        result = compile_abp_lines(lines)
        s = result.stats
        self.assertEqual(s.total, len(lines))
        self.assertEqual(
            s.compiled + s.skipped_comment + s.skipped_cosmetic + s.skipped_unsupported,
            s.total)
        self.assertEqual(len(result.rules), s.compiled)

    def test_ids_are_unique_and_sequential(self):
        result = compile_abp_lines([f"||h{i}.io^" for i in range(100)])
        ids = [r["id"] for r in result.rules]
        self.assertEqual(ids, list(range(1, 101)))


if __name__ == "__main__":
    unittest.main()
