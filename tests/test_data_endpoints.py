"""Product data-access endpoints: /v1/map, /v1/extract, /v1/crawl.

These fill the honest gaps the README used to list. Each is deterministic and
backed by the pure logic in src/api/extract.py and sitemap_urls().

Contracts:
  POST /v1/map     {"url": <site or sitemap url>} -> {"urls": [...], "source": <sitemap url>}
  POST /v1/extract {"url": <page>, "fields": [{name,jsonld,css,regex}, ...]}
                   -> {"fields": {...}, "markdown": <clean text>}
  POST /v1/crawl   {"urls": [<page>, ...], "fields": [...]?}
                   -> {"results": [{"url","fields","markdown"}...], "count": N}
"""
import json
import socket as _socket
import tempfile
import unittest
import urllib.error
import urllib.request

from src.api.server import BrowserFarmSaaSServer

_REAL_GETADDRINFO = _socket.getaddrinfo


def _fake_dns(host, *args, **kwargs):
    if isinstance(host, str) and host.endswith("example.com"):
        port = args[0] if args else kwargs.get("port", 0)
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
    return _REAL_GETADDRINFO(host, *args, **kwargs)


def setUpModule():
    _socket.getaddrinfo = _fake_dns
    # Hermetic: disable the RSS/sitemap probe (covered elsewhere) so nothing hits real TCP.
    global _RSS_SAVED
    from src.browser_engine import platform_adapters as _pa
    _RSS_SAVED = _pa.RssSitemapAdapter.fetch
    _pa.RssSitemapAdapter.fetch = lambda self, url, get: None


def tearDownModule():
    _socket.getaddrinfo = _REAL_GETADDRINFO
    from src.browser_engine import platform_adapters as _pa
    _pa.RssSitemapAdapter.fetch = _RSS_SAVED


SITEMAP_XML = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               "<url><loc>https://example.com/</loc></url>"
               "<url><loc>https://example.com/pricing</loc></url></urlset>")

PAGE = ('<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Pergel Pro","price":"49"}'
        '</script></head><body><span id="stock">In stock</span>'
        "<p>The starter plan costs 49 dollars monthly.</p></body></html>")


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data,
                                 method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class _Base(unittest.TestCase):
    def start(self, driver=None, get_text=None, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = BrowserFarmSaaSServer(
            port=0, db_dir=tmp.name, profiles={},
            driver_fn=driver or (lambda e, u, s: PAGE),
            get_text_fn=get_text or (lambda u: SITEMAP_XML),
            nous_proxy_url="http://127.0.0.1:9/v1", **kw)
        srv.start_background()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.port}"


class TestMap(_Base):
    def test_lists_sitemap_urls(self):
        base = self.start()
        st, body = call(base, "/v1/map", {"url": "https://example.com"})
        self.assertEqual(st, 200)
        self.assertEqual(body["urls"], ["https://example.com/", "https://example.com/pricing"])
        self.assertIn("source", body)

    def test_requires_url(self):
        base = self.start()
        st, body = call(base, "/v1/map", {})
        self.assertEqual(st, 400)
        self.assertIn("code", body["error"])


class TestExtract(_Base):
    def test_extracts_named_fields(self):
        base = self.start()
        st, body = call(base, "/v1/extract", {
            "url": "https://example.com/p",
            "fields": [
                {"name": "product_name", "jsonld": "name"},
                {"name": "price", "jsonld": "price"},
                {"name": "stock", "css": "stock"},
            ],
        })
        self.assertEqual(st, 200)
        self.assertEqual(body["fields"]["product_name"], "Pergel Pro")
        self.assertEqual(body["fields"]["price"], "49")
        self.assertEqual(body["fields"]["stock"], "In stock")
        self.assertIn("markdown", body)

    def test_requires_url_and_fields(self):
        base = self.start()
        self.assertEqual(call(base, "/v1/extract", {"fields": []})[0], 400)
        self.assertEqual(call(base, "/v1/extract", {"url": "https://example.com"})[0], 400)


class TestCrawl(_Base):
    def test_crawls_multiple_urls(self):
        base = self.start()
        st, body = call(base, "/v1/crawl", {
            "urls": ["https://example.com/a", "https://example.com/b"],
            "fields": [{"name": "name", "jsonld": "name"}],
        })
        self.assertEqual(st, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["results"][0]["fields"]["name"], "Pergel Pro")

    def test_caps_url_count(self):
        base = self.start()
        st, body = call(base, "/v1/crawl", {"urls": [f"https://example.com/{i}" for i in range(200)]})
        # over the cap -> 400, never an unbounded fan-out
        self.assertEqual(st, 400)
        self.assertIn("code", body["error"])


if __name__ == "__main__":
    unittest.main()
