"""Chromium must launch INSIDE bf_engine when enforcement is on (fail-closed)."""
import os
import unittest
from unittest import mock


class NetnsChromiumWrapperTests(unittest.TestCase):
    def test_wrapper_runs_chrome_inside_namespace(self):
        from src.browser_engine.engine_drivers import _netns_chromium_wrapper
        path = _netns_chromium_wrapper("/opt/chrome", namespace="bf_engine")
        text = open(path).read()
        self.assertIn("ip netns exec bf_engine", text)
        self.assertIn("/opt/chrome", text)
        self.assertIn("exec ", text)
        self.assertNotIn("SUDO_PASSWORD", text)  # never bake secrets into files
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o700)

    def test_enforced_launch_uses_wrapper_executable(self):
        env = {"ORACLE_EGRESS_ENFORCE": "1", "ORACLE_EGRESS_NETNS": "1"}
        with mock.patch.dict(os.environ, env), \
             mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard"), \
             mock.patch("src.browser_engine.engine_drivers._netns_chromium_wrapper",
                        return_value="/tmp/wrap.sh") as w:
            from src.browser_engine.engine_drivers import _launch_kwargs
            kw = _launch_kwargs("/opt/chrome")
        w.assert_called_once()
        self.assertEqual(kw["executable_path"], "/tmp/wrap.sh")
        self.assertTrue(any(a.startswith("--proxy-server=") for a in kw["args"]))

    def test_no_netns_when_enforcement_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORACLE_EGRESS_ENFORCE", None)
            from src.browser_engine.engine_drivers import _launch_kwargs
            kw = _launch_kwargs("/opt/chrome")
        self.assertEqual(kw, {})


if __name__ == "__main__":
    unittest.main()
