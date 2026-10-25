import unittest

from src.browser_engine.rule_engine import compile_rules


class TestWildcardPreFilter(unittest.TestCase):
    """Wildcard rules can't use Aho-Corasick (they aren't plain substrings),
    but their longest literal chunk is a cheap pre-check: if the chunk is
    absent from the URL, the regex must not run at all."""

    def test_literal_chunk_rejects_without_running_regex(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/track/*/pixel.gif"}},
        ])
        runs = []
        rule_id = id(engine._rules[0])
        real = engine._compiled_regex[rule_id]

        class Spy:
            def search(self, s):
                runs.append(1)
                return real.search(s)

        engine._compiled_regex[rule_id] = Spy()
        d = engine.check("https://x.io/other/path.js")
        self.assertEqual(d.action, "allow")
        self.assertEqual(runs, [], "regex must not run when the literal chunk is absent")

    def test_literal_chunk_does_not_change_correctness(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/track/*/pixel.gif"}}])
        self.assertEqual(
            engine.check("https://x.io/track/ab/pixel.gif", resource_type="image").action,
            "block")
        self.assertEqual(
            engine.check("https://x.io/track/ab/other.gif", resource_type="image").action,
            "allow")

    def test_multi_wildcard_pattern_uses_longest_chunk(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "/a/*/very/long/chunk/*/z.gif"}}])
        self.assertEqual(
            engine.check("https://x.io/a/bb/z.gif", resource_type="image").action, "allow")
        self.assertEqual(
            engine.check("https://x.io/a/bb/very/long/chunk/cc/z.gif",
                         resource_type="image").action, "block")

    def test_pattern_without_wildcard_still_works(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"urlFilter": "||tracker.io/ads/banner"}}])
        self.assertEqual(
            engine.check("https://tracker.io/ads/banner.png", resource_type="image").action,
            "block")


if __name__ == "__main__":
    unittest.main()
