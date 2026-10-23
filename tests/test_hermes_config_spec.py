from pathlib import Path
import subprocess
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
from src.infra.hermes_config_builder import (
    build_optimal_hermes_spec,
    generate_hermes_cli_commands,
)


class TestHermesConfigSpec(unittest.TestCase):
    def test_optimal_hermes_spec_contains_all_11_real_aux_tasks_and_custom_oracle_proxy(self):
        spec = build_optimal_hermes_spec()
        expected_aux = {
            "title_generation",
            "vision",
            "compression",
            "approval",
            "web_extract",
            "skills_hub",
            "mcp",
            "triage_specifier",
            "kanban_decomposer",
            "profile_describer",
            "curator",
        }
        self.assertEqual(set(spec["auxiliary"].keys()), expected_aux)
        # Approval & low-cost aux slots use real Nous Portal free/95%-off models
        self.assertIn(
            spec["auxiliary"]["approval"]["model"],
            {"upstage/solar-mini4", "qwen/qwen3.8-27b", "deepseek/deepseek-v4.1-flash-1017"},
        )
        # Vision uses strong multimodal model
        self.assertEqual(
            spec["auxiliary"]["vision"]["model"], "google/gemini-4-argon"
        )
        # Named Custom Provider proxy bridging Hermes -> oracle router (:8090, LiveRouter) -> hermes proxy (:8645 -> Nous Portal)
        self.assertIn("oracle-router", spec["providers"])
        oracle_prov = spec["providers"]["oracle-router"]
        self.assertEqual(oracle_prov["api"], "http://127.0.0.1:8090/v1")
        self.assertEqual(oracle_prov["session_affinity_header"], "x-hermes-session-id")
        self.assertEqual(oracle_prov["catalog_provider"], "nous")
        self.assertEqual(spec["nous"]["anthropic_wire"], "chat")
        self.assertEqual(spec["subscription_proxy"]["upstream_url"], "http://127.0.0.1:8645/v1")

        # Immutable Core checkpoints & Delegation scaling
        self.assertTrue(spec["checkpoints"]["enabled"])
        self.assertEqual(spec["delegation"]["max_concurrent_children"], 10)
        # Per-capability split search/extract
        self.assertEqual(spec["web"]["search_provider"], "searxng")
        self.assertEqual(spec["web"]["extract_provider"], "firecrawl")
        # MoA preset validation
        moa_default = spec["moa"]["presets"]["default"]
        self.assertEqual(moa_default["fanout"], "every_n:3")
        self.assertEqual(spec["moa"]["privacy_filter"], "display")

        cmds = generate_hermes_cli_commands(spec)
        self.assertFalse(any("hermes proxy start" in c for c in cmds))
        self.assertFalse(any("smart_model_routing" in c for c in cmds))
        self.assertFalse(any("hermes config set model.provider" in c for c in cmds))
        self.assertTrue(any("hermes config set providers.oracle-router.api http://127.0.0.1:8090/v1" in c for c in cmds))
        self.assertFalse(any("skills install" in c or "FIRECRAWL_API_URL" in c for c in cmds))

    def test_cli_exposes_serving_and_catalog_refresh_commands(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.cli", "--help"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        self.assertIn("serve", result.stdout)
        self.assertIn("refresh-catalog", result.stdout)

    def test_doctor_does_not_report_ready_without_upstream(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.cli", "doctor"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        report = __import__("json").loads(result.stdout)
        self.assertNotEqual(report["status"], "READY")


if __name__ == "__main__":
    unittest.main()
