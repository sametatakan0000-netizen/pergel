import unittest

from src.bench.adapters import FetchResult
from src.bench.env import capture_env
from src.bench.runner import Scenario, Target, run_cell


class FakeAdapter:
    def __init__(self, ok=True, ms=5.0):
        self.id, self._ok, self._ms = "fake", ok, ms

    def start(self): pass
    def stop(self): pass
    def root_pids(self): return []

    def fetch(self, url, marker, timeout_s=30.0):
        return FetchResult(self._ok, self._ms, 100 if self._ok else 0, "" if self._ok else "Boom")


class RunnerTests(unittest.TestCase):
    def test_run_cell_produces_one_row_per_lifecycle(self):
        t = Target("fake", lambda: FakeAdapter(True, 5.0))
        rows = run_cell(t, Scenario("static", "/static", "M"), "http://x", lifecycles=4, warmups=1, fetches=3)
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["target"] for r in rows}, {"fake"})
        self.assertEqual(rows[0]["success_rate"], 1.0)
        self.assertEqual(rows[0]["fetch_ms_median"], 5.0)
        self.assertIn("cold_start_ms", rows[0])
        self.assertIn("peak_pss_kib", rows[0])

    def test_failing_engine_records_zero_success_and_no_latency(self):
        t = Target("bad", lambda: FakeAdapter(False))
        rows = run_cell(t, Scenario("spa", "/spa", "M"), "http://x", lifecycles=2, warmups=0, fetches=2)
        self.assertEqual(rows[0]["success_rate"], 0.0)
        self.assertIsNone(rows[0]["fetch_ms_median"])

    def test_env_has_reproducibility_fields(self):
        env = capture_env()
        for key in ("cpu_model", "nproc", "mem_total_kib", "kernel", "loadavg_1m", "python", "git_sha", "timestamp"):
            self.assertIn(key, env)
