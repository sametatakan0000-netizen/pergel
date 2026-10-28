"""Global-first Pergel surface.

- i18n engine with 8 complete locales (tr/en/de/es/fr/ru/ar/zh), RTL
  switching, and a language selector persisted client-side.
- Accessibility hooks on every branded surface (labels, focus rings).
- The Pergel rebrand: tokens, manifest, desktop entry, icons, package
  names, and one-time legacy config migration from ``~/.config/vane``.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from src.brand import i18n, package, render, tokens, vane_app
from src.brand.icons import icon_svg
from src.brand.vane_app import user_dirs

LANGS = {"tr", "en", "de", "es", "fr", "ru", "ar", "zh"}


class TestI18n(unittest.TestCase):
    def test_eight_locales_complete(self):
        self.assertTrue(LANGS <= set(i18n.LOCALES), sorted(i18n.LOCALES))
        keys = set(i18n.LOCALES["en"])
        self.assertGreaterEqual(len(keys), 15)
        for lang, table in i18n.LOCALES.items():
            self.assertEqual(set(table), keys, f"{lang} keys incomplete")
            for k, v in table.items():
                self.assertTrue(v.strip(), f"{lang}:{k} empty")

    def test_ntp_localizes_and_switches_rtl(self):
        # the NTP is a hard-scriptless product rule: localization is STATIC
        # (pre-rendered per locale) and the switcher is plain anchors
        en = render.render_ntp()
        self.assertIn('<html lang="en"', en)   # global default language
        self.assertIn("Search the web or type a URL", en)
        self.assertNotIn("<script", en)
        self.assertIn("vane_ntp_tr.html", en)  # plain-link language switch
        tr = render.render_ntp("tr")
        self.assertIn('<html lang="tr"', tr)
        self.assertIn("arayın", tr)
        ar = render.render_ntp("ar")
        self.assertIn('<html lang="ar" dir="rtl"', ar)   # RTL static

    def test_prepare_profile_writes_localized_variants(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"LANG": "tr_TR.UTF-8"}):
                vane_app.prepare_profile(td, shield_port=41998)
            with open(os.path.join(td, "vane_ntp.html")) as f:
                self.assertIn('<html lang="tr"', f.read())  # system language
            for code in LANGS:
                self.assertTrue(
                    os.path.isfile(os.path.join(td, f"vane_ntp_{code}.html")),
                    code)

    def test_every_dynamic_surface_carries_i18n_hooks(self):
        # NTP excluded (scriptless); the dynamic surfaces translate live
        for fn in (render.render_commandbar, render.render_side_panel):
            self.assertIn('data-i18n', fn(), fn.__name__)
        self.assertIn('data-i18n', render.render_shield_panel(8787))

    def test_a11y_hooks(self):
        html = render.render_ntp()
        self.assertIn('aria-label', html)
        self.assertIn(':focus-visible', html)


class TestPergelBrand(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(tokens.NAME, "Pergel")

    def test_manifest(self):
        m = render.extension_manifest()
        self.assertEqual(m["name"], "Pergel")
        self.assertEqual(m["short_name"], "Pergel")

    def test_desktop_entry(self):
        text = render.render_desktop_entry()
        self.assertIn("Name=Pergel", text)
        self.assertIn("Exec=pergel %U", text)
        self.assertIn("Icon=pergel", text)
        self.assertIn("StartupWMClass=Pergel", text)

    def test_icon_is_compass_mark(self):
        svg = icon_svg()
        self.assertIn("M30 70 L48 26 L66 70", svg)   # the pergel legs
        self.assertIn("Q48 78 64 62", svg)           # the scribe arc

    def test_package_tree_installs_pergel(self):
        with tempfile.TemporaryDirectory() as td:
            root = package.stage_tree(os.path.join(td, "root"))
            self.assertTrue(os.access(os.path.join(root, "usr/bin/pergel"),
                                      os.X_OK))
            # compat alias for muscle memory
            self.assertTrue(os.path.islink(os.path.join(root, "usr/bin/vane")))
            with open(os.path.join(root, "usr/share/applications",
                                   "pergel.desktop")) as f:
                self.assertIn("Name=Pergel", f.read())
            for size in (48, 128, 256):
                self.assertTrue(os.path.isfile(os.path.join(
                    root, f"usr/share/icons/hicolor/{size}x{size}/apps/pergel.png")))
            self.assertTrue(os.path.isfile(os.path.join(
                root, "usr/share/icons/hicolor/scalable/apps/pergel.svg")))
            with open(os.path.join(root, "DEBIAN/control")) as f:
                self.assertIn("Package: pergel-browser", f.read())

    def test_build_deb_name(self):
        with tempfile.TemporaryDirectory() as td:
            deb = package.build_deb(td)
            self.assertTrue(os.path.basename(deb)
                            .startswith("pergel-browser_"))
            self.assertTrue(os.path.isfile(deb))

    def test_legacy_vane_config_migrates_once(self):
        with tempfile.TemporaryDirectory() as home:
            legacy = os.path.join(home, ".config", "vane")
            os.makedirs(os.path.join(legacy, "profile", "Default"))
            with open(os.path.join(legacy, "vane.prefs"), "w") as f:
                json.dump({"k": 1}, f)
            with mock.patch.dict(os.environ, {"HOME": home}):
                dirs = user_dirs()
                self.assertTrue(dirs["config"].endswith(
                    os.path.join(".config", "pergel")))
                self.assertTrue(os.path.isfile(os.path.join(
                    dirs["config"], "vane.prefs")))


if __name__ == "__main__":
    unittest.main()
