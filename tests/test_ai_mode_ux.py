"""RED: SOTA UX layer — AI Mode routing, command bar, side panel, speed prefs.

2026 browser-UX research (Chrome 156, Firefox, Brave, Edge, Safari, Vivaldi,
Dia, Comet) distilled into four tracks the product must ship:

1. **AI Mode integration** — Chromium base means Google AI Mode
   (``udm=50``) works natively; the NTP must offer a Web / AI Mode choice
   and the omnibox keyword ``ai`` must route straight to AI Mode.
2. **Command bar** — Arc-style palette (Alt+K) for tabs + search.
3. **Side panel** — open-tab overview + "sentez" (free, search-based).
4. **Speed layer** — vertical tabs (``vertical_tabs.enabled`` pref) and
   memory saver (``performance_tuning.memory_saver_mode.state`` pref),
   both verified real pref names in the Chromium 156 binary.
"""
import json
import os
import tempfile
import unittest

from src.brand.render import (
    extension_manifest,
    performance_preferences,
    render_ntp,
    search_url,
    write_extension,
)


class TestSearchRouting(unittest.TestCase):
    def test_web_search_is_plain_google(self):
        self.assertEqual(
            search_url("pergel test", "web"),
            "https://www.google.com/search?q=pergel+test")

    def test_ai_mode_search_uses_udm50(self):
        # Fortinet/GitHub-verified: AI Mode = google.com/search?udm=50
        url = search_url("pergel test", "ai")
        self.assertIn("udm=50", url)
        self.assertIn("q=pergel+test", url)

    def test_urlencodes_turkish(self):
        self.assertNotIn("ş", search_url("ağaç şifre", "ai"))


class TestNtpModeToggle(unittest.TestCase):
    def test_ntp_offers_web_and_ai_mode_buttons(self):
        html = render_ntp()
        self.assertIn("AI Mode", html)               # en default label
        self.assertIn("AI Modu", render_ntp("tr"))   # Turkish variant keeps it
        self.assertIn("Web", html)
        # zero-script mode select: two submit buttons carrying the udm value
        self.assertIn('name="udm"', html)
        self.assertIn('value="50"', html)   # AI Mode
        self.assertIn('value="14"', html)   # clean web-only

    def test_ntp_stays_scriptless_and_minimal(self):
        html = render_ntp()
        self.assertNotIn("<script", html)
        self.assertNotIn('src="http', html)
        self.assertLess(len(html), 16_000)


class TestExtensionManifest(unittest.TestCase):
    def setUp(self):
        self.m = extension_manifest()

    def test_omnibox_keyword_is_ai(self):
        self.assertEqual(self.m["omnibox"]["keyword"], "ai")

    def test_background_worker_registered(self):
        self.assertEqual(self.m["background"]["service_worker"], "background.js")

    def test_side_panel_registered(self):
        self.assertEqual(self.m["side_panel"]["default_path"], "panel.html")

    def test_command_bar_shortcut_alt_k(self):
        cmd = self.m["commands"]["pergel-command-bar"]
        self.assertEqual(cmd["suggested_key"]["default"], "Alt+K")

    def test_permissions_cover_tabs_and_side_panel(self):
        self.assertIn("tabs", self.m["permissions"])
        self.assertIn("sidePanel", self.m["permissions"])

    def test_newtab_override_survives(self):
        self.assertEqual(self.m["chrome_url_overrides"]["newtab"], "pergel_ntp.html")


class TestExtensionFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        write_extension(self.tmp)

    def _read(self, name):
        with open(os.path.join(self.tmp, name)) as f:
            return f.read()

    def test_all_surfaces_written(self):
        for name in ("manifest.json", "pergel_ntp.html", "background.js",
                     "commandbar.html", "panel.html"):
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, name)),
                            name + " missing")

    def test_background_routes_ai_mode(self):
        bg = self._read("background.js")
        self.assertIn("chrome.omnibox.onInputEntered", bg)
        self.assertIn("udm=50", bg)
        self.assertIn("chrome.commands.onCommand", bg)
        self.assertIn("chrome.sidePanel.setPanelBehavior", bg)

    def test_command_bar_lists_tabs_and_search_modes(self):
        cb = self._read("commandbar.html")
        self.assertIn("chrome.tabs.query", cb)
        self.assertIn("AI Modu", cb)

    def test_side_panel_sentez_uses_tab_titles(self):
        panel = self._read("panel.html")
        self.assertIn("chrome.tabs.query", panel)
        self.assertIn("sentez", panel.lower())


class TestRenderingPerformance(unittest.TestCase):
    """The visible window must composite on the GPU; --disable-gpu is a
    headless-CI crutch that must never reach a real desktop session."""

    def test_headless_keeps_gpu_disabled_for_ci(self):
        from src.browser_engine.cdp_adblock_driver import browser_base_args
        self.assertIn("--disable-gpu", browser_base_args(headless=True))

    def test_visible_window_enables_gpu(self):
        from src.browser_engine.cdp_adblock_driver import browser_base_args
        self.assertNotIn("--disable-gpu", browser_base_args(headless=False))

    def test_visible_session_command_has_no_gpu_flag(self):
        from src.browser_engine.adblock_session import compile_adblock
        from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
        sess = AdblockBrowserSession(compile_adblock(["||ads.example.com^"]),
                                     headless=False)
        self.assertNotIn("--disable-gpu", sess._build_command())


class TestPerformancePrefs(unittest.TestCase):
    def test_prepare_profile_enables_vertical_tabs_and_memory_saver(self):
        from src.brand import pergel_app
        tmp = tempfile.mkdtemp()
        pergel_app.prepare_profile(tmp, shield_port=41999)
        with open(os.path.join(tmp, "Default", "Preferences")) as f:
            prefs = json.load(f)
        self.assertTrue(prefs["vertical_tabs"]["enabled"])
        self.assertEqual(
            prefs["performance_tuning"]["memory_saver_mode"]["state"], 1)


if __name__ == "__main__":
    unittest.main()
