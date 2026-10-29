"""Page-level A/B via the PRODUCTION loader (load_extensions_dir + CDP driver).

A/B on real Chromium, same driver both runs, only the ExtensionHost differs:
  treatment (extension dir loaded) -> /ads.example.com/ script BLOCKED (data-ad ABSENT)
  control (no extension)           -> script runs (data-ad PRESENT)
  both                             -> unrelated /banner.js runs (data-banner PRESENT)
"""
import http.server
import os
import tempfile
import threading
import unittest

from tests.test_cdp_e2e_live import _find_chromium  # noqa: F401  (skip gate)
from src.browser_engine.adblock_session import AdblockBundle
from src.browser_engine.cdp_adblock_driver import make_adblock_driver
from src.browser_engine.extension_host import load_extensions_dir

PAGE = (b"<html><body><p>organic</p><script src='/banner.js'></script>"
        b"<script src='/ads.example.com/x.js'></script></body></html>")
BANNER = b"document.body.setAttribute('data-banner','ran');"
ADSCRIPT = b"document.body.setAttribute('data-ad','ran');"


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/banner.js"):
            body, ctype = BANNER, "application/javascript"
        elif "ads.example.com" in self.path:
            body, ctype = ADSCRIPT, "application/javascript"
        else:
            body, ctype = PAGE, "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class LoadExtensionsDirPageProofTests(unittest.TestCase):
    def test_production_loader_blocks_matching_script_on_page(self):
        try:
            import websockets  # noqa: F401
        except ImportError:
            self.skipTest('websockets not installed')
        if _find_chromium() is None:
            self.skipTest('no chromium binary')

        httpd = http.server.HTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"

        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "test-adblock")
            os.makedirs(d)
            with open(os.path.join(d, "manifest.json"), "w") as f:
                f.write('{"manifest_version": 3, "name": "test-adblock", "version": "1",'
                        ' "permissions": ["declarativeNetRequest"],'
                        ' "declarative_net_request": {"rule_resources":'
                        ' [{"id": "r", "enabled": true, "path": "r.json"}]}}')
            with open(os.path.join(d, "r.json"), "w") as f:
                f.write('[{"id": 1, "priority": 1, "action": {"type": "block"},'
                        ' "condition": {"urlFilter": "/ads.example.com/",'
                        ' "resourceTypes": ["script"]}}]')

            host = load_extensions_dir(root)
            self.assertIsNotNone(host)

            from src.browser_engine.worker import private_targets_allowed

            def run(h):
                drv = make_adblock_driver(AdblockBundle(), extensions=h)
                with private_targets_allowed(True):
                    return drv("chromium", url, "live")

            treated = run(host)
            control = run(None)

        # Unrelated script ran in BOTH runs -> page-level JS is live.
        self.assertIn("data-banner", treated)
        self.assertIn("data-banner", control)
        # The extension's target script is blocked only when the extension is on.
        self.assertNotIn("data-ad", treated)
        self.assertIn("data-ad", control)


if __name__ == "__main__":
    unittest.main()
