"""Aho-Corasick matcher for the literal-filter bucket.

Matching N literal substrings with N x str.find is O(N * text). The automaton
finds all of them in one pass: O(text + matches). This is the last piece that
keeps the engine's promise of sublinear matching on real blocklists.
"""
import time
import unittest

from src.browser_engine.aho_corasick import AhoCorasick


class TestAhoCorasickMatches(unittest.TestCase):
    def test_single_pattern_found(self):
        ac = AhoCorasick(["/ads/"])
        self.assertEqual(ac.find("https://x.io/ads/b.gif"), {"/ads/"})

    def test_no_match_returns_empty(self):
        ac = AhoCorasick(["/ads/"])
        self.assertEqual(ac.find("https://x.io/main.css"), set())

    def test_multiple_overlapping_patterns_all_found(self):
        ac = AhoCorasick(["ads", "ads/banner", "banner"])
        self.assertEqual(ac.find("xx/ads/banner_x"), {"ads", "ads/banner", "banner"})

    def test_empty_pattern_set_matches_nothing(self):
        ac = AhoCorasick([])
        self.assertEqual(ac.find("anything"), set())

    def test_pattern_at_end_of_text(self):
        ac = AhoCorasick([".gif"])
        self.assertEqual(ac.find("https://x.io/a.gif"), {".gif"})

    def test_prefix_chain_reports_all(self):
        ac = AhoCorasick(["a", "ab", "abc"])
        self.assertEqual(ac.find("zzabc"), {"a", "ab", "abc"})


class TestAhoCorasickPerformance(unittest.TestCase):
    def test_many_patterns_match_in_one_pass(self):
        patterns = [f"/trk{i}/" for i in range(2000)]
        ac = AhoCorasick(patterns)
        text = "https://example.org/some/long/path/with/segments/index.html"
        t0 = time.perf_counter()
        n = 2000
        for _ in range(n):
            ac.find(text)
        per = (time.perf_counter() - t0) / n * 1e6
        # 2000 patterns in one pass must be far cheaper than 2000 substring scans.
        self.assertLess(per, 50.0, f"{per:.1f}us per find() is too slow for 2000 patterns")

    def test_beats_naive_scan(self):
        import bisect
        patterns = [f"/trk{i}/" for i in range(2000)]
        ac = AhoCorasick(patterns)
        text = "https://example.org/some/long/path/index.html"
        n = 2000
        t0 = time.perf_counter()
        for _ in range(n):
            ac.find(text)
        ac_us = (time.perf_counter() - t0) / n * 1e6
        t0 = time.perf_counter()
        for _ in range(n):
            for p in patterns:
                bisect.bisect_left([text.find(p)], 0)
        naive_us = (time.perf_counter() - t0) / n * 1e6
        self.assertLess(ac_us, naive_us, f"Aho-Corasick ({ac_us:.0f}us) must beat naive scan ({naive_us:.0f}us)")


if __name__ == "__main__":
    unittest.main()
