"""The plain-HTTP driver must return agent-readable main content, not raw HTML.

Raw HTML wastes the agent's context window on markup and script (Wikipedia
returned ~236 KB of which the article is a small fraction). The driver is the
token-efficiency boundary, so it must emit clean main-content Markdown.
"""
import http.server
import threading
import unittest

from src.browser_engine.worker import html_to_clean_markdown

ARTICLE = (
    "<html><head><script>var tracking = 1;</script><style>p{color:red}</style></head>"
    "<body><nav><a href='/menu'>Menu link</a></nav>"
    "<article><h1>Web scraping</h1>"
    "<p>Web scraping extracts structured data from websites. It is widely used for "
    "price monitoring, research and archiving public pages, and it has a long history "
    "in the development of search engines and data pipelines.</p>"
    "<p>Extraction tools parse the document tree and keep the textual content.</p>"
    "</article><footer>Footer boilerplate</footer></body></html>"
)


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
        else:
            body = ARTICLE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class CleanMarkdownDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.HTTPServer(("127.0.0.1", 0), _H)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.out = html_to_clean_markdown(ARTICLE)

    def test_no_raw_html_markup(self):
        self.assertNotIn("<html", self.out.lower())
        self.assertNotIn("<script", self.out.lower())
        self.assertNotIn("<p>", self.out.lower())

    def test_keeps_main_article_text(self):
        self.assertIn("Web scraping extracts structured data", self.out)

    def test_drops_script_and_boilerplate(self):
        self.assertNotIn("tracking = 1", self.out)
        self.assertNotIn("Footer boilerplate", self.out)

    def test_substantially_smaller_than_raw(self):
        self.assertLess(len(self.out), len(ARTICLE))


if __name__ == "__main__":
    unittest.main()
