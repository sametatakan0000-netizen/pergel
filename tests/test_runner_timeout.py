"""Regression: a hanging adapter must not stall the whole benchmark run.

`run_cell` runs every lifecycle under a wall-clock timeout. A target whose
`start()`/`fetch()` hangs (e.g. a GUI browser failing to bind headless CDP) is
marked as timed_out and skipped, so the remaining targets still get measured.
"""
import time
import unittest

from src.bench.runner import Scenario, Target, run_cell

SC = Scenario("static", "/static", "MARKER")


class _HangingAdapter:
    def start(self):
        time.sleep(30)  # simulates connect_over_cdp blocking forever

    def fetch(self, url, marker):
        raise AssertionError("should not reach fetch once start hangs")

    def root_pids(self):
        return []

    def stop(self):
        pass


class RunCellTimeoutTests(unittest.TestCase):
    def test_hanging_start_is_marked_and_skipped(self):
        target = Target("hang", _HangingAdapter)
        t0 = time.perf_counter()
        rows = run_cell(target, SC, "http://x", lifecycles=3, warmups=1, fetches=1,
                        timeout_s=0.4)
        elapsed = time.perf_counter() - t0
        # Must return promptly, not block for the 30 s hang.
        self.assertLess(elapsed, 5.0)
        # Every lifecycle reported as timed out, with no fake timings.
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r["target"], "hang")
            self.assertTrue(r.get("timed_out"))
            self.assertIsNone(r.get("fetch_ms_median"))

    def test_hanging_one_target_does_not_affect_next(self):
        # A healthy adapter after a hanging one still produces real rows.
        class _OkAdapter:
            def start(self): pass
            def fetch(self, url, marker):
                class _R:
                    ok = True
                    ms = 12.0
                return _R()
            def root_pids(self):
                return []
            def stop(self): pass

        run_cell(Target("hang", _HangingAdapter), SC, "http://x", lifecycles=1,
                 warmups=1, fetches=1, timeout_s=0.3)
        rows = run_cell(Target("ok", _OkAdapter), SC, "http://x", lifecycles=2,
                        warmups=1, fetches=3, timeout_s=2.0)
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0].get("timed_out"))
        self.assertEqual(rows[0]["fetch_ms_median"], 12.0)


if __name__ == "__main__":
    unittest.main()
