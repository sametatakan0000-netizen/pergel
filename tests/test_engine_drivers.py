"""Real engine drivers: lightpanda (tier-1) and Chromium/Playwright (tier-2)."""
import http.server
import os
import shutil
import threading
import unittest
from unittest import mock

from src.browser_engine.egress_proxy import EgressPolicy
from src.browser_engine.engine_drivers import (
    engine_driver,
    _lightpanda_bin,
    EngineUnavailable,
)
from src.browser_engine.worker import BrowserWorker, FetchBlocked, private_targets_allowed

PAGE = b"""<!doctype html><html><head><title>T</title></head>
<body><h1>Merhaba Motor</h1><p>Bu bir test sayfasidir ve yeterince uzun bir govdeye sahiptir.</p></body></html>"""

# Hermetic resolver stub: the SSRF pre-flight resolves hosts without real DNS.
PUBLIC_POLICY = EgressPolicy(resolver=lambda host: ["93.184.216.34"])


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/robots"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args):
        pass


class PolicyTests(unittest.TestCase):
    def test_robots_block_raises_before_any_engine_runs(self):
        import subprocess
        from unittest import mock
        import src.browser_engine.engine_drivers as ed
        with mock.patch.object(ed, "_allowed_by_robots", return_value=False), \
                mock.patch.object(subprocess, "run") as run:
            with self.assertRaises(FetchBlocked):
                engine_driver("lightpanda", "https://blocked.example.com/", "s", policy=PUBLIC_POLICY)
        run.assert_not_called()

    def test_unknown_engine_falls_back_to_plain_http_driver(self):
        import src.browser_engine.engine_drivers as ed
        seen = {}
        orig_allowed, orig_default = ed._allowed_by_robots, ed._default_url_driver
        ed._allowed_by_robots = lambda url, ua, **kw: True
        ed._default_url_driver = lambda engine, url, s, **kw: seen.setdefault("call", (engine, url)) and ""
        try:
            engine_driver("camofox", "https://example.com/", "s")
        finally:
            ed._allowed_by_robots, ed._default_url_driver = orig_allowed, orig_default
        self.assertEqual(seen["call"][0], "camofox")

    def test_lightpanda_bin_prefers_env_override(self):
        stub = os.path.join(LightpandaStubTests._dir(), "lp-env")
        with open(stub, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(stub, 0o755)
        os.environ["LIGHTPANDA_BIN"] = stub
        try:
            self.assertEqual(_lightpanda_bin(), stub)
        finally:
            del os.environ["LIGHTPANDA_BIN"]


class LightpandaStubTests(unittest.TestCase):
    def test_stub_binary_output_is_returned(self):
        stub = os.path.join(self._dir(), "lp-stub")
        with open(stub, "w") as fh:
            fh.write("#!/bin/sh\necho '<html><body>STUB-HTML</body></html>'\n")
        os.chmod(stub, 0o755)
        os.environ["LIGHTPANDA_BIN"] = stub
        try:
            # PUBLIC_POLICY is strict -> the new SSRF model routes through the
            # relay; stub the guard so this does not bind a real port.
            with mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard",
                            return_value=mock.MagicMock()):
                out = engine_driver("lightpanda", "https://example.com/", "s", policy=PUBLIC_POLICY)
        finally:
            del os.environ["LIGHTPANDA_BIN"]
        self.assertIn("STUB-HTML", out)

    def test_stub_binary_failure_raises_so_worker_escalates(self):
        stub = os.path.join(self._dir(), "lp-fail")
        with open(stub, "w") as fh:
            fh.write("#!/bin/sh\nexit 3\n")
        os.chmod(stub, 0o755)
        os.environ["LIGHTPANDA_BIN"] = stub
        try:
            with self.assertRaises(Exception):
                engine_driver("lightpanda", "https://example.com/", "s", policy=PUBLIC_POLICY)
        finally:
            del os.environ["LIGHTPANDA_BIN"]

    @staticmethod
    def _dir():
        d = os.path.join(os.path.dirname(__file__), "_stubs")
        os.makedirs(d, exist_ok=True)
        return d


class RealEngineIntegration(unittest.TestCase):
    """Real binaries against a local HTTP server. Skipped where an engine is not installed."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_lightpanda_renders_local_page(self):
        if not (_lightpanda_bin() and os.path.exists(_lightpanda_bin())):
            self.skipTest("lightpanda binary not installed")
        with private_targets_allowed():  # local test server = private target opt-in
            out = engine_driver("lightpanda", self.url, "it")
        self.assertIn("Merhaba Motor", out)

    def test_chromium_renders_local_page(self):
        try:
            import playwright  # noqa: F401
        except ImportError:
            self.skipTest("playwright not installed")
        with private_targets_allowed():  # local test server = private target opt-in
            out = engine_driver("chromium-browser-use", self.url, "it")
        self.assertIn("Merhaba Motor", out)

    def test_worker_cascade_produces_markdown_with_real_engine(self):
        if not (_lightpanda_bin() and os.path.exists(_lightpanda_bin())):
            self.skipTest("lightpanda binary not installed")
        with private_targets_allowed():  # local test server = private target opt-in
            res = BrowserWorker(driver_fn=engine_driver).execute_task("it1", self.url)
        self.assertTrue(res["oracle_passed"])
        self.assertIn("Merhaba Motor", res["markdown"])


if __name__ == "__main__":
    unittest.main()
