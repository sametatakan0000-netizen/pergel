import importlib
import os
import unittest
from unittest import mock


class MoaDefaultOffTests(unittest.TestCase):
    """MoA stays opt-in: every member re-reads the full (100K+) context, so N members multiply
    the dominant cost, and the policy DB holds no evidence that MoA ever beat a single model."""

    def _reload(self, value):
        env = {k: v for k, v in os.environ.items() if k != "ORACLE_MOA"}
        if value is not None:
            env["ORACLE_MOA"] = value
        with mock.patch.dict(os.environ, env, clear=True):
            import src.api.server as server
            return importlib.reload(server).MOA_ENABLED

    def tearDown(self):
        import src.api.server as server
        importlib.reload(server)

    def test_unset_means_off(self):
        self.assertFalse(self._reload(None))

    def test_explicit_zero_is_off(self):
        self.assertFalse(self._reload("0"))

    def test_explicit_one_turns_it_on(self):
        self.assertTrue(self._reload("1"))
