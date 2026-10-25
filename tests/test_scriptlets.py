"""Scriptlet rules (``##+js(...)``) and procedural cosmetic rules (``#?#``)."""
import unittest

from src.browser_engine.scriptlets import (
    compile_scriptlets,
    scriptlet_js,
    supported_scriptlets,
)


class TestCompileScriptlets(unittest.TestCase):
    def test_basic_rule(self):
        rules = compile_scriptlets(["example.com##+js(set-constant, ads, false)"])
        self.assertEqual(len(rules), 1)
        r = rules[0]
        self.assertEqual(r["name"], "set-constant")
        self.assertEqual(r["args"], ["ads", "false"])
        self.assertEqual(r["domains"], ["example.com"])
        self.assertEqual(r["exceptions"], [])

    def test_unscoped_rule(self):
        rules = compile_scriptlets(["##+js(nowoif)"])
        self.assertEqual(rules[0]["domains"], [])
        self.assertEqual(rules[0]["args"], [])

    def test_multiple_domains(self):
        rules = compile_scriptlets(["a.com,b.com##+js(nowoif)"])
        self.assertEqual(rules[0]["domains"], ["a.com", "b.com"])

    def test_exception_rule(self):
        rules = compile_scriptlets(["example.com#@#+js(nowoif)"])
        self.assertEqual(rules[0]["exceptions"], ["example.com"])

    def test_quoted_args_keep_commas(self):
        rules = compile_scriptlets(
            ["example.com##+js(replace-xhr-response, '\"a,b\"', 'x')"])
        self.assertEqual(rules[0]["args"][0], "'\"a,b\"'")

    def test_non_scriptlet_lines_ignored(self):
        rules = compile_scriptlets([
            "! comment",
            "example.com##.ad-banner",
            "||example.com^$third-party",
        ])
        self.assertEqual(rules, [])


class TestScriptletJs(unittest.TestCase):
    def test_emits_call_for_supported_scriptlet(self):
        js = scriptlet_js(compile_scriptlets(["example.com##+js(nowoif)"]),
                          host="www.example.com")
        self.assertIn("nowoif()", js)

    def test_unsupported_scriptlet_skipped(self):
        js = scriptlet_js(
            compile_scriptlets(["example.com##+js(trusted-replace-xhr-response)"]),
            host="www.example.com")
        self.assertEqual(js, "")

    def test_domain_scope_respected(self):
        rules = compile_scriptlets(["other.com##+js(nowoif)"])
        self.assertEqual(scriptlet_js(rules, host="example.com"), "")

    def test_helper_defined_once_for_many_rules(self):
        rules = compile_scriptlets([
            "a.com##+js(set-constant, x, 1)",
            "b.com##+js(set-constant, y, 2)",
        ])
        js = scriptlet_js(rules, host="a.com")
        self.assertEqual(js.count("function setc("), 1)
        self.assertIn("setc(\"x\", \"1\")", js)

    def test_allowlist_covers_common_families(self):
        sup = supported_scriptlets()
        for name in ("abort-on-property-read", "set-constant",
                     "addEventListener-defuser", "no-setInterval-if"):
            self.assertIn(name, sup)


if __name__ == "__main__":
    unittest.main()
