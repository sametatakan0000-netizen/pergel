import unittest

from src.router.context_governor import advised_context_length, effective_window


class ContextGovernorTests(unittest.TestCase):
    def test_effective_window_is_capped(self):
        self.assertEqual(effective_window(1_000_000, cap=200_000), 200_000)

    def test_small_models_keep_their_real_window(self):
        self.assertEqual(effective_window(32_000, cap=200_000), 32_000)

    def test_virtual_profile_reports_cap_not_pool_max(self):
        self.assertEqual(advised_context_length([1_000_000, 2_000_000], cap=200_000), 200_000)

    def test_small_pool_reports_its_real_max(self):
        self.assertEqual(advised_context_length([32_000, 8_000], cap=200_000), 32_000)

    def test_none_when_pool_empty(self):
        self.assertIsNone(advised_context_length([], cap=200_000))
