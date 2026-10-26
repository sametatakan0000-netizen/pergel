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
