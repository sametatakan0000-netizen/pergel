import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.browser_engine.worker import FetchBlocked, _default_url_driver

BODY = b"<html><body><h1>Hello</h1><p>" + b"word " * 40 + b"</p></body></html>"


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        routes = {
            "/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /private\n"),
            "/ok": (200, "text/html; charset=utf-8", BODY),
            "/private": (200, "text/html", BODY),
            "/forbidden": (403, "text/html", b"denied"),
            "/pdf": (200, "application/pdf", b"%PDF-1.4"),
            "/huge": (200, "text/html", b"<p>" + b"x" * (3 * 1024 * 1024)),
        }
        status, ctype, body = routes.get(self.path, (404, "text/plain", b"nf"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestHttpDriver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def fetch(self, path):
        return _default_url_driver("lightpanda", self.base + path, "s1")

    def test_ok_returns_raw_html_for_discovery(self):
        out = self.fetch("/ok")
        self.assertIn("<h1>Hello</h1>", out)  # raw HTML preserved for discover_har_api_endpoints

    def test_robots_disallow_blocks(self):
        with self.assertRaises(FetchBlocked):
            self.fetch("/private")

    def test_http_error_raises_so_worker_escalates(self):
        with self.assertRaises(Exception):
            self.fetch("/forbidden")

    def test_non_html_rejected(self):
        with self.assertRaises(FetchBlocked):
            self.fetch("/pdf")

    def test_body_capped_at_2mb(self):
        self.assertLessEqual(len(self.fetch("/huge")), 2 * 1024 * 1024)
