import os
import tempfile
import unittest
from dataclasses import replace

from src.router.live_router import LiveRouter, price_tier
from src.router.model_registry import build_profiles
from src.router.moa_plan import (ABSOLUTE_TURN_CAP_USD, MAX_MEMBERS, budget_ratio, plan_moa,
                                 turn_cost)

CATALOG = {"version": 1, "providers": {"nous": {"models": [
    {"id": "v/tiny-a"}, {"id": "v/tiny-b"}, {"id": "v/tiny-c"}, {"id": "v/tiny-d"},
    {"id": "v/mid-a"}, {"id": "v/mid-b"}, {"id": "v/flagship"}, {"id": "v/weak"},
]}}}


def meta(cost_in, cost_out, ctx=200000):
    return {
        "tool_call": True, "reasoning": False, "reasoning_options": [],
        "modalities": {"input": ["text"]}, "limit": {"context": ctx},
        "cost": {"input": cost_in, "output": cost_out},
    }


MODELS_DEV = {"openrouter": {"models": {
    "v/tiny-a": meta(0.10, 0.50),
    "v/tiny-b": meta(0.08, 0.40),
    "v/tiny-c": meta(0.00, 0.00),
    "v/tiny-d": meta(0.25, 1.00),
    "v/mid-a": meta(1.00, 5.00),
    "v/mid-b": meta(1.50, 6.00),
    "v/flagship": meta(2.00, 10.00),
    "v/weak": meta(0.05, 0.20),
}}}


def chat(text, model="oracle/auto"):
    return {"model": model, "messages": [{"role": "user", "content": text}]}


# ~30K prompt tokens: a realistic Hermes turn, so cost math is not degenerate.
BIG_TEXT = "x" * 90000


class TestMoaPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "router.db")
        profiles = build_profiles(CATALOG, MODELS_DEV, fetched_at="t")
        # Equal-quality cheap band + a premium tier + one clearly weak model.
        for mid in ("v/tiny-a", "v/tiny-b", "v/tiny-d"):
            profiles[mid] = replace(profiles[mid], intelligence_index=44.0)
        profiles["v/tiny-c"] = replace(profiles["v/tiny-c"], intelligence_index=43.0)
        profiles["v/mid-a"] = replace(profiles["v/mid-a"], intelligence_index=56.0)
        profiles["v/mid-b"] = replace(profiles["v/mid-b"], intelligence_index=53.0)
        profiles["v/flagship"] = replace(profiles["v/flagship"], intelligence_index=57.6)
        profiles["v/weak"] = replace(profiles["v/weak"], intelligence_index=12.0)
        self.profiles = profiles
        self.router = LiveRouter(self.db, profiles, explore_epsilon=0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_easy_turn_stays_single_model(self):
        plan = plan_moa(self.router, chat("merhaba"), now=1000.0)
        self.assertFalse(plan["moa"]["enabled"])
        self.assertEqual(plan["moa"]["members"], [])
        self.assertEqual(plan["tier"], 1)

    def test_hard_turn_picks_amiral_and_tolerance_band_members(self):
        plan = plan_moa(self.router, chat("mimari refactor planı: " + BIG_TEXT), now=1000.0,
                        force=True)
        self.assertEqual(plan["amiral"], "v/mid-b")  # cheapest inside the 5-point band
        members = plan["moa"]["members"]
        self.assertTrue(plan["moa"]["enabled"])
        self.assertLessEqual(len(members), MAX_MEMBERS)
        self.assertNotIn("v/mid-b", members)
        self.assertNotIn("v/weak", members)  # 45 points below the band leader
        for mid in members:
            self.assertLessEqual(price_tier(self.profiles[mid]), plan["tier"])

    def test_band_members_are_ordered_by_quality_per_dollar(self):
        # Three near-equal cheap candidates: the cheapest leads as Amiral, the rest are
        # members ranked by quality per dollar.
        profiles = dict(self.profiles)
        profiles["v/tiny-d"] = replace(profiles["v/tiny-d"], list_cost_in=0.06,
                                       list_cost_out=0.30)
        for mid, quality in (("v/tiny-a", 42.0), ("v/tiny-b", 40.0), ("v/tiny-d", 41.0)):
            profiles[mid] = replace(profiles[mid], intelligence_index=quality)
        profiles["v/tiny-c"] = replace(profiles["v/tiny-c"], intelligence_index=20.0)
        router = LiveRouter(os.path.join(self.tmp.name, "band.db"), profiles, explore_epsilon=0)
        plan = plan_moa(router, chat("merhaba"), now=1000.0, force=True)
        self.assertEqual(plan["amiral"], "v/tiny-d")  # cheapest inside the band
        members = plan["moa"]["members"]
        self.assertGreaterEqual(len(members), 2)
        ratio = lambda p: p.intelligence_index / (p.billed_cost_in + p.billed_cost_out)
        costs = [ratio(profiles[mid]) for mid in members]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_cap_is_a_multiple_of_the_amiral_cost_not_a_constant(self):
        plan = plan_moa(self.router, chat("mimari analiz " + BIG_TEXT), now=1000.0, force=True)
        single = plan["moa"]["amiral_cost_usd"]
        self.assertAlmostEqual(plan["moa"]["cap_usd"] / single, plan["moa"]["ratio"], places=2)
        self.assertLessEqual(plan["moa"]["cap_usd"], ABSOLUTE_TURN_CAP_USD)
        self.assertGreaterEqual(plan["moa"]["ratio"], 1.0)

    def test_budget_ratio_shrinks_with_spend_and_grows_with_difficulty(self):
        calm = budget_ratio(3, 0, 1.0, spent_today_usd=0.0)
        hard = budget_ratio(3, 2, 1.0, spent_today_usd=0.0)
        unsure = budget_ratio(3, 0, 0.0, spent_today_usd=0.0)
        overspent = budget_ratio(3, 0, 1.0, spent_today_usd=20.0)
        self.assertGreater(hard, calm)
        self.assertGreater(unsure, calm)
        self.assertLess(overspent, calm)
        self.assertGreaterEqual(overspent, 1.0)  # never below the Amiral itself

    def test_spend_pressure_removes_members(self):
        rich = plan_moa(self.router, chat("mimari analiz " + BIG_TEXT), now=1000.0, force=True)
        lean = plan_moa(self.router, chat("mimari analiz " + BIG_TEXT), now=1000.0,
                        force=True, spent_today_usd=20.0)
        self.assertLessEqual(len(lean["moa"]["members"]), len(rich["moa"]["members"]))
        self.assertLessEqual(lean["moa"]["cap_usd"], rich["moa"]["cap_usd"])

    def test_member_cost_uses_prompt_size(self):
        small = turn_cost(self.profiles["v/tiny-a"], 1000)
        big = turn_cost(self.profiles["v/tiny-a"], 100000)
        self.assertGreater(big, small)


if __name__ == "__main__":
    unittest.main()
