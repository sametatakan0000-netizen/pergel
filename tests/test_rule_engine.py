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


class TestModifyHeaders(unittest.TestCase):
    """modifyHeaders must apply real header set/remove/append operations."""

    def test_set_request_header(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "modifyHeaders",
                        "requestHeaders": [{"header": "DNT", "operation": "set", "value": "1"}]},
             "condition": {"requestDomains": ["tracker.io"]}},
        ])
        d = engine.check("https://tracker.io/p.gif", resource_type="image")
        self.assertEqual(d.action, "modifyHeaders")
        self.assertEqual(d.request_header_ops, [
            {"header": "DNT", "operation": "set", "value": "1"}])

    def test_remove_request_header(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "modifyHeaders",
                        "requestHeaders": [{"header": "Referer", "operation": "remove"}]},
             "condition": {"requestDomains": ["tracker.io"]}},
        ])
        d = engine.check("https://tracker.io/p.gif")
        self.assertEqual(d.request_header_ops, [
            {"header": "Referer", "operation": "remove"}])

    def test_append_response_header(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "modifyHeaders",
                        "responseHeaders": [{"header": "X-Frame-Options", "operation": "set",
                                             "value": "DENY"}]},
             "condition": {"requestDomains": ["tracker.io"]}},
        ])
        d = engine.check("https://tracker.io/p.gif")
        self.assertEqual(d.response_header_ops, [
            {"header": "X-Frame-Options", "operation": "set", "value": "DENY"}])

    def test_apply_to_headers_produces_modified_copy(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "modifyHeaders",
                        "requestHeaders": [
                            {"header": "DNT", "operation": "set", "value": "1"},
                            {"header": "Referer", "operation": "remove"}]},
             "condition": {"requestDomains": ["tracker.io"]}},
        ])
        d = engine.check("https://tracker.io/p.gif")
        original = {"Referer": "https://news.example", "Accept": "image/*"}
        out = d.apply_to_headers(original, response=False)
        self.assertEqual(out, {"Accept": "image/*", "DNT": "1"})
        # original untouched
        self.assertEqual(original, {"Referer": "https://news.example", "Accept": "image/*"})

    def test_append_operation_adds_comma_value(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "modifyHeaders",
                        "requestHeaders": [{"header": "Accept", "operation": "append",
                                            "value": "image/webp"}]},
             "condition": {"requestDomains": ["tracker.io"]}},
        ])
        d = engine.check("https://tracker.io/p.gif")
        out = d.apply_to_headers({"Accept": "image/*"}, response=False)
        self.assertEqual(out["Accept"], "image/*, image/webp")

    def test_unknown_operation_rejected(self):
        with self.assertRaises(ValueError):
            compile_rules([
                {"id": 1, "priority": 1,
                 "action": {"type": "modifyHeaders",
                            "requestHeaders": [{"header": "X", "operation": "explode"}]},
                 "condition": {"requestDomains": ["tracker.io"]}},
            ])


