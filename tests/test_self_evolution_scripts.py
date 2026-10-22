import unittest
from src.devtools.self_evolution_engine import (
    compute_ecosystem_fingerprint,
    distill_evolution_record,
    evaluate_silent_watchdog,
)


class TestSelfEvolutionScripts(unittest.TestCase):
    def test_silent_watchdog_returns_empty_string_when_all_healthy(self):
        out = evaluate_silent_watchdog(
            disk_free_gb=50.0,
            failed_tests=0,
            unhealthy_services=[],
        )
        self.assertEqual(out, "")

    def test_silent_watchdog_emits_alert_only_on_anomaly(self):
        out = evaluate_silent_watchdog(
            disk_free_gb=2.0,
            failed_tests=1,
            unhealthy_services=["firecrawl"],
        )
        self.assertIn("ANOMALY_DETECTED", out)
        self.assertIn("firecrawl", out)

    def test_ecosystem_fingerprint_and_three_mode_evolution_distiller(self):
        state = {
            "repos": {"rtk-ai/rtk": "v1.0.1", "DietrichGebert/ponytail": "v5.3.2"},
            "skills_count": 49,
        }
        fp1 = compute_ecosystem_fingerprint(state)
        fp2 = compute_ecosystem_fingerprint(state)
        self.assertEqual(fp1, fp2)

        rec = distill_evolution_record(
            mode="CAPTURED",
            source="tirth8205/code-review-graph",
            decision="Add AST dead-code and change-risk scoring to local codebase graph",
            evidence="65x-357x token reduction on codebase queries",
        )
        self.assertEqual(rec["mode"], "CAPTURED")
        self.assertIn("65x-357x", rec["compact_entry"])


if __name__ == "__main__":
    unittest.main()
