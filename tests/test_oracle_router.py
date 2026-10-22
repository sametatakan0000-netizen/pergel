import tempfile
import os
import unittest
from src.router.oracle_router import DynamicOracleRouter, OracleSignal


class TestOracleRouter(unittest.TestCase):
    def test_cascading_escalation_from_tier1_to_tier3_on_oracle_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "router.db")
            router = DynamicOracleRouter(db_path=db_path, half_life_seconds=3600)
            calls = []

            def fake_executor(model_id: str, prompt: str) -> str:
                calls.append(model_id)
                if model_id != "google/gemini-4-argon":
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
            self.assertEqual(result["final_model"], "google/gemini-4-argon")
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


if __name__ == "__main__":
    unittest.main()
