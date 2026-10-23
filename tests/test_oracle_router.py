import os
import tempfile
import unittest
from src.router.oracle_router import (
    NOUS_CURATED_CATALOG_IDS,
    DynamicOracleRouter,
    OracleSignal,
)


class TestOracleRouter(unittest.TestCase):
    def test_cascading_escalation_from_tier1_to_tier3_on_oracle_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "router.db")
            router = DynamicOracleRouter(db_path=db_path, half_life_seconds=3600)
            calls = []

            def fake_executor(model_id: str, prompt: str) -> str:
                calls.append(model_id)
                if model_id not in {"google/gemini-4-argon", "openai/gpt-6.1-sol"}:
                    return "INVALID_OUTPUT"
                return '{"status": "ok", "code": "valid"}'

            result = router.route_and_execute(
                prompt="Karmaşık mimari tasarım ve kod üret",
                task_type="coding",
                executor=fake_executor,
                oracle_validator=lambda out: OracleSignal(
                    passed=out.startswith("{"), channel="strong"
                ),
            )
            self.assertIn(
                result["final_model"], {"google/gemini-4-argon", "openai/gpt-6.1-sol"}
            )
            self.assertGreaterEqual(len(calls), 2)

    def test_half_life_decay_reduces_old_failure_penalty(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "router.db")
            router = DynamicOracleRouter(db_path=db_path, half_life_seconds=10)
            now = 1000.0
            router.record_outcome(
                "deepseek/deepseek-v4-pro",
                passed=False,
                channel="strong",
                timestamp=now - 100.0,
            )
            score_decayed = router.get_model_score(
                "deepseek/deepseek-v4-pro", now=now
            )
            router.record_outcome(
                "openai/gpt-6-sol",
                passed=False,
                channel="strong",
                timestamp=now - 1.0,
            )
            score_recent_fail = router.get_model_score("openai/gpt-6-sol", now=now)
            self.assertGreater(score_decayed, score_recent_fail)

    def test_self_evolving_router_adapts_task_tier_floor_and_emits_evolution_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "router.db")
            router = DynamicOracleRouter(db_path=db_path, half_life_seconds=3600)

            tier1_set = set(router.tiers[0])

            def strict_executor(model_id: str, prompt: str) -> str:
                if model_id in tier1_set:
                    return "FAIL_TIER_1"
                return '{"valid": true}'

            # Enough strong failures in Tier 1 to drop tier score <= TIER_DEMOTION_THRESHOLD
            for _ in range(2):
                router.route_and_execute(
                    prompt="Derin tersine mühendislik analizi",
                    task_type="rea_binary_audit",
                    executor=strict_executor,
                    oracle_validator=lambda out: OracleSignal(
                        passed=out.startswith("{"), channel="strong"
                    ),
                )

            self.assertEqual(router.get_task_tier_floor("rea_binary_audit"), 2)

            calls_after_evolution = []

            def tracking_executor(model_id: str, prompt: str) -> str:
                calls_after_evolution.append(model_id)
                return '{"valid": true}'

            res = router.route_and_execute(
                prompt="Yeni binary analizi",
                task_type="rea_binary_audit",
                executor=tracking_executor,
                oracle_validator=lambda out: OracleSignal(
                    passed=out.startswith("{"), channel="strong"
                ),
            )
            self.assertEqual(res["attempts"][0]["tier"], 2)
            self.assertEqual(len(calls_after_evolution), 1)

            ledger = router.get_evolution_ledger()
            self.assertGreaterEqual(len(ledger), 1)
            self.assertEqual(ledger[-1]["mode"], "DERIVED")
            self.assertIn("rea_binary_audit", ledger[-1]["compact_entry"])

    def test_full_57_model_nous_catalog_live_promos_and_adaptive_tuning(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "router.db")
            router = DynamicOracleRouter(db_path=db_path, half_life_seconds=3600)

            # Verify all 57 official Nous Portal catalog models + free portal models are present
            self.assertGreaterEqual(len(NOUS_CURATED_CATALOG_IDS), 57)
            for mid in NOUS_CURATED_CATALOG_IDS:
                self.assertIn(mid, router.inventory)

            # Verify live portal promos and free models from portal.nousresearch.com/models
            self.assertEqual(router.inventory["upstage/solar-mini4"].input_cost_per_mtok, 0.0)
            self.assertEqual(router.inventory["meituan/longcat-2.5-preview"].input_cost_per_mtok, 0.0)
            self.assertAlmostEqual(router.inventory["qwen/qwen3.8-27b"].input_cost_per_mtok, 0.02)
            self.assertIn("95%", router.inventory["qwen/qwen3.8-27b"].sale_badge)
            self.assertAlmostEqual(
                router.inventory["deepseek/deepseek-v4.1-flash-1017"].input_cost_per_mtok, 0.07
            )
            self.assertTrue(router.inventory["z-ai/glm-5.2"].is_silent_default)

            # Verify dynamic catalog sync ingests new Nous Portal models and logs CAPTURED evolution
            added = router.sync_live_model_catalog(
                {
                    "providers": {
                        "nous": {
                            "models": [
                                {"id": "nousresearch/hermes-5-frontier"},
                            ]
                        }
                    }
                }
            )
            self.assertEqual(added, ["nousresearch/hermes-5-frontier"])
            self.assertIn("nousresearch/hermes-5-frontier", router.inventory)

            # Verify adaptive parameter fine-tuning (reasoning_effort, temperature, speed variant)
            base_tuning = router.get_adaptive_tuning("deepseek/deepseek-v4-pro", "exploit_synthesis")
            self.assertEqual(base_tuning["reasoning_effort"], "medium")

            router.record_outcome(
                "deepseek/deepseek-v4-pro",
                passed=False,
                channel="strong",
                task_type="exploit_synthesis",
            )
            evolved_tuning = router.get_adaptive_tuning("deepseek/deepseek-v4-pro", "exploit_synthesis")
            self.assertEqual(evolved_tuning["reasoning_effort"], "high")
            self.assertLess(evolved_tuning["temperature"], base_tuning["temperature"])

            # Verify rich "who is who" persona metadata and persistent MODEL_PROFILES.json export
            argon_prof = router.inventory["google/gemini-4-argon"]
            self.assertTrue(argon_prof.role_persona)
            self.assertIn("multimodal_vision", argon_prof.strengths)
            self.assertGreaterEqual(argon_prof.context_window, 200000)
            self.assertEqual(argon_prof.discount_pct, 50)

            out_json = os.path.join(tmp, "MODEL_PROFILES.json")
            exported = router.export_model_profiles_json(out_json)
            self.assertTrue(os.path.exists(out_json))
            self.assertGreaterEqual(exported["total_models"], 64)
            self.assertIn("qwen/qwen3.8-27b", exported["profiles"])
            self.assertIn("role_persona", exported["profiles"]["qwen/qwen3.8-27b"])
            self.assertEqual(exported["profiles"]["qwen/qwen3.8-27b"]["metadata_status"], "unverified")
            self.assertNotIn("google/gemini-3.7-flash:free", router.tiers[0])

    def test_catalog_refresh_persists_verified_ids_without_guessing_capabilities(self):
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread

        class Catalog(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                data = json.dumps({"version": 1, "providers": {"nous": {
                    "models": [{"id": "test/new-model", "default": False}]
                }}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        catalog = ThreadingHTTPServer(("127.0.0.1", 0), Catalog)
        thread = Thread(target=catalog.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = os.path.join(tmp, "router.db")
                url = f"http://127.0.0.1:{catalog.server_port}/catalog.json"
                router = DynamicOracleRouter(db_path=db_path)
                self.assertEqual(router.refresh_catalog(url), ["test/new-model"])
                new_profile = router.inventory["test/new-model"]
                self.assertFalse(new_profile.supports_vision)
                self.assertFalse(new_profile.supports_tools)
                self.assertIn("test/new-model", DynamicOracleRouter(db_path=db_path).inventory)
        finally:
            catalog.shutdown()
            catalog.server_close()
            thread.join(timeout=3)

    def test_catalog_sync_rejects_unverified_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = DynamicOracleRouter(db_path=os.path.join(tmp, "router.db"))
            with self.assertRaises(ValueError):
                router.sync_live_model_catalog({"providers": {"nous": {"models": "not a list"}}})
            self.assertNotIn("n", router.inventory)


if __name__ == "__main__":
    unittest.main()
