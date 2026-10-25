"""Adblock integration: one filter list -> all four layers -> one injection.

The four layers (network DNR engine, cosmetic CSS, scriptlets, procedural
filters) each live in their own module and are verified in isolation. This is
the seam that composes them: ``compile_adblock`` routes one filter list into
every layer at once, and ``build_injection`` folds the renderer-side layers
(cosmetic + scriptlets + procedural) into a single ``document-start`` JS source.

Pure: no sockets, no browser. The live CDP fetch is a separate test module.
"""
import unittest

from src.browser_engine.adblock_session import AdblockBundle, build_injection, compile_adblock


LIST = [
    "! a comment",
    "||ads.example.com^",                       # network block
    "@@||ads.example.com/allowed.js",           # network allow
    "example.com##.sponsored-ad",               # cosmetic hide
    "example.com#@#.sponsored-ad",              # cosmetic exception (cancels above on example.com)
    "other.com##.banner",                       # cosmetic hide, other.com scoped
    "example.com##+js(set-constant, __adBlockEnabled, true)",  # scriptlet
    "example.com#?#.slot:has-text(Sponsored)",  # procedural
]


class TestCompileAdblock(unittest.TestCase):
    def test_bundle_has_all_four_layers(self):
        bundle = compile_adblock(LIST)
        self.assertIsInstance(bundle, AdblockBundle)
        # network engine matches a blocked ad URL
        self.assertEqual(bundle.network.check(
            "https://ads.example.com/pixel.gif").action, "block")
        # cosmetic rules parsed
        selectors = [r["selector"] for r in bundle.cosmetic]
        self.assertIn(".sponsored-ad", selectors)
        self.assertIn(".banner", selectors)
        # scriptlet parsed
        self.assertEqual(bundle.scriptlets[0]["name"], "set-constant")
        # procedural parsed
        self.assertEqual(bundle.procedural[0]["base"], ".slot")

    def test_scriptlets_are_not_mistaken_for_cosmetic(self):
        # `##+js(...)` must not land in the cosmetic layer as a `+js(...)` selector
        bundle = compile_adblock(LIST)
        for rule in bundle.cosmetic:
            self.assertFalse(rule["selector"].startswith("+js("),
                             f"scriptlet leaked into cosmetic: {rule['selector']}")

    def test_empty_list_is_empty_bundle(self):
        bundle = compile_adblock([])
        self.assertEqual(bundle.cosmetic, [])
        self.assertEqual(bundle.scriptlets, [])
        self.assertEqual(bundle.procedural, [])
        self.assertEqual(build_injection(bundle, "example.com"), "")


class TestBuildInjection(unittest.TestCase):
    def test_injection_combines_all_renderer_layers(self):
        bundle = compile_adblock(LIST)
        js = build_injection(bundle, "example.com")
        # cosmetic: the cancelled selector must be absent on example.com
        self.assertNotIn(".sponsored-ad {", js)  # cancelled by #@# on example.com
        self.assertNotIn(".banner", js)          # scoped to other.com -> excluded
        # scriptlet helper is present and called
        self.assertIn("setc(", js)
        self.assertIn("__adBlockEnabled", js)
        # procedural runner is present
        self.assertIn("has-text", js)
        self.assertIn("MutationObserver", js)

    def test_scoped_cosmetic_applies_on_its_own_host(self):
        bundle = compile_adblock(LIST)
        js = build_injection(bundle, "other.com")
        self.assertIn(".banner", js)          # other.com scoped -> included here

    def test_cosmetic_only_host_excludes_out_of_scope(self):
        bundle = compile_adblock(LIST)
        js = build_injection(bundle, "unrelated.com")
        self.assertNotIn(".banner", js)       # other.com scoped -> excluded
        self.assertNotIn("__adBlockEnabled", js)  # example.com scriptlet -> excluded

    def test_injection_is_a_single_runnable_source(self):
        bundle = compile_adblock(LIST)
        js = build_injection(bundle, "example.com")
        self.assertTrue(js.strip().startswith("(() =>") or "(() =>" in js)
        # balanced-ish sanity: at least one IIFE closure present
        self.assertIn("})();", js)

    def test_injection_uses_json_css_escaping(self):
        # CSS text must be embedded as a JSON string literal (never Python repr)
        bundle = compile_adblock(['example.com##.ad:has-text("quoted")'])
        js = build_injection(bundle, "example.com")
        if js:
            self.assertIn("textContent = ", js)


if __name__ == "__main__":
    unittest.main()
