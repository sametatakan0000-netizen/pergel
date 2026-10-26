"""Page-level proof: a blocked extension script must not execute on the page.

A/B on real Chromium against a local HTTP server:
  control (no extension)  -> banner.js runs, marks <body data-banner="ran">
  treatment (extension)   -> banner.js is blocked, marker is ABSENT
"""
import asyncio
import http.server
import threading
import unittest
import unittest.mock

from tests.test_cdp_e2e_live import _find_chromium, websockets
from src.browser_engine.adblock_session import AdblockBundle
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
from src.browser_engine.extension_host import Extension, ExtensionHost

PAGE = (
    b"<html><body><p>organic</p>"
    b"<script src='/banner.js'></script></body></html>"
)
BANNER = b"document.body.setAttribute('data-banner','ran');"


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = BANNER if self.path == "/banner.js" else PAGE
        ctype = "application/javascript" if self.path == "/banner.js" else "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _block_banner_host():
    host = ExtensionHost()
    host.attach(Extension("page-ext", dnr_rules=[
        {"id": 1, "priority": 1, "action": {"type": "block"},
         "condition": {"urlFilter": "/banner.js", "resourceTypes": ["script"]}},
    ]))
    return host


class TestBlockedScriptDoesNotRunOnPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _find_chromium() is None or websockets is None:
            raise unittest.SkipTest("no chromium binary or websockets lib")
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _fetch(self, extensions):
        async def go():
            async with AdblockBrowserSession(AdblockBundle(),
                                             extensions=extensions) as sess:
                return await sess.fetch(self.url, host="127.0.0.1", timeout=15)
        return asyncio.run(go())

    def test_control_script_runs_without_extension(self):
        body = self._fetch(None)
        self.assertIn("data-banner", str(body))

    def test_blocked_script_does_not_run(self):
        body = self._fetch(_block_banner_host())
        self.assertNotIn("data-banner", str(body))


if __name__ == "__main__":
    unittest.main()
