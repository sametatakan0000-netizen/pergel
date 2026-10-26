"""Refusal classification at the fetch layer.

A plain-HTTP response that refuses access must be detected and tagged with the
stable access-block code, so the API layer can surface it. This suite drives the
plain-HTTP driver against a local server that refuses in different ways.
"""
import http.server
import threading
import unittest
import urllib.error

from src.browser_engine.worker import FetchBlocked, _default_url_driver


class _RefusalHandler(http.server.BaseHTTPRequestHandler):
    """Serves a refusal per PATH, plus a permissive robots.txt."""

    ROUTES = {
        "/403": (403, "text/html", "<html><body>Forbidden</body></html>"),
        "/429": (429, "text/html", "<html><body>Too Many Requests</body></html>"),
        "/402": (402, "text/html", "<html><body>Payment required</body></html>"),
        "/401": (401, "text/html", "<html><body>Unauthorized</body></html>"),
        "/captcha": (200, "text/html", "<html><body>Are you a robot? "
                                      "<div class='g-recaptcha'></div></body></html>"),
        "/paywall": (200, "text/html", "<html><body>Subscribe to continue reading. "
                                       "Log in to access this article.</body></html>"),
        "/ok": (200, "text/html", "<html><body><p>plenty of visible text for extraction</p>"
                                  "</body></html>"),
    }

    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        status, ctype, body = self.ROUTES.get(self.path, (404, "text/plain", "not found"))
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if self.path == "/429":
            self.send_header("Retry-After", "30")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class RefusalClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.HTTPServer(("127.0.0.1", 0), _RefusalHandler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def _drive(self, path):
        return _default_url_driver("lightpanda", f"{self.base}{path}", "s1")

    def _assert_block(self, path, expected_code):
        with self.assertRaises(FetchBlocked) as ctx:
            self._drive(path)
        self.assertEqual(ctx.exception.code, expected_code, str(ctx.exception))

    def test_403_is_blocked_by_site(self):
        self._assert_block("/403", "blocked_by_site")

    def test_429_is_rate_limited_by_site(self):
        self._assert_block("/429", "rate_limited_by_site")

    def test_402_is_paywall_or_login_required(self):
        self._assert_block("/402", "paywall_or_login_required")

    def test_401_is_paywall_or_login_required(self):
        self._assert_block("/401", "paywall_or_login_required")

    def test_captcha_page_is_captcha_required(self):
        self._assert_block("/captcha", "captcha_required")

    def test_paywall_body_is_paywall_or_login_required(self):
        self._assert_block("/paywall", "paywall_or_login_required")

    def test_normal_page_is_not_blocked(self):
        body = self._drive("/ok")
        self.assertIn("visible text", body)
