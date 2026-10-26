"""End-to-end proof over the REAL HTTP endpoint: extension rules block on the page.

POST /v1/jobs/browse -> BrowserFarmSaaSServer -> _resolve_driver -> CDP driver ->
real Chromium. A/B with the same driver path, only the extension dir differs:
  treatment (extension loaded) -> matching script BLOCKED (data-ad absent)
  control (no extension)       -> script runs (data-ad present)
  both                         -> unrelated script runs (data-banner present)

Hermetic: the extension lives in a temp dir. allow_private_targets=True is set on
this test instance only so the loopback test page is reachable; production keeps
the SSRF guard on.
"""
import http.server
import json
import os
import tempfile
import threading
import unittest
import unittest.mock
import urllib.request

from src.api.server import BrowserFarmSaaSServer

# The body needs >10 chars of extractable text or the worker's engine ladder
# treats the fetch as empty and the job fails before assertions can run.
# Markers are *visible text* injected by the scripts, so they survive
# html_to_clean_markdown (which strips body attributes and <script> tags).
PAGE = (b"<html><body><p>organic</p>"
        b"<p>This is enough extracted text for the worker to treat the fetch as a"
        b" successful content capture rather than an empty body.</p>"
        b"<div id='slot'></div>"
        b"<script src='/banner.js'></script>"
        b"<script src='/ads.example.com/x.js'></script></body></html>")
BANNER = b"document.getElementById('slot').textContent += ' banner-marker-ran';"
ADSCRIPT = b"document.getElementById('slot').textContent += ' ad-marker-ran';"

MANIFEST = '{"manifest_version": 3, "name": "test-adblock", "version": "1",' \
           ' "permissions": ["declarativeNetRequest"],' \
           ' "declarative_net_request": {"rule_resources":' \
           ' [{"id": "r", "enabled": true, "path": "r.json"}]}}'
RULES = '[{"id": 1, "priority": 1, "action": {"type": "block"},' \
        ' "condition": {"urlFilter": "/ads.example.com/",' \
        ' "resourceTypes": ["script"]}}]'


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


class HttpChainExtensionProofTests(unittest.TestCase):
    def test_extension_blocks_script_via_real_http_endpoint(self):
        httpd = http.server.HTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        page_url = f"http://127.0.0.1:{httpd.server_address[1]}/"

        with tempfile.TemporaryDirectory() as ext_root, \
                tempfile.TemporaryDirectory() as data_root:
            d = os.path.join(ext_root, "test-adblock")
            os.makedirs(d)
            with open(os.path.join(d, "manifest.json"), "w") as f:
                f.write(MANIFEST)
            with open(os.path.join(d, "r.json"), "w") as f:
                f.write(RULES)

            def fetch_html(ext_dir):
                env = {"BROWSE_API_KEY": ""}
                if ext_dir:
                    env["ORACLE_EXTENSIONS_DIR"] = ext_dir
                with unittest.mock.patch.dict(os.environ, env, clear=False):
                    if not ext_dir:
                        os.environ.pop("ORACLE_EXTENSIONS_DIR", None)
                    srv = BrowserFarmSaaSServer(
                        port=0, db_dir=data_root, profiles={},
                        nous_proxy_url="http://127.0.0.1:9/v1",
                        allow_private_targets=True)
                    srv.start_background()
                    try:
                        req = urllib.request.Request(
                            f"http://127.0.0.1:{srv.port}/v1/jobs/browse",
                            json.dumps({"url": page_url}).encode(),
                            {"Content-Type": "application/json"})
                        job = json.loads(
                            urllib.request.urlopen(req, timeout=90).read())
                    finally:
                        srv.shutdown()
                self.assertEqual(job.get("status"), "completed", job)
                return job.get("extracted_markdown") or job.get("raw_html") or ""

            treated = fetch_html(ext_root)
            control = fetch_html(None)

        # Unrelated script ran in both -> page-level JS is live.
        self.assertIn("banner-marker-ran", treated)
        self.assertIn("banner-marker-ran", control)
        # Extension's target is blocked only when the extension is loaded.
        self.assertNotIn("ad-marker-ran", treated)
        self.assertIn("ad-marker-ran", control)


if __name__ == "__main__":
    unittest.main()
