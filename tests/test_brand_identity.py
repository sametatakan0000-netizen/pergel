"""RED: Vane brand identity — tokens and branded surface renderers.

The product must stop looking like "stock Chromium + filters" and carry its
own brand (decided name: **Vane**, direction: micro-level minimalist
optimize). Three surfaces carry the identity and must render from ONE token
source (no colour drift between surfaces):

* new-tab page   — the first thing every user sees,
* shield panel   — live blocked counter (the differentiating feature),
* desktop entry  — the double-click launcher users actually see in the menu.

Every rendered surface must expose the brand name, use the accent token, and
embed the monogram mark. The desktop entry must satisfy the freedesktop spec
(Type/Name/Exec/Icon/Categories) so GNOME indexes it.
"""
import unittest

from src.brand import tokens
from src.brand.render import (
    render_desktop_entry,
    render_ntp,
    render_shield_panel,
    theme_preferences,
)


class TestBrandTokens(unittest.TestCase):
    def test_brand_name_is_vane(self):
        self.assertEqual(tokens.NAME, "Vane")

    def test_tagline_is_minimalist_optimized(self):
        self.assertIn("minimal", tokens.TAGLINE.lower())

    def test_palette_is_dark_with_single_accent(self):
        # one accent colour, dark graphite base — "micro-level minimalist"
        self.assertTrue(tokens.ACCENT.startswith("#"))
        self.assertTrue(tokens.BG.startswith("#"))
        # base must be dark (premium graphite), not white
        r, g, b = tokens.rgb(tokens.BG)
        self.assertLess(max(r, g, b), 80, "background must stay dark graphite")

    def test_rgb_helper_parses_hex(self):
        self.assertEqual(tokens.rgb("#0A0B10"), (10, 11, 16))


class TestNewTabPage(unittest.TestCase):
    def test_ntp_carries_brand_name_and_monogram(self):
        html = render_ntp()
        self.assertIn("Vane", html)
        self.assertIn("monogram", html)

    def test_ntp_uses_the_accent_token(self):
        html = render_ntp()
        self.assertIn(tokens.ACCENT, html)

    def test_ntp_is_micro_minimalist(self):
        # no framework bloat: single inline document, no external requests
        html = render_ntp()
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertLess(len(html), 64_000)


class TestShieldPanel(unittest.TestCase):
    def test_panel_shows_live_block_counter(self):
        html = render_shield_panel(stats_port=41234)
        self.assertIn("blocked", html.lower())
        self.assertIn("41234", html)

    def test_panel_uses_brand_and_accent(self):
        html = render_shield_panel(stats_port=1)
        self.assertIn("Vane", html)
        self.assertIn(tokens.ACCENT, html)


class TestThemePreferences(unittest.TestCase):
    def test_theme_paints_frame_and_toolbar_with_brand_colors(self):
        prefs = theme_preferences()
        colors = prefs["theme"]["colors"]
        self.assertEqual(colors["frame"], list(tokens.rgb(tokens.BG)))
        self.assertEqual(colors["toolbar"], list(tokens.rgb(tokens.SURFACE)))
        self.assertEqual(colors["tab_text"], list(tokens.rgb(tokens.TEXT)))


class TestDesktopEntry(unittest.TestCase):
    def test_desktop_entry_satisfies_freedesktop_required_keys(self):
        text = render_desktop_entry()
        self.assertIn("[Desktop Entry]", text)
        self.assertIn("Type=Application", text)
        self.assertIn("Name=Vane", text)
        self.assertIn("Exec=vane %U", text)
        self.assertIn("Icon=vane", text)
        self.assertIn("Categories=Network;WebBrowser;", text)
        self.assertIn("Terminal=false", text)

    def test_desktop_entry_no_display_name_leak(self):
        # nothing Chromium-ish in the launcher the user sees
        text = render_desktop_entry()
        self.assertNotIn("chromium", text.lower())
        self.assertNotIn("python", text.lower())


if __name__ == "__main__":
    unittest.main()
