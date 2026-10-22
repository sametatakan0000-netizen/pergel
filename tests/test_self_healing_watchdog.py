import unittest
from src.infra.self_healing_watchdog import SelfHealingWatchdog


class TestSelfHealingWatchdog(unittest.TestCase):
    def test_watchdog_rotates_expired_token_and_restarts_unhealthy_service(self):
        restarted = []
        rotated = []
        watchdog = SelfHealingWatchdog(
            health_probes={"firecrawl": lambda: False, "searxng": lambda: True},
            restart_fn=lambda svc: restarted.append(svc) or True,
            token_ttl_check=lambda: 120,
            token_refresh_fn=lambda: rotated.append("refreshed") or True,
        )
        report = watchdog.run_cycle()
        self.assertIn("firecrawl", restarted)
        self.assertNotIn("searxng", restarted)
        self.assertEqual(rotated, ["refreshed"])
        self.assertEqual(report["healed_services"], ["firecrawl"])
        self.assertTrue(report["token_refreshed"])


if __name__ == "__main__":
    unittest.main()
