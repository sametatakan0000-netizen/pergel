import os
import tempfile
import unittest

from src.router.live_router import LiveRouter, price_tier
from src.router.model_registry import build_profiles

CATALOG = {"version": 1, "providers": {"nous": {"models": [
    {"id": "v/free-text"}, {"id": "v/cheap-vision"}, {"id": "v/mid"},
    {"id": "v/flagship"}, {"id": "v/apex"}, {"id": "v/no-meta"},
]}}}


def meta(cost_in, cost_out, vision=False, efforts=("low", "medium", "high"), ctx=200000):
    return {
        "tool_call": True, "reasoning": bool(efforts),
        "reasoning_options": [{"type": "effort", "values": list(efforts)}] if efforts else [],
        "modalities": {"input": ["text", "image"] if vision else ["text"]},
        "limit": {"context": ctx}, "cost": {"input": cost_in, "output": cost_out},
    }


MODELS_DEV = {"openrouter": {"models": {
    "v/free-text": meta(0, 0, efforts=("none", "high")),
    "v/cheap-vision": meta(0.1, 0.4, vision=True),
    "v/mid": meta(0.9, 3.0),
    "v/flagship": meta(2.0, 10.0, vision=True, efforts=("low", "medium", "high", "max")),
    "v/apex": meta(10.0, 50.0, vision=True, efforts=("low", "medium", "high", "xhigh", "max")),
}}}


def chat(text, image=False, tools=False, model="oracle/auto", **extra):
    content = [{"type": "text", "text": text}]
    if image:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}})
    payload = {"model": model, "messages": [{"role": "user", "content": content}], **extra}
    if tools:
        payload["tools"] = [{"type": "function", "function": {"name": "terminal"}}]
    return payload


class TestLiveRouter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "router.db")
        self.profiles = build_profiles(CATALOG, MODELS_DEV, fetched_at="t")
        self.router = LiveRouter(self.db, self.profiles)

    def tearDown(self):
        self.tmp.cleanup()

    def test_price_tier_bands_are_explicit(self):
        self.assertEqual(price_tier(self.profiles["v/free-text"]), 1)
        self.assertEqual(price_tier(self.profiles["v/cheap-vision"]), 1)
        self.assertEqual(price_tier(self.profiles["v/mid"]), 2)
        self.assertEqual(price_tier(self.profiles["v/flagship"]), 3)
        self.assertEqual(price_tier(self.profiles["v/apex"]), 4)

    def test_simple_chat_uses_cheapest_and_vision_filters_candidates(self):
        self.assertEqual(self.router.plan(chat("merhaba"))[0], "v/free-text")
        self.assertEqual(self.router.plan(chat("bu ne?", image=True))[0], "v/cheap-vision")

    def test_premium_profile_and_architecture_requests_start_higher(self):
        self.assertEqual(self.router.plan(chat("mimari tasarım analizi"))[0], "v/flagship")
        self.assertEqual(self.router.plan(chat("selam", model="oracle/premium"))[0], "v/apex")

    def test_candidates_are_ordered_fallbacks_and_never_unverified(self):
        plan = self.router.plan(chat("merhaba"))
        self.assertEqual(plan[:2], ["v/free-text", "v/cheap-vision"])
        self.assertNotIn("v/no-meta", plan)

    def test_free_profile_only_returns_zero_cost_models(self):
        self.assertEqual(self.router.plan(chat("x", model="oracle/free")), ["v/free-text"])
        self.assertEqual(self.router.plan(chat("x", image=True, model="oracle/free")), [])

    def test_session_affinity_persists_across_restarts(self):
        self.router.commit_choice("s1", "v/mid")
        restarted = LiveRouter(self.db, self.profiles)
        self.assertEqual(restarted.plan(chat("merhaba"), session_id="s1")[0], "v/mid")

    def test_session_only_escalates_never_downgrades(self):
        self.router.commit_choice("s1", "v/free-text")
        self.assertEqual(self.router.plan(chat("mimari tasarım"), session_id="s1")[0], "v/flagship")
        self.router.commit_choice("s1", "v/flagship")
        self.assertEqual(self.router.plan(chat("teşekkürler"), session_id="s1")[0], "v/flagship")

    def test_sticky_model_without_vision_is_replaced_for_image_turns(self):
        self.router.commit_choice("s1", "v/mid")
        self.assertTrue(self.profiles[self.router.plan(chat("bak", image=True), session_id="s1")[0]].supports_vision)

    def test_rate_limited_model_cools_down_then_recovers(self):
        self.router.record_upstream("v/free-text", status=429, latency_ms=50, now=1000.0)
        self.assertNotEqual(self.router.plan(chat("merhaba"), now=1001.0)[0], "v/free-text")
        self.assertEqual(self.router.plan(chat("merhaba"), now=1000.0 + 301)[0], "v/free-text")

    def test_client_errors_do_not_trigger_cooldown(self):
        self.router.record_upstream("v/free-text", status=400, latency_ms=5, now=1000.0)
        self.assertEqual(self.router.plan(chat("merhaba"), now=1001.0)[0], "v/free-text")

    def test_prepare_payload_swaps_model_and_clamps_effort(self):
        out = self.router.prepare_payload(chat("x", reasoning_effort="medium", temperature=0.3), "v/free-text")
        self.assertEqual(out["model"], "v/free-text")
        self.assertEqual(out["reasoning_effort"], "high")
        self.assertEqual(out["temperature"], 0.3)
        out = self.router.prepare_payload(chat("x", reasoning_effort="xhigh"), "v/flagship")
        self.assertEqual(out["reasoning_effort"], "max")
        no_meta = self.router.prepare_payload(chat("x", reasoning_effort="xhigh"), "v/no-meta")
        self.assertEqual(no_meta["reasoning_effort"], "xhigh")  # unknown model: leave caller value untouched

    def test_explicit_model_requests(self):
        self.assertEqual(self.router.plan(chat("x", model="v/apex")), ["v/apex"])
        self.assertEqual(self.router.plan(chat("x", model="v/no-meta")), ["v/no-meta"])
        with self.assertRaises(KeyError):
            self.router.plan(chat("x", model="v/unknown"))

    def test_within_tier_higher_benchmark_beats_lower_price(self):
        from dataclasses import replace
        profiles = dict(self.profiles)
        profiles["v/cheap-vision"] = replace(profiles["v/cheap-vision"], intelligence_index=40.0)
        profiles["v/free-text"] = replace(profiles["v/free-text"], intelligence_index=20.0)
        router = LiveRouter(self.db, profiles)
        self.assertEqual(router.plan(chat("merhaba"))[0], "v/cheap-vision")

    def test_upstream_events_are_persisted_with_usage(self):
        self.router.record_upstream("v/mid", status=200, latency_ms=812, prompt_tokens=100, completion_tokens=20)
        stats = LiveRouter(self.db, self.profiles).model_stats("v/mid")
        self.assertEqual(stats["requests"], 1)
        self.assertEqual(stats["errors"], 0)
        self.assertEqual(stats["prompt_tokens"], 100)


