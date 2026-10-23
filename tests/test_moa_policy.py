import os
import random
import tempfile
import unittest

from src.router import moa_policy as mp
from src.router.moa_policy import MoaPolicy


class TestMoaPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.policy = MoaPolicy(os.path.join(self.tmp.name, "moa.db"), rng=random.Random(1))

    def tearDown(self):
        self.tmp.cleanup()

    def feed(self, mode, bad, n, bucket="t3:txt:m"):
        with self.policy._conn() as conn:
            conn.executemany("INSERT INTO moa_outcomes (bucket, mode, bad, signal, ts) VALUES (?,?,?,?,0)",
                             [(bucket, mode, bad, "user_retry" if bad else "continued")] * n)

    def test_cold_bucket_explores_at_configured_rate(self):
        self.assertEqual(self.policy.explore_rate("t3:txt:m"), mp.COLD_EXPLORE)

    def test_insufficient_samples_stay_cold(self):
        self.feed("moa", 0, mp.MIN_OBS - 1)
        self.feed("single", 1, mp.MIN_OBS)
        self.assertEqual(self.policy.explore_rate("t3:txt:m"), mp.COLD_EXPLORE)

    def test_moa_clearly_better_becomes_default_with_single_probe(self):
        self.feed("moa", 0, 20)
        self.feed("single", 1, 20)  # single bad rate 1.0 vs moa 0.0
        self.assertAlmostEqual(self.policy.explore_rate("t3:txt:m"), 1.0 - mp.DECIDED_SINGLE_PROBE)

    def test_moa_clearly_worse_is_mostly_closed(self):
        self.feed("moa", 1, 20)
        self.feed("single", 0, 20)
        self.assertAlmostEqual(self.policy.explore_rate("t3:txt:m"), mp.DECIDED_MOA_PROBE)

    def test_difference_inside_margin_is_undecided(self):
        self.feed("moa", 0, 40)
        self.feed("single", 0, 39)
        self.feed("single", 1, 1)  # single 1/40 = 0.025 < MARGIN
        self.assertEqual(self.policy.explore_rate("t3:txt:m"), mp.COLD_EXPLORE)

    def test_buckets_are_independent(self):
        self.feed("moa", 0, 20, bucket="t3:txt:m")
        self.feed("single", 1, 20, bucket="t3:txt:m")
        self.assertEqual(self.policy.explore_rate("t2:txt:s"), mp.COLD_EXPLORE)

    def test_choose_respects_rate_and_is_deterministic_for_seed(self):
        picks = [self.policy.choose("t3:txt:m") for _ in range(2000)]
        share = picks.count("moa") / len(picks)
        self.assertGreater(share, mp.COLD_EXPLORE - 0.03)
        self.assertLess(share, mp.COLD_EXPLORE + 0.03)

    def test_feedback_settles_to_the_arm_that_produced_the_answer(self):
        self.policy.remember("s1", "t3:txt:m", "moa", now=1.0)
        self.assertEqual(self.policy.settle("s1", "user_retry", now=2.0), "moa")
        self.assertEqual(self.policy.counts("t3:txt:m")["moa"], {"n": 1, "bad": 1})
        # pending entry is consumed: a second signal goes nowhere
        self.assertIsNone(self.policy.settle("s1", "continued", now=3.0))

    def test_neutral_signal_consumes_pending_without_recording(self):
        self.policy.remember("s2", "t3:txt:m", "single", now=1.0)
        self.assertIsNone(self.policy.settle("s2", None, now=2.0))
        self.assertEqual(self.policy.counts("t3:txt:m")["single"]["n"], 0)

    def test_positive_signal_counts_as_good(self):
        self.policy.remember("s3", "t3:txt:m", "single", now=1.0)
        self.policy.settle("s3", "continued", now=2.0)
        self.assertEqual(self.policy.counts("t3:txt:m")["single"], {"n": 1, "bad": 0})

    def test_no_session_no_record(self):
        self.assertIsNone(self.policy.settle(None, "user_retry"))


if __name__ == "__main__":
    unittest.main()
