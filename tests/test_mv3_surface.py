"""B series: MV3 extension surface — let third-party extensions run on us.

The platform-agnostic contract (no vendor lock-in): parse an MV3 manifest,
bridge its ``declarativeNetRequest`` rules onto our existing rule engine, and
inject its content scripts at the right document phase. This is the surface
that lets Bitwarden/Grammarly/any MV3 extension run unchanged.

RED first (module absent), then GREEN.
"""
import unittest

from src.browser_engine.mv3_surface import (
    MV3Manifest,
    content_script_sources,
    load_manifest,
    manifest_dnr_rules,
    build_extension_engine,
)

MANIFEST = {
    "manifest_version": 3,
    "name": "Sample Blocker",
    "version": "1.0",
    "permissions": ["declarativeNetRequest"],
    "host_permissions": ["<all_urls>"],
    "declarativeNetRequest": {
        "rule_resources": [{
            "id": "ruleset_1",
            "enabled": True,
            "path": "rules.json",
        }]
    },
    "content_scripts": [{
        "matches": ["<all_urls>"],
        "js": ["content.js"],
        "css": ["hide.css"],
        "run_at": "document_start",
    }],
}


class ManifestParseTests(unittest.TestCase):
    def test_load_manifest_reads_identity(self):
        m = load_manifest(MANIFEST)
        self.assertIsInstance(m, MV3Manifest)
        self.assertEqual(m.name, "Sample Blocker")
        self.assertEqual(m.version, "1.0")
        self.assertEqual(m.manifest_version, 3)

    def test_manifest_requires_mv3(self):
        with self.assertRaises(ValueError):
            load_manifest({"manifest_version": 2, "name": "old"})

    def test_declares_dnr_permission(self):
        m = load_manifest(MANIFEST)
        self.assertTrue(m.uses_dnr)

    def test_content_script_sources_lists_js_at_document_start(self):
        m = load_manifest(MANIFEST)
        css, js, run_at = content_script_sources(m)[0]
        self.assertEqual(js, ["content.js"])
        self.assertEqual(css, ["hide.css"])
        self.assertEqual(run_at, "document_start")


class DnrBridgeTests(unittest.TestCase):
    def test_manifest_dnr_rules_translates_to_engine_rules(self):
        ext_rules = [{
            "id": 1,
            "priority": 1,
            "action": {"type": "block"},
            "condition": {"urlFilter": "||ads.example^", "resourceTypes": ["main_frame"]},
        }]
        rules = manifest_dnr_rules(ext_rules)
        self.assertEqual(rules[0]["action"]["type"], "block")
        self.assertIn("ads.example", rules[0]["condition"]["urlFilter"])

    def test_build_extension_engine_blocks_extension_rule(self):
        ext_rules = [{
            "id": 1,
            "priority": 1,
            "action": {"type": "block"},
            "condition": {"urlFilter": "||ads.example^", "resourceTypes": ["main_frame"]},
        }]
        engine = build_extension_engine(ext_rules)
        decision = engine.check("https://ads.example/tracker", "main_frame")
        self.assertEqual(decision.action, "block")

    def test_build_extension_engine_allows_other(self):
        ext_rules = [{
            "id": 1,
            "priority": 1,
            "action": {"type": "block"},
            "condition": {"urlFilter": "||ads.example^", "resourceTypes": ["main_frame"]},
        }]
        engine = build_extension_engine(ext_rules)
        self.assertEqual(engine.check("https://work.example/", "main_frame").action, "allow")


if __name__ == "__main__":
    unittest.main()
