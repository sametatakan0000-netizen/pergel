"""TDD: load MV3 extensions from a manifest directory into an ExtensionHost.

Before this, there was no way to construct an ExtensionHost in production —
ExtensionHost() was only ever built inside tests. This loader turns a
directory of MV3 extension manifests into a host the adblock driver factory
can consume.
"""
import json
import os
import tempfile
import unittest

from src.browser_engine.extension_host import load_extensions_dir


class LoadExtensionsDirTests(unittest.TestCase):
    def _write_manifest(self, root, name, rules):
        d = os.path.join(root, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "manifest.json"), "w") as f:
            json.dump({
                "manifest_version": 3, "name": name, "version": "1.0",
                "declarative_net_request": {"rule_resources": [{
                    "id": "ruleset_1", "enabled": True, "path": "rules.json"}]},
            }, f)
        with open(os.path.join(d, "rules.json"), "w") as f:
            json.dump(rules, f)

    def test_loads_manifest_rules_into_host(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "adblock-ext", [
                {"id": 1, "priority": 1, "action": {"type": "block"},
                 "condition": {"urlFilter": "||ads.example.com^",
                               "resourceTypes": ["script"]}},
            ])
            host = load_extensions_dir(root)
            self.assertEqual(host.list_extensions(), ["adblock-ext"])
            d = host.check("https://ads.example.com/banner.js", "script")
            self.assertEqual(d.action, "block")

    def test_empty_or_missing_dir_yields_empty_host(self):
        with tempfile.TemporaryDirectory() as root:
            host = load_extensions_dir(root)
            self.assertEqual(host.list_extensions(), [])
        host = load_extensions_dir("/nonexistent/path")
        self.assertEqual(host.list_extensions(), [])


if __name__ == "__main__":
    unittest.main()
