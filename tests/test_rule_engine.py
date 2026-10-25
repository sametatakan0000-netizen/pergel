"""Rule engine prototype: MV3-style declarative rules with a rule-quota-breaking
domain index. This is the "blocking DNR super-extension layer" differentiator
from docs/rea/positioning-synthesis.md §7 decisions 2 & 9.
"""
import unittest

from src.browser_engine.rule_engine import RuleEngine, compile_rules


class TestMatchDomain(unittest.TestCase):
    def test_exact_domain_matches(self):
        self.assertTrue(RuleEngine.match_domain("doubleclick.net", "doubleclick.net"))

    def test_subdomain_matches_subdomain_pattern(self):
        self.assertTrue(RuleEngine.match_domain("ad.doubleclick.net", "doubleclick.net"))

    def test_parent_does_not_match_subdomain_pattern(self):
        self.assertFalse(RuleEngine.match_domain("doubleclick.net", "ad.doubleclick.net"))

    def test_unrelated_domain_does_not_match(self):
        self.assertFalse(RuleEngine.match_domain("example.org", "doubleclick.net"))

    def test_case_and_trailing_dot_are_normalized(self):
        self.assertTrue(RuleEngine.match_domain("AD.DoubleClick.NET.", "doubleclick.net"))


class TestCheckDecision(unittest.TestCase):
    def _engine(self, rules):
        return compile_rules(rules)

    def test_block_rule_blocks_matching_image(self):
        engine = self._engine([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://ad.doubleclick.net/x.gif", resource_type="image")
        self.assertEqual(d.action, "block")
        self.assertEqual(d.rule_id, 1)

    def test_no_matching_rule_allows(self):
        engine = self._engine([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://example.org/index.html", resource_type="main_frame")
        self.assertEqual(d.action, "allow")
        self.assertIsNone(d.rule_id)

    def test_resource_type_mismatch_allows(self):
        engine = self._engine([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://ad.doubleclick.net/x.gif", resource_type="script")
        self.assertEqual(d.action, "allow")

    def test_allow_rule_overrides_block_even_at_lower_priority(self):
        engine = self._engine([
            {"id": 1, "priority": 100, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
            {"id": 2, "priority": 1, "action": {"type": "allow"},
             "condition": {"requestDomains": ["ad.doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://ad.doubleclick.net/x.gif", resource_type="image")
        self.assertEqual(d.action, "allow")
        self.assertEqual(d.rule_id, 2)

    def test_redirect_rule_carries_target(self):
        engine = self._engine([
            {"id": 7, "priority": 1,
             "action": {"type": "redirect", "redirect": {"url": "https://localhost/pixel.png"}},
             "condition": {"requestDomains": ["tracker.io"], "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://tracker.io/p.gif", resource_type="image")
        self.assertEqual(d.action, "redirect")
        self.assertEqual(d.redirect_url, "https://localhost/pixel.png")


class TestRuleQuotaBreaking(unittest.TestCase):
    """MV3 caps static DNR rules at 30k/extension. Our index must handle far
    more and, crucially, match without scanning the whole list."""

    def test_32k_rules_beyond_mv3_quota_match_correctly(self):
        rules = [
            {"id": i, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": [f"host{i}.net"], "resourceTypes": ["image"]}}
            for i in range(32_000)
        ]
        engine = compile_rules(rules)
        self.assertGreater(len(rules), 30_000)  # beyond the MV3 static quota
        d = engine.check("https://host31999.net/a.png", resource_type="image")
        self.assertEqual(d.action, "block")
        self.assertEqual(d.rule_id, 31_999)
        d2 = engine.check("https://host0.net/a.png", resource_type="image")
        self.assertEqual(d2.rule_id, 0)

    def test_match_scans_candidates_not_whole_rule_list(self):
        rules = [
            {"id": i, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": [f"host{i}.net"], "resourceTypes": ["image"]}}
            for i in range(32_000)
        ]
        engine = compile_rules(rules)
        engine.check("https://host12345.net/a.png", resource_type="image")
        # The whole point of the domain index: a lookup must not walk all 32k.
        self.assertLess(engine.last_candidate_count, 10)


if __name__ == "__main__":
    unittest.main()
