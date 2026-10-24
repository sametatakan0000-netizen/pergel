import unittest

from src.bench.report import aggregate, render_markdown


def rows(target, fetch_ms, n=10, pss=50_000):
    return [{"target": target, "scenario": "static", "lifecycle": i, "cold_start_ms": 100.0,
             "success_rate": 1.0, "fetch_ms_median": fetch_ms + i * 0.01, "peak_pss_kib": pss, "cpu_s": 0.5}
            for i in range(n)]


ENV = {"cpu_model": "X", "nproc": 12, "kernel": "k", "loadavg_1m": 0.2, "git_sha": "abc", "timestamp": "t"}


class ReportTests(unittest.TestCase):
    def test_claimable_ratio_is_rendered(self):
        md = render_markdown(rows("chrome", 100.0) + rows("lp", 10.0), ENV, baseline_id="chrome")
        self.assertIn("×", md)
        self.assertIn("10.0×", md)

    def test_overlap_prints_no_ratio(self):
        md = render_markdown(rows("chrome", 100.0) + rows("other", 100.0), ENV, baseline_id="chrome")
        self.assertNotIn("×", md)
        self.assertIn("no significant difference", md)

    def test_failed_engine_shows_success_rate_not_latency(self):
        bad = [dict(r, success_rate=0.0, fetch_ms_median=None) for r in rows("lp", 1.0)]
        md = render_markdown(rows("chrome", 100.0) + bad, ENV, baseline_id="chrome")
        self.assertIn("0%", md)
        self.assertIn("n/a", md)

    def test_env_and_methodology_footer_present(self):
        md = render_markdown(rows("chrome", 100.0), ENV, baseline_id="chrome")
        self.assertIn("git abc", md)
        self.assertIn("lifecycles", md)

    def test_aggregate_groups_by_target_and_scenario(self):
        agg = aggregate(rows("a", 1.0) + rows("b", 2.0))
        self.assertEqual(set(agg), {("a", "static"), ("b", "static")})
