"""Procedural (``#?#``) rules: parse and emit a JS filter."""
import unittest

from src.browser_engine.procedural import compile_procedural, procedural_js


class TestCompileProcedural(unittest.TestCase):
    def test_has_text_test_extracted(self):
        rules = compile_procedural(
            ["discord.com#?#.wrapper:has-text(Get Reward)"])
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["base"], ".wrapper")
        self.assertEqual(rules[0]["tests"], [("has-text", "Get Reward")])
        self.assertEqual(rules[0]["domains"], ["discord.com"])

    def test_multiple_tests(self):
        rules = compile_procedural(
            ["x.com#?#.row:has(.ad):has-text(Sponsored)"])
        self.assertEqual(rules[0]["tests"],
                         [("has-text", "Sponsored"), ("has", ".ad")])

    def test_exception_rule(self):
        rules = compile_procedural(["a.com#@?#.ad:has-text(x)"])
        self.assertEqual(rules[0]["exceptions"], ["a.com"])

    def test_non_procedural_lines_ignored(self):
        rules = compile_procedural([
            "! comment",
            "a.com##.banner",
            "a.com##+js(nowoif)",
        ])
        self.assertEqual(rules, [])


class TestProceduralJs(unittest.TestCase):
    def test_emits_rule_payload(self):
        rules = compile_procedural(["x.com#?#.ad:has-text(Sponsored)"])
        js = procedural_js(rules, host="www.x.com")
        self.assertIn(".ad", js)
        self.assertIn("Sponsored", js)
        self.assertIn("has-text", js)

    def test_domain_scope_respected(self):
        rules = compile_procedural(["other.com#?#.ad:has-text(x)"])
        self.assertEqual(procedural_js(rules, host="x.com"), "")

    def test_exception_cancels(self):
        rules = compile_procedural([
            "#?#.ad:has-text(x)",
            "x.com#@?#.ad:has-text(x)",
        ])
        self.assertEqual(procedural_js(rules, host="x.com"), "")


if __name__ == "__main__":
    unittest.main()
