import unittest

from src.router.moa_exec import (DRAFT_HEADER, MAX_DRAFT_CHARS, build_aggregator_payload,
                                 draft_text, member_usage_summary, run_members)


def ok(text):
    return 200, {"choices": [{"message": {"role": "assistant", "content": text}}]}


class TestMoaExec(unittest.TestCase):
    def test_draft_text_handles_content_tool_calls_and_empty(self):
        self.assertEqual(draft_text({"choices": [{"message": {"content": " hi "}}]}), "hi")
        tc = {"choices": [{"message": {"content": "", "tool_calls": [
            {"function": {"name": "terminal", "arguments": "{\"command\":\"ls\"}"}}]}}]}
        self.assertIn("proposed tool call: terminal", draft_text(tc))
        self.assertIsNone(draft_text({"choices": [{"message": {"content": "  "}}]}))
        self.assertIsNone(draft_text({}))
        self.assertLessEqual(len(draft_text({"choices": [{"message": {"content": "x" * 99999}}]})),
                             MAX_DRAFT_CHARS)

    def test_members_run_non_streaming_and_failures_are_dropped(self):
        seen = {}

        def call(model_id, payload):
            seen[model_id] = payload.get("stream")
            if model_id == "bad":
                return 500, {}
            if model_id == "boom":
                raise OSError("down")
            return ok(f"answer from {model_id}")

        payload = {"model": "oracle/auto", "stream": True, "stream_options": {"x": 1},
                   "messages": [{"role": "user", "content": "q"}]}
        drafts = run_members(call, ["m1", "bad", "boom", "m2"], payload)
        self.assertEqual([m for m, _ in drafts], ["m1", "m2"])
        self.assertTrue(all(v is False for v in seen.values()))

    def test_aggregator_gets_drafts_before_last_user_turn_and_tools_untouched(self):
        payload = {"model": "oracle/auto", "tools": [{"type": "function"}],
                   "messages": [{"role": "system", "content": "sys"},
                                {"role": "user", "content": "old"},
                                {"role": "assistant", "content": "a"},
                                {"role": "user", "content": "new"}]}
        out = build_aggregator_payload(payload, [("m1", "draft one")])
        self.assertEqual(out["tools"], payload["tools"])
        self.assertEqual(out["messages"][-2]["role"], "system")
        self.assertIn(DRAFT_HEADER, out["messages"][-2]["content"])
        self.assertIn("draft one", out["messages"][-2]["content"])
        self.assertEqual(out["messages"][-1]["content"], "new")
        self.assertEqual(len(payload["messages"]), 4)  # input not mutated

    def test_no_drafts_means_unchanged_messages(self):
        payload = {"messages": [{"role": "user", "content": "q"}]}
        self.assertEqual(build_aggregator_payload(payload, [])["messages"], payload["messages"])

    def test_usage_summary_reports_used_and_dropped(self):
        s = member_usage_summary([("m1", "x")], ["m1", "m2"])
        self.assertEqual(s, {"attempted": ["m1", "m2"], "used": ["m1"], "dropped": ["m2"]})


if __name__ == "__main__":
    unittest.main()
