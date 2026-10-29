"""RED: the desktop product must behave like a real browser, not a painted shell.

User feedback on the live window: opening a new tab showed Google (Chromium's
own NTP), the Pergel page "smelled AI" (centered logo, tagline, clock, dead search
box) and the window carried "Chrome for Testing" / --no-sandbox infobars with no
own identity. Contract now:

* NTP = bare wordmark + a search box that ACTUALLY searches. Nothing else.
* Ctrl+T must land on the Pergel NTP via a real ``chrome_url_overrides.newtab``
  extension — the mechanism branded browsers use.
* Window identity: ``--class=Pergel`` (+ StartupWMClass), infobars off.
* ``--no-sandbox`` only when running as root; the desktop user gets the real
  sandbox (AppArmor userns profile).
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from src.browser_engine import cdp_adblock_driver as driver
from src.brand import render, pergel_app


class TestNewTabOverrideExtension(unittest.TestCase):
    def test_manifest_overrides_chromium_new_tab(self):
        m = render.extension_manifest()
        self.assertEqual(m["manifest_version"], 3)
        self.assertEqual(m["chrome_url_overrides"]["newtab"], "pergel_ntp.html")
        self.assertEqual(m["name"], "Pergel")

    def test_write_extension_ships_manifest_and_page(self):
        with tempfile.TemporaryDirectory() as d:
            render.write_extension(d)
            with open(os.path.join(d, "manifest.json")) as f:
                m = json.load(f)
            self.assertEqual(m["chrome_url_overrides"]["newtab"],
                             "pergel_ntp.html")
            with open(os.path.join(d, "pergel_ntp.html")) as f:
                page = f.read()
            self.assertIn("Pergel", page)
            self.assertIn('name="q"', page)


class TestWindowIdentity(unittest.TestCase):
    def test_launch_flags_brand_the_window(self):
        flags = pergel_app.launch_flags("/x/ext")
        for f in ("--class=Pergel", "--disable-infobars", "--test-type",
                  "--no-first-run", "--no-default-browser-check",
                  "--load-extension=/x/ext",
                  "--disable-extensions-except=/x/ext"):
            self.assertIn(f, flags)

    def test_sandbox_flag_only_for_root(self):
        with mock.patch.object(driver.os, "geteuid", return_value=0):
            self.assertIn("--no-sandbox", driver.browser_base_args())
        with mock.patch.object(driver.os, "geteuid", return_value=1000):
            self.assertNotIn("--no-sandbox", driver.browser_base_args())

    def test_session_accepts_extra_args(self):
        import inspect
        sig = inspect.signature(driver.AdblockBrowserSession.__init__)
        self.assertIn("extra_args", sig.parameters)

    def test_wmclass_matches_class_flag(self):
        entry = render.render_desktop_entry()
        self.assertIn("StartupWMClass=Pergel", entry)
        self.assertIn("Icon=pergel", entry)


class TestDebShipsExtension(unittest.TestCase):
    def test_staged_tree_contains_the_extension(self):
        from src.brand.package import stage_tree
        with tempfile.TemporaryDirectory() as d:
            root = stage_tree(d)
            self.assertTrue(os.path.isfile(os.path.join(
                root, "usr/lib/pergel/extension/manifest.json")))


if __name__ == "__main__":
    unittest.main()
