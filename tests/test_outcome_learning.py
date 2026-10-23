import os
import tempfile
import unittest

from src.router.outcome_learning import (
    OutcomeLearner,
    StreamAccumulator,
    analyze_response,
    bucket_for,
    is_correction,
)

TOOLS = [{"type": "function", "function": {"name": "terminal"}}]


def user(text):
    return {"role": "user", "content": text}


class TestStructuralAnalysis(unittest.TestCase):
    def test_valid_tool_call_is_ok_and_not_final(self):
        body = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "terminal", "arguments": "{\"cmd\": \"ls\"}"}}]},
            "finish_reason": "tool_calls"}]}
        self.assertEqual(analyze_response(body, TOOLS), (True, False, "tool_calls_ok"))

    def test_malformed_arguments_and_unknown_tools_fail(self):
        bad_json = {"choices": [{"message": {"tool_calls": [
            {"function": {"name": "terminal", "arguments": "{cmd: ls"}}]}}]}
        self.assertEqual(analyze_response(bad_json, TOOLS)[2], "malformed_tool_arguments")
        unknown = {"choices": [{"message": {"tool_calls": [
            {"function": {"name": "rm_everything", "arguments": "{}"}}]}}]}
        self.assertEqual(analyze_response(unknown, TOOLS)[2], "unknown_tool")

    def test_empty_answer_fails_and_text_answer_is_final(self):
        self.assertEqual(analyze_response({"choices": [{"message": {"content": "  "}}]}, TOOLS)[:2], (False, False))
        self.assertEqual(analyze_response({"choices": [{"message": {"content": "Tamam."}}]}, TOOLS), (True, True, "answer"))

    def test_stream_accumulator_rebuilds_tool_call_arguments(self):
        acc = StreamAccumulator()
        for line in [
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"terminal","arguments":"{\\"cmd\\""}}]}}]}\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \\"ls\\"}"}}]}}]}\n',
            b'data: [DONE]\n',
        ]:
            acc.feed(line)
        self.assertEqual(analyze_response(acc.as_response(), TOOLS), (True, False, "tool_calls_ok"))

    def test_corrections_are_detected_in_turkish_and_english(self):
        for text in ("Yanlış, bu olmadı", "hayır öyle değil", "that's wrong", "doesn't work"):
            self.assertTrue(is_correction(text), text)
        for text in ("teşekkürler, şimdi testleri yaz", "great, next step"):
            self.assertFalse(is_correction(text), text)

    def test_bucket_combines_keyword_tier_modality_and_size(self):
        self.assertEqual(bucket_for({"messages": [user("merhaba")]}, keyword_tier=1), "t1:txt:s")
        big = {"messages": [user("x" * 300000)]}
        self.assertEqual(bucket_for(big, keyword_tier=2), "t2:txt:l")


class TestOutcomeLearner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rolls = []
        self.learner = OutcomeLearner(os.path.join(self.tmp.name, "l.db"), rng=lambda: 0.99, clock=lambda: 1005.0)

    def tearDown(self):
        self.tmp.cleanup()

    def respond(self, session, model, final=True, ok=True, tier=1, bucket="t1:txt:s", now=1000.0):
        self.learner.on_response(session, model, bucket, tier, structural_ok=ok, final_answer=final,
                                 last_user_hash=self.learner.last_user_hash(self.msgs), msg_count=len(self.msgs), now=now)

    def test_user_retry_penalizes_previous_model(self):
        self.msgs = [user("soru")]
        self.respond("s", "m/a")
        self.learner.on_request("s", {"messages": [user("soru")]}, now=1001.0)  # regenerate
        self.assertLess(self.learner.reliability("m/a", "t1:txt:s"), 0.5)

    def test_continuing_after_final_answer_rewards_model(self):
        self.msgs = [user("soru")]
        self.respond("s", "m/a")
        self.learner.on_request("s", {"messages": [user("soru"), {"role": "assistant", "content": "cevap"},
                                                   user("harika, devam")]}, now=1001.0)
        self.assertGreater(self.learner.reliability("m/a", "t1:txt:s"), 0.5)

    def test_correction_penalizes_and_tool_loops_are_neutral(self):
        self.msgs = [user("soru")]
        self.respond("s", "m/a", final=False)  # tool call turn: next request ends with a tool result
        self.learner.on_request("s", {"messages": [user("soru"), {"role": "tool", "content": "ok"}]}, now=1001.0)
        self.assertAlmostEqual(self.learner.reliability("m/a", "t1:txt:s"), 0.5 + 0.0, delta=0.06)
        self.respond("s", "m/a", final=True)
        self.learner.on_request("s", {"messages": [user("soru"), user("yanlış oldu bu")]}, now=1002.0)
        self.assertLess(self.learner.reliability("m/a", "t1:txt:s"), 0.5)

    def test_structural_failures_are_recorded_immediately(self):
        self.msgs = [user("x")]
        for _ in range(3):
            self.respond("s", "m/bad", ok=False, final=False)
        self.assertLess(self.learner.reliability("m/bad", "t1:txt:s"), 0.3)

    def test_evidence_decays_with_half_life(self):
        self.learner.record("m/a", "b", 1, neg=4.0, reason="t", now=0.0)
        early = self.learner.reliability("m/a", "b", now=0.0)
        late = self.learner.reliability("m/a", "b", now=14 * 86400 * 6)  # six half-lives later
        self.assertLess(early, 0.25)
        self.assertGreater(late, 0.45)

    def test_failing_bucket_raises_start_tier_and_logs_decision(self):
        self.assertEqual(self.learner.start_tier("t1:txt:s", keyword_tier=1, now=10.0), 1)  # no evidence yet
        for i in range(6):
            self.learner.record(f"m/{i % 2}", "t1:txt:s", 1, neg=1.0, reason="user_retry", now=10.0)
        self.learner.record("m/0", "t1:txt:s", 1, pos=1.0, reason="continued", now=10.0)
        self.assertEqual(self.learner.start_tier("t1:txt:s", keyword_tier=1, now=11.0), 2)
        events = self.learner.evolution_events()
        self.assertTrue(any(e["kind"] == "floor_raised" and e["bucket"] == "t1:txt:s" for e in events))

    def test_exploration_occasionally_tries_one_tier_lower(self):
        explorer = OutcomeLearner(os.path.join(self.tmp.name, "e.db"), rng=lambda: 0.01, epsilon=0.05)
        self.assertEqual(explorer.start_tier("t3:txt:s", keyword_tier=3, now=1.0), 2)
        self.assertEqual(explorer.start_tier("t1:txt:s", keyword_tier=1, now=1.0), 1)  # cannot go below 1


if __name__ == "__main__":
    unittest.main()
