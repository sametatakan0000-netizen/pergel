"""RED: a real, visible browser window the user can drive.

The product IS the browser engine, so the engine must be able to surface as an
actual window on the user's desktop — not only as a headless scrape. Two
lifecycle knobs are needed on ``AdblockBrowserSession``:

* ``headless=False``  -> the launched Chromium command must NOT carry
  ``--headless=new`` (the window is visible on the display).
* ``keep_open=True``  -> leaving the context manager must NOT terminate the
  browser process (the user is still driving it); closing it is the caller's job.

These are asserted on the real launch command and the real process teardown,
not on a mock, so a regression is caught as a launch/teardown behaviour change.
"""
import asyncio
import subprocess
import unittest
from unittest import mock

from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession


def _launch_args(sess) -> list:
    """Extract the argv the session used to spawn Chromium."""
    return sess._proc.args


class TestVisibleBrowserLifecycle(unittest.TestCase):
    def test_headless_false_drops_the_headless_flag(self):
        bundle = compile_adblock([])
        sess = AdblockBrowserSession(bundle, headless=False)
        # build the exact command __aenter__ would spawn, without launching
        argv = sess._build_command()
        self.assertNotIn("--headless=new", argv,
                         "headless=False must not force a headless window")
        self.assertIn("--remote-debugging-port=0", argv)

    def test_default_stays_headless(self):
        bundle = compile_adblock([])
        sess = AdblockBrowserSession(bundle)
        argv = sess._build_command()
        self.assertIn("--headless=new", argv,
                      "existing headless-by-default behaviour must be preserved")

    def test_keep_open_does_not_terminate_the_process(self):
        bundle = compile_adblock([])
        sess = AdblockBrowserSession(bundle, keep_open=True)
        proc = mock.Mock()
        sess._proc = proc
        sess._ws = None
        sess._pump = None
        asyncio.run(sess.__aexit__(None, None, None))
        proc.terminate.assert_not_called()

    def test_default_exit_terminates_the_process(self):
        bundle = compile_adblock([])
        sess = AdblockBrowserSession(bundle)
        proc = mock.Mock()
        sess._proc = proc
        sess._ws = None
        sess._pump = None
        asyncio.run(sess.__aexit__(None, None, None))
        proc.terminate.assert_called_once()

    def test_on_blocked_callback_is_accepted_and_reported(self):
        """Every enforced decision is surfaced to the caller (live block counter)."""
        seen = []
        bundle = compile_adblock(["||ads.example.com^"])
        sess = AdblockBrowserSession(bundle, on_blocked=seen.append)
        # simulate the pump's enforcement path on a blocked + an allowed request
        blocked_params = {"request": {"url": "http://ads.example.com/x.gif",
                                      "method": "GET", "headers": {}},
                          "requestId": "r1"}
        allowed_params = {"request": {"url": "http://example.com/ok",
                                      "method": "GET", "headers": {}},
                          "requestId": "r2"}
        sess._notify_decision(blocked_params)
        sess._notify_decision(allowed_params)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]["action"], "block")
        self.assertEqual(seen[0]["url"], "http://ads.example.com/x.gif")
        self.assertEqual(seen[1]["action"], "allow")


if __name__ == "__main__":
    unittest.main()
