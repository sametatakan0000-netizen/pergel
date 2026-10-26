"""Engine launch path MUST wire egress enforcement when enabled (not a shelf).

RED first: chromium_proxy_args are not yet passed to Playwright's launch().
Hermetic — a stub captures the launch kwargs; no real browser, no sudo.
"""
import unittest
from unittest import mock


class LaunchArgsTests(unittest.TestCase):
    def test_chromium_launch_receives_proxy_args_when_enforcement_on(self):
        with mock.patch.dict("os.environ", {"ORACLE_EGRESS_ENFORCE": "1",
                                           "ORACLE_EGRESS_PROXY_HOST": "10.255.255.1",
                                           "ORACLE_EGRESS_PROXY_PORT": "8899"}):
            from src.browser_engine.engine_drivers import _chromium_launch_args
            # Argument generation only: do not bind a real proxy in unit tests.
            with mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard"):
                args = _chromium_launch_args()
        self.assertIn("--proxy-server=http://10.255.255.1:8899", args)
        self.assertTrue(any(a.startswith("--host-resolver-rules=") for a in args))

    def test_chromium_launch_args_empty_when_enforcement_off(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ORACLE_EGRESS_ENFORCE", None)
            from src.browser_engine.engine_drivers import _chromium_launch_args
            args = _chromium_launch_args()
        self.assertEqual(args, [])

    def test_enforcement_defaults_to_off(self):
        import os
        os.environ.pop("ORACLE_EGRESS_ENFORCE", None)
        from src.browser_engine.engine_drivers import _egress_enforce
        self.assertFalse(_egress_enforce())


if __name__ == "__main__":
    unittest.main()
