import unittest

from src.bench.fixture_server import fixture_server
from src.bench.suites.fidelity import run_fidelity


class TestFidelitySuite(unittest.TestCase):
    """Task 3.4 — no-LLM task-fidelity micro-suite on the deterministic fixtures."""

    def test_all_cases_pass_on_fixtures(self):
        with fixture_server() as base:
            report = run_fidelity(base)
        for name, reason in report["failed"].items():
            self.fail(f"fidelity case {name!r} failed: {reason}")
        self.assertEqual(sorted(report["passed"]), sorted([
            "api_discovery_recall", "boilerplate_removal",
            "robots_block_never_escalates", "body_cap_2mb",
        ]))

    def test_dead_base_reports_reasons_without_crashing(self):
        # nothing listens on port 1: cases must report failure reasons, not raise
        report = run_fidelity("http://127.0.0.1:1")
        self.assertGreaterEqual(len(report["failed"]), 3)
        for reason in report["failed"].values():
            self.assertIsInstance(reason, str)
            self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
