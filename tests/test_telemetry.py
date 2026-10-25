import unittest

from src.browser_engine.rule_engine import compile_rules
from src.browser_engine.telemetry import RuleStats


class TestRuleStats(unittest.TestCase):
    def setUp(self):
        self.stats = RuleStats()

    def test_counts_by_action(self):
        self.stats.record("block", rule_id=1)
        self.stats.record("block", rule_id=1)
        self.stats.record("allow", rule_id=None)
        self.stats.record("redirect", rule_id=2)
        self.assertEqual(self.stats.totals(), {"block": 2, "allow": 1, "redirect": 1})

    def test_top_rules_by_count(self):
        for _ in range(5):
            self.stats.record("block", rule_id=7)
        self.stats.record("block", rule_id=8)
        self.assertEqual(self.stats.top_rules(2), [(7, 5), (8, 1)])

    def test_top_rules_excludes_allow_without_rule(self):
        self.stats.record("allow", rule_id=None)
        self.stats.record("block", rule_id=1)
        self.assertEqual(self.stats.top_rules(), [(1, 1)])

    def test_zero_snapshot_is_empty(self):
        self.assertEqual(self.stats.totals(), {})
        self.assertEqual(self.stats.top_rules(), [])

    def test_total_decisions(self):
        self.stats.record("block", rule_id=1)
        self.stats.record("allow", rule_id=None)
        self.assertEqual(self.stats.total_decisions(), 2)

    def test_totals_and_top_rules_after_bridge_dispatch(self):
        from src.browser_engine.cdp_bridge import CDPBridge
        from src.browser_engine.telemetry import RuleStats

        engine = compile_rules([
            {"id": 42, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["ads.example"], "resourceTypes": ["image"]}},
        ])
        stats = RuleStats()
        bridge = CDPBridge(engine, lambda m: None, stats=stats)
        bridge.on_request_paused({"requestId": "1",
                                  "request": {"url": "https://ads.example/x.gif"},
                                  "resourceType": "Image"})
        bridge.on_request_paused({"requestId": "2",
                                  "request": {"url": "https://ok.example/y.js"},
                                  "resourceType": "Script"})
        self.assertEqual(stats.totals(), {"block": 1, "allow": 1})
        self.assertEqual(stats.top_rules(), [(42, 1)])
        self.assertEqual(stats.total_decisions(), 2)


if __name__ == "__main__":
    unittest.main()
