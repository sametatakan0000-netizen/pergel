import unittest
from src.net_lab.sober_net_diagnostics import analyze_socket_trace_and_recommend_routing
from src.browser_engine.browser_orchestrator import BrowserFarmOrchestrator


class TestNetDiagnosticsAndBrowserOrchestrator(unittest.TestCase):
    def test_socket_trace_analyzer_identifies_timeout_and_reset_endpoints(self):
        sample_trace = (
            'connect(14, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("128.116.102.3")}, 16) = -1 ETIMEDOUT\n'
            'write(14, "TLS_HANDSHAKE", 517) = -1 ECONNRESET'
        )
        report = analyze_socket_trace_and_recommend_routing(sample_trace)
        self.assertEqual(report["detected_issue"], "TLS_HANDSHAKE_RESET_OR_TIMEOUT")
        self.assertIn("128.116.102.3", report["affected_ips"])
        self.assertEqual(report["recommended_mtu"], 1400)
        self.assertTrue(report["evidence_tagged"])

    def test_browser_farm_orchestrator_isolates_sessions_and_selects_engine(self):
        orch = BrowserFarmOrchestrator()
        self.assertEqual(
            orch.select_engine(needs_vision=False, js_complexity="low"),
            "lightpanda",
        )
        self.assertEqual(
            orch.select_engine(needs_vision=True, js_complexity="high"),
            "chromium-browser-use",
        )
        self.assertEqual(
            orch.select_engine(needs_vision=True, js_complexity="isolated_profile"),
            "camofox",
        )
        spec = orch.build_session_task(
            "job-101",
            url="https://target.example.com",
            needs_vision=True,
            js_complexity="high",
            webhook_url="https://callback.example.com/hook",
        )
        self.assertEqual(spec["session_name"], "farm_job-101")
        self.assertEqual(spec["engine"], "chromium-browser-use")
        self.assertEqual(spec["webhook_url"], "https://callback.example.com/hook")


if __name__ == "__main__":
    unittest.main()
