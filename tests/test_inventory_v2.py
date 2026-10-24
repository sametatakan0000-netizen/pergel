import unittest

from src.router.live_router import prune_dominated, unproven_premium
from src.router.model_registry import VerifiedProfile


def prof(mid, cin, cout, aa=None, ctx=200_000):
    return VerifiedProfile(model_id=mid, status="verified_metadata", context_window=ctx,
                           portal_cost_in=cin, portal_cost_out=cout,
                           list_cost_in=cin, list_cost_out=cout, intelligence_index=aa)


class UnprovenPremiumTests(unittest.TestCase):
    def setUp(self):
        # tier-1 style pool: cheap proven models + one expensive model with NO published benchmark
        self.cheap = [prof("a/cheap1", 0.02, 1.0, 39.5), prof("a/cheap2", 0.1, 0.5, 43.4),
                      prof("a/cheap3", 0.12, 0.4, 41.8)]
        self.phantom = prof("x/ultraspeed", 4.35, 8.7, None)
        self.pool = self.cheap + [self.phantom]
        self.served = {p.model_id for p in self.pool}

    def test_rule_flags_expensive_without_benchmark(self):
        self.assertTrue(unproven_premium(self.phantom, self.pool))

    def test_rule_spares_models_with_a_benchmark(self):
        pricey_but_measured = prof("a/measured", 5.0, 25.0, 41.8)
        self.assertFalse(unproven_premium(pricey_but_measured, self.pool + [pricey_but_measured]))

    def test_rule_spares_cheap_models_without_a_benchmark(self):
        cheap_unknown = prof("a/cheapunknown", 0.05, 0.2, None)
        self.assertFalse(unproven_premium(cheap_unknown, self.pool + [cheap_unknown]))

    def test_rule_needs_enough_measured_peers_to_define_a_median(self):
        lone = prof("x/lone", 9.0, 9.0, None)
        self.assertFalse(unproven_premium(lone, [lone]))

    def test_pool_with_no_benchmarks_at_all_demotes_nothing(self):
        # absence of data across the whole pool says nothing about one model
        pool = [prof(f"v/m{i}", c, c * 4, None) for i, c in enumerate((0.1, 0.5, 2.0, 10.0))]
        self.assertFalse(any(unproven_premium(p, pool) for p in pool))

    def test_prune_moves_phantom_to_dominated(self):
        primary, dominated = prune_dominated(self.pool, set(), self.served)
        self.assertIn("x/ultraspeed", {p.model_id for p in dominated})
        self.assertNotIn("x/ultraspeed", {p.model_id for p in primary})
        self.assertEqual({"a/cheap1", "a/cheap2", "a/cheap3"} - {p.model_id for p in primary}, set())


if __name__ == "__main__":
    unittest.main()
