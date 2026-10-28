"""RED: Vane app wiring — branded profile, live shield feed, branded command.

The whole identity must ride the REAL serving path: the desktop launcher's
``main()`` must open the branded new-tab page in a persistent branded profile,
and the engine's ``on_blocked`` decisions must feed the shield panel's live
counter. ``AdblockBrowserSession`` therefore has to accept a caller-owned
``user_data_dir`` (persistent, themed profile) and a ``start_url`` instead of
throwaway ``about:blank``.
"""
import json
import os
import tempfile
import unittest

from src.brand import tokens
from src.brand.stats import ShieldStats
from src.brand.vane_app import make_on_blocked, prepare_profile
from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession


class TestShieldWiring(unittest.TestCase):
    def test_on_blocked_feeds_the_live_counter(self):
        shield = ShieldStats()
        seen = []
        cb = make_on_blocked(shield, sink=seen.append)
        cb({"action": "block", "rule_id": "||ads^"})
        cb({"action": "allow", "rule_id": None})
        self.assertEqual(shield.snapshot()["blocked_total"], 1)
        self.assertEqual(seen, [
            {"action": "block", "rule_id": "||ads^"},
            {"action": "allow", "rule_id": None},
        ])


class TestBrandedProfile(unittest.TestCase):
    def test_prepare_profile_writes_theme_and_surfaces(self):
        with tempfile.TemporaryDirectory() as td:
            ntp = prepare_profile(td, shield_port=41234)
            self.assertEqual(ntp, os.path.join(td, "vane_ntp.html"))
            with open(os.path.join(td, "Default/Preferences")) as f:
                prefs = json.load(f)
            self.assertEqual(
                prefs["theme"]["colors"]["frame"],
                list(tokens.rgb(tokens.BG)))
            with open(os.path.join(td, "vane_ntp.html")) as f:
                self.assertIn("Pergel", f.read())
            with open(os.path.join(td, "vane_shield.html")) as f:
                self.assertIn("41234", f.read())

    def test_prepare_profile_preserves_existing_prefs(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "Default"))
            with open(os.path.join(td, "Default/Preferences"), "w") as f:
                json.dump({"download": {"prompt_for_download": True}}, f)
            prepare_profile(td, shield_port=1)
            with open(os.path.join(td, "Default/Preferences")) as f:
                prefs = json.load(f)
            self.assertTrue(prefs["download"]["prompt_for_download"])
            self.assertIn("theme", prefs)


class TestBrandedCommand(unittest.TestCase):
    def test_session_uses_caller_profile_and_start_url(self):
        bundle = compile_adblock(["||ads.example.com^"])
        sess = AdblockBrowserSession(
            bundle, browser_path="/bin/true",
            user_data_dir="/tmp/vane-profile",
            start_url="file:///tmp/vane-profile/vane_ntp.html")
        cmd = sess._build_command()
        self.assertIn("--user-data-dir=/tmp/vane-profile", cmd)
        self.assertEqual(cmd[-1], "file:///tmp/vane-profile/vane_ntp.html")


if __name__ == "__main__":
    unittest.main()
