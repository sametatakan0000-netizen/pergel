import os
import unittest

from src.bench.suites.browserbench import (
    LIGHTPANDA_STATUS,
    extract_jetstream_score,
    extract_speedometer_score,
    run_suite,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


class _FakeAdapter:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def fetch(self, url, timeout_s=None):
        self.calls.append((url, timeout_s))
        return self.html


class TestScoreParsers(unittest.TestCase):
    """Task 3.1 — score extraction from captured suite-result HTML (hermetic)."""

    def test_speedometer_score_extracted(self):
        score = extract_speedometer_score(fixture("speedometer31_result.html"))
        self.assertAlmostEqual(score, 38.42, places=2)

    def test_speedometer_error_rejected(self):
        html = '<div id="result-number">Error</div><div id="confidence-number"></div>'
        with self.assertRaises(ValueError) as ctx:
            extract_speedometer_score(html)
        self.assertIn("Error", str(ctx.exception))

    def test_speedometer_missing_result_element_raises(self):
        with self.assertRaises(ValueError):
            extract_speedometer_score("<section id='summary'>no result here</section>")

    def test_jetstream_score_extracted(self):
        score = extract_jetstream_score(fixture("jetstream3_result.html"))
        self.assertAlmostEqual(score, 469.07, places=2)

    def test_jetstream_integer_score_parses(self):
        html = '<div class="score">469</div><label>Score</label>'
        self.assertAlmostEqual(extract_jetstream_score(html), 469.0, places=2)

    def test_jetstream_missing_score_raises(self):
        with self.assertRaises(ValueError):
            extract_jetstream_score('<div id="result-summary">not run yet</div>')


class TestRunSuite(unittest.TestCase):
    def test_run_suite_dispatches_by_url(self):
        cases = [
            ("https://browserbench.org/Speedometer3.1/?startAutomatically=1",
             "speedometer31_result.html", 38.42),
            ("https://browserbench.org/JetStream3.0/?startAutomatically=1",
             "jetstream3_result.html", 469.07),
        ]
        for url, name, expected in cases:
            adapter = _FakeAdapter(fixture(name))
            score = run_suite(adapter, url, timeout_s=120)
            self.assertAlmostEqual(score, expected, places=2)
            self.assertEqual(adapter.calls, [(url, 120)])

    def test_unknown_suite_url_rejected(self):
        adapter = _FakeAdapter("<html></html>")
        with self.assertRaises(ValueError):
            run_suite(adapter, "https://example.com/other", timeout_s=5)

    def test_lightpanda_reported_not_as_zero(self):
        self.assertEqual(LIGHTPANDA_STATUS, "n/a (unsupported Web APIs)")


if __name__ == "__main__":
    unittest.main()