class TestUrlFilter(unittest.TestCase):
    """urlFilter (AdBlock-ish wildcard) and regexFilter matching on the URL."""

    def test_url_filter_substring(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/ads/", "resourceTypes": ["script"]}},
        ])
        d = engine.check("https://cdn.example.com/ads/banner.js", resource_type="script")
        self.assertEqual(d.action, "block")

    def test_url_filter_no_match(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/ads/", "resourceTypes": ["script"]}},
        ])
        d = engine.check("https://cdn.example.com/app/main.js", resource_type="script")
        self.assertEqual(d.action, "allow")

    def test_url_filter_wildcard_star(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/track/*/pixel.gif", "resourceTypes": ["image"]}},
        ])
        self.assertEqual(
            engine.check("https://t.io/track/abc/pixel.gif", resource_type="image").action,
            "block")
        self.assertEqual(
            engine.check("https://t.io/track/abc/other.gif", resource_type="image").action,
            "allow")

    def test_url_filter_anchor_caret_matches_start(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "||tracker.io^", "resourceTypes": ["image"]}},
        ])
        self.assertEqual(
            engine.check("https://tracker.io/p.gif", resource_type="image").action, "block")

    def test_url_filter_plus_means_literal_plus(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "a+b", "resourceTypes": ["other"]}},
        ])
        self.assertEqual(engine.check("https://x.io/a+b", resource_type="other").action, "block")
        self.assertEqual(engine.check("https://x.io/ab", resource_type="other").action, "allow")


class TestRegexFilter(unittest.TestCase):
    def test_regex_filter_matches(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"regexFilter": r"/banner\d+\.gif$", "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://x.io/img/banner42.gif", resource_type="image")
        self.assertEqual(d.action, "block")

    def test_regex_filter_no_match(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"regexFilter": r"/banner\d+\.gif$", "resourceTypes": ["image"]}},
        ])
        d = engine.check("https://x.io/img/hero.png", resource_type="image")
        self.assertEqual(d.action, "allow")


class TestRegexSafetyGuard(unittest.TestCase):
    """MV3 rejects 'unsafe' regexes (catastrophic backtracking risk). Our
    compiler must refuse them rather than ship a DoS."""

    def test_nested_quantifier_rejected(self):
        with self.assertRaises(ValueError):
            compile_rules([
                {"id": 1, "priority": 1, "action": {"type": "block"},
                 "condition": {"regexFilter": r"(a+)+$"}},
            ])

    def test_alternating_quantifier_rejected(self):
        with self.assertRaises(ValueError):
            compile_rules([
                {"id": 1, "priority": 1, "action": {"type": "block"},
                 "condition": {"regexFilter": r"(a|a)*$"}},
            ])

    def test_simple_regex_accepted(self):
        compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"regexFilter": r"/banner\d+\.gif$"}},
        ])  # should not raise


class TestGlobalBucketPerformance(unittest.TestCase):
    """A domain-agnostic bucket is unavoidable (unanchored filters match any
    host), but it must be cheap: literal-only filters use str.find, wildcards
    use a build-time-compiled regex — never per-query translation."""

    def test_global_rules_stay_sublinear_per_query(self):
        rules = [{"id": i, "priority": 1, "action": {"type": "block"},
                  "condition": {"urlFilter": f"/tracker{i}/"}} for i in range(2000)]
        rules += [{"id": 2000 + i, "priority": 1, "action": {"type": "block"},
                   "condition": {"urlFilter": f"/pixel{i}/*.gif"}} for i in range(500)]
        engine = compile_rules(rules)
        import time
        t0 = time.perf_counter()
        n = 200
        for _ in range(n):
            engine.check("https://x.example.org/main.css")
        per = (time.perf_counter() - t0) / n * 1e6
        # 2500 global rules must not cost milliseconds per query.
        self.assertLess(per, 2000.0, f"{per:.0f}us per query is too slow")

    def test_literal_global_rule_matches_via_substring(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/ads/banner_"}}])
        self.assertEqual(
            engine.check("https://x.io/ads/banner_7.png", resource_type="image").action,
            "block")

    def test_wildcard_global_rule_still_matches(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/track/*/pixel.gif"}}])
        self.assertEqual(
            engine.check("https://x.io/track/ab/pixel.gif", resource_type="image").action,
            "block")
        self.assertEqual(
            engine.check("https://x.io/track/ab/other.gif", resource_type="image").action,
            "allow")


class TestQuotaBreakingRealList(unittest.TestCase):
    """Regression guard for the real-list pathology: domain-anchored urlFilter
    rules (e.g. "||doubleclick.net/ads/") must be INDEXED, not added to a
    per-request global scan."""

    @staticmethod
    def _anchored(domain, path=""):
        return {"id": hash((domain, path)) % 100000, "priority": 1,
                "action": {"type": "block"},
                "condition": {"urlFilter": f"||{domain}/{path}"}}

    def test_domain_anchored_url_filter_is_indexed_not_global(self):
        engine = compile_rules([self._anchored("doubleclick.net", "ads/")])
        engine.check("https://unrelated.example.org/main.css")
        # The doubleclick rule must NOT have been a candidate for unrelated.host.
        self.assertLess(engine.last_candidate_count, 1)

    def test_domain_anchored_url_filter_still_matches_its_domain(self):
        engine = compile_rules([self._anchored("doubleclick.net", "ads/")])
        d = engine.check("https://ad.doubleclick.net/ads/x.gif")
        self.assertEqual(d.action, "block")

    def test_unanchored_pattern_still_scans_globally(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/ads/"}}])
        d = engine.check("https://anywhere.example/ads/x.gif")
        self.assertEqual(d.action, "block")

    def test_many_anchored_filters_do_not_blow_up_candidate_count(self):
        rules = [self._anchored(f"host{i}.net", "ads/") for i in range(2000)]
        engine = compile_rules(rules)
        engine.check("https://unrelated.example.org/a.css")
        self.assertLess(engine.last_candidate_count, 20)

    def test_domain_indexed_rules_dont_leak_to_sibling_host(self):
        engine = compile_rules([self._anchored("otherhost.net", "ads/")])
        d = engine.check("https://host0.net/ads/x.gif")
        self.assertEqual(d.action, "allow")


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
