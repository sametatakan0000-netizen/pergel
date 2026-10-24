import unittest

from src.bench.install import pick_cft_urls

SAMPLE = {"channels": {"Stable": {"version": "156.0.8078.47", "downloads": {
    "chrome": [{"platform": "linux64", "url": "https://x/chrome-linux64.zip"},
               {"platform": "win64", "url": "https://x/chrome-win64.zip"}],
    "chrome-headless-shell": [{"platform": "linux64", "url": "https://x/hs-linux64.zip"}]}}}}


class InstallTests(unittest.TestCase):
    def test_picks_linux64_assets_for_channel(self):
        version, urls = pick_cft_urls(SAMPLE, "Stable", "linux64")
        self.assertEqual(version, "156.0.8078.47")
        self.assertEqual(urls, {"chrome": "https://x/chrome-linux64.zip",
                                "chrome-headless-shell": "https://x/hs-linux64.zip"})

    def test_missing_channel_raises(self):
        with self.assertRaises(KeyError):
            pick_cft_urls(SAMPLE, "Beta", "linux64")