class TestLiveRouterNousRegistry(unittest.TestCase):
    """Portal prices, curated pool and context-fit using the Nous-format registry builder."""

    def setUp(self):
        from src.router.model_registry import build_registry

        def model(mid, cost_in, ctx, vision=False):
            return {"id": mid, "context_length": ctx,
                    "architecture": {"input_modalities": ["text", "image"] if vision else ["text"]},
                    "supported_parameters": ["tools"],
                    "pricing": {"prompt": str(cost_in / 1e6), "completion": str(cost_in * 4 / 1e6)}}

        catalog = {"version": 1, "providers": {"nous": {"models": [
            {"id": "c/small"}, {"id": "c/big"}, {"id": "c/promo"}]}}}
        nous = {"data": [
            model("c/small", 0.1, 32000),
            model("c/small:free", 0, 32000),
            model("c/big", 0.2, 1000000),
            # list $5 but Portal bills $0.25 -> must be treated as tier 1, not tier 4
            dict(model("c/promo", 0.25, 200000), pricing={"prompt": "0.00000025", "completion": "0.000001",
                                                          "original": {"prompt": "0.000005", "completion": "0.00002"}}),
            model("x/uncurated", 0.01, 500000),
        ]}
        self.tmp = tempfile.TemporaryDirectory()
        self.profiles = build_registry(catalog, nous, None, fetched_at="t")
        self.router = LiveRouter(os.path.join(self.tmp.name, "r.db"), self.profiles)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tier_uses_billed_portal_price(self):
        self.assertEqual(price_tier(self.profiles["c/promo"]), 1)

    def test_uncurated_models_are_never_auto_selected_but_explicitly_allowed(self):
        self.assertNotIn("x/uncurated", self.router.plan(chat("merhaba")))
        self.assertEqual(self.router.plan(chat("x", model="x/uncurated")), ["x/uncurated"])

    def test_free_profile_uses_portal_zero_price_variants(self):
        self.assertEqual(self.router.plan(chat("x", model="oracle/free")), ["c/small:free"])

    def test_requests_that_do_not_fit_skip_small_context_models(self):
        small_request = self.router.plan(chat("merhaba"))
        self.assertIn("c/small", small_request)
        huge = chat("a" * 200000)  # ~67K tokens by the conservative estimate: too big for 32K windows
        plan = self.router.plan(huge)
        self.assertNotIn("c/small", plan)
        self.assertNotIn("c/small:free", plan)
        self.assertIn("c/big", plan)

    def test_image_payload_bytes_do_not_inflate_token_estimate(self):
        payload = chat("bak", image=True)
        payload["messages"][0]["content"][1]["image_url"]["url"] = "data:image/png;base64," + "A" * 400000
        from src.router.live_router import estimate_tokens
        self.assertLess(estimate_tokens(payload), 10000)  # would be ~133K if base64 were counted

    def test_virtual_context_length_is_largest_window_in_profile_pool(self):
        self.assertEqual(self.router.virtual_context_length("oracle/auto"), 1000000)
        self.assertEqual(self.router.virtual_context_length("oracle/free"), 32000)


if __name__ == "__main__":
    unittest.main()
