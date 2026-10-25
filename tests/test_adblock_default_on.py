"""Adblock enforcement is default-on in the product fetch path.

Contract:
- No env / no explicit paths  -> enforced driver if the default filter lists exist.
- ORACLE_ADBLOCK_LISTS=off    -> plain engine_driver (explicit opt-out).
- Default lists missing       -> plain engine_driver (never break the product).
- Enforced driver raises      -> fall back to engine_driver for that fetch (fail-open
                                 on availability, logged; policy blocks never escalate).
"""
import os
import tempfile
import unittest
from unittest import mock

from src.api import server as srv
from src.browser_engine.engine_drivers import engine_driver


class TestDefaultOn(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORACLE_ADBLOCK_LISTS", None)
        self.tmp = tempfile.mkdtemp()
        self.lists = os.path.join(self.tmp, "filterlists")
        os.makedirs(self.lists)

    def tearDown(self):
        self._env.stop()

    def _write_list(self, name):
        p = os.path.join(self.lists, name)
        with open(p, "w") as f:
            f.write("||ads.example.test^\n")
        return p

    def test_default_on_uses_enforced_driver_when_lists_exist(self):
        self._write_list("easylist.txt")
        with mock.patch.object(srv, "DEFAULT_FILTER_LISTS_DIR", self.lists), \
             mock.patch.object(srv, "make_adblock_driver", return_value=lambda *a: "x") as mk:
            d = srv._resolve_driver(None)
        self.assertIsNot(d, engine_driver)
        self.assertTrue(mk.called)

    def test_explicit_off_env_disables(self):
        self._write_list("easylist.txt")
        os.environ["ORACLE_ADBLOCK_LISTS"] = "off"
        with mock.patch.object(srv, "DEFAULT_FILTER_LISTS_DIR", self.lists):
            self.assertIs(srv._resolve_driver(None), engine_driver)

    def test_missing_lists_falls_back_to_plain_driver(self):
        with mock.patch.object(srv, "DEFAULT_FILTER_LISTS_DIR", self.lists):
            self.assertIs(srv._resolve_driver(None), engine_driver)

    def test_env_paths_override_default_dir(self):
        p = self._write_list("custom.txt")
        os.environ["ORACLE_ADBLOCK_LISTS"] = p
        with mock.patch.object(srv, "make_adblock_driver", return_value=lambda *a: "x") as mk:
            d = srv._resolve_driver(None)
        self.assertIsNot(d, engine_driver)
        self.assertTrue(mk.called)

    def test_enforced_failure_falls_back_to_plain_driver(self):
        calls = []

        def broken(engine, url, session):
            calls.append(url)
            raise RuntimeError("chromium unavailable")

        def plain(engine, url, session):
            return "<p>plain</p>"

        with mock.patch.object(srv, "engine_driver", plain):
            wrapped = srv._with_fallback(broken)
            self.assertEqual(wrapped(None, "https://a.test/", "s"), "<p>plain</p>")
        self.assertEqual(calls, ["https://a.test/"])


if __name__ == "__main__":
    unittest.main()
