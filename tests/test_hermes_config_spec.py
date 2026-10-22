import unittest
from src.infra.hermes_config_builder import (
    build_optimal_hermes_spec,
    generate_hermes_cli_commands,
)


class TestHermesConfigSpec(unittest.TestCase):
    def test_optimal_hermes_spec_contains_all_11_real_aux_tasks_and_invariants(self):
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
        # Approval must use a fast/cheap model, not the expensive main model
        self.assertIn(
            spec["auxiliary"]["approval"]["model"],
            {"google/gemini-3.7-flash:free", "qwen/qwen3.6-27b"},
        )
        # Vision uses strong multimodal model
        self.assertEqual(
            spec["auxiliary"]["vision"]["model"], "google/gemini-4-argon"
        )
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
        self.assertTrue(any("hermes config set model.default google/gemini-4-argon" in c for c in cmds))
        self.assertTrue(any("hermes config set SEARXNG_URL http://localhost:8888" in c for c in cmds))
        self.assertTrue(any("hermes config set FIRECRAWL_API_URL http://localhost:3002" in c for c in cmds))


if __name__ == "__main__":
    unittest.main()
