import unittest
from src.bench.stats import bootstrap_ci, mad, ratio_claim, summarize


class StatsTests(unittest.TestCase):
    def test_mad(self):
        self.assertEqual(mad([1, 2, 3, 4, 100]), 1)

    def test_bootstrap_is_deterministic_and_brackets_median(self):
        xs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        a, b = bootstrap_ci(xs), bootstrap_ci(xs)
        self.assertEqual(a, b)
        self.assertLessEqual(a[0], 14.5)
        self.assertGreaterEqual(a[1], 14.5)

    def test_separated_samples_are_claimable_with_ratio(self):
        base = [100 + i * 0.1 for i in range(12)]
        cand = [10 + i * 0.1 for i in range(12)]
        r = ratio_claim(base, cand)
        self.assertTrue(r["claimable"])
        self.assertGreater(r["ratio"], 9)

    def test_overlapping_samples_not_claimable(self):
        xs = [10 + i * 0.1 for i in range(12)]
        r = ratio_claim(xs, list(xs))
        self.assertFalse(r["claimable"])
        self.assertEqual(r["reason"], "ci overlap")

    def test_too_few_samples_not_claimable(self):
        r = ratio_claim([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        self.assertFalse(r["claimable"])
        self.assertTrue(r["reason"].startswith("n<"))

    def test_summarize_shape(self):
        s = summarize([1, 2, 3, 4, 5, 6])
        self.assertEqual(set(s), {"n", "median", "mad", "ci95", "min", "max"})
