"""TDD: production server wires the MV3 extension host into the adblock driver.

When ``ORACLE_EXTENSIONS_DIR`` points at a manifest dir, the server's
``_resolve_driver`` must hand an ExtensionHost to ``make_adblock_driver`` so
extension DNR rules are enforced in the live CDP path.
"""
import os
import json
import tempfile
import unittest

from src.api.server import _maybe_extension_host
from src.browser_engine.adblock_session import load_adblock_bundle


class MaybeExtensionHostTests(unittest.TestCase):
    def test_unset_env_returns_none(self):
        os.environ.pop("ORACLE_EXTENSIONS_DIR", None)
        self.assertIsNone(_maybe_extension_host())

    def test_empty_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as root:
            os.environ["ORACLE_EXTENSIONS_DIR"] = root
            try:
                self.assertIsNone(_maybe_extension_host())
            finally:
                os.environ.pop("ORACLE_EXTENSIONS_DIR", None)

    def test_manifest_dir_returns_loaded_host(self):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "ext"); os.makedirs(d)
            with open(os.path.join(d, "manifest.json"), "w") as f:
                json.dump({"manifest_version": 3, "name": "ext", "version": "1.0",
                           "declarative_net_request": {"rule_resources": [
                               {"id": "r", "enabled": True, "path": "rules.json"}]}}, f)
            with open(os.path.join(d, "rules.json"), "w") as f:
                json.dump([{"id": 1, "priority": 1, "action": {"type": "block"},
                            "condition": {"urlFilter": "||ads.example.com^",
                                          "resourceTypes": ["script"]}}], f)
            os.environ["ORACLE_EXTENSIONS_DIR"] = root
            try:
                host = _maybe_extension_host()
            finally:
                os.environ.pop("ORACLE_EXTENSIONS_DIR", None)
            self.assertIsNotNone(host)
            self.assertEqual(host.list_extensions(), ["ext"])


if __name__ == "__main__":
    unittest.main()



class ResolveDriverExtensionsOnlyTests(unittest.TestCase):
    """Extensions must be enforced even when no filter lists are configured."""

    def test_extensions_without_lists_still_use_cdp_driver(self):
        from src.api import server as srv
        seen = {}

        def fake_make(bundle, extensions=None):
            seen["ext"] = extensions
            return "CDP_DRIVER"

        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "ext"); os.makedirs(d)
            with open(os.path.join(d, "manifest.json"), "w") as f:
                json.dump({"manifest_version": 3, "name": "ext", "version": "1",
                           "declarative_net_request": {"rule_resources": [
                               {"id": "r", "enabled": True, "path": "r.json"}]}}, f)
            with open(os.path.join(d, "r.json"), "w") as f:
                json.dump([], f)
            empty_lists = os.path.join(root, "no_lists"); os.makedirs(empty_lists)
            old = (srv.make_adblock_driver, srv.DEFAULT_FILTER_LISTS_DIR,
                   os.environ.get("ORACLE_EXTENSIONS_DIR"),
                   os.environ.get("ORACLE_ADBLOCK_LISTS"))
            srv.make_adblock_driver = fake_make
            srv.DEFAULT_FILTER_LISTS_DIR = empty_lists  # no filter lists at all
            os.environ["ORACLE_EXTENSIONS_DIR"] = root
            os.environ.pop("ORACLE_ADBLOCK_LISTS", None)
            try:
                drv = srv._resolve_driver(None)
            finally:
                srv.make_adblock_driver = old[0]
                srv.DEFAULT_FILTER_LISTS_DIR = old[1]
                for k, v in (("ORACLE_EXTENSIONS_DIR", old[2]),
                             ("ORACLE_ADBLOCK_LISTS", old[3])):
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v
        self.assertIsNotNone(drv)  # wrapped by _with_fallback, not engine_driver
        self.assertIsNot(drv, srv.engine_driver)
        self.assertIsNotNone(seen.get("ext"), "extension host must reach the CDP driver")


if __name__ == "__main__":
    unittest.main()
