import unittest

from src.browser_engine.platform_adapters import RssSitemapAdapter, default_registry


class FakeGet:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.routes.get(url)


RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Example Blog</title>
<item><title>Post One</title><link>https://example.com/1</link>
<description>First post summary</description></item>
<item><title>Post Two</title><link>https://example.com/2</link>
<description>Second post</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Blog</title>
<entry><title>Entry A</title><link href="https://example.com/a"/>
<summary>Alpha</summary></entry>
</feed>"""

SITEMAP = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://example.com/page1</loc></url>
<url><loc>https://example.com/page2</loc></url>
</urlset>"""


class TestRssSitemapAdapter(unittest.TestCase):
    def test_can_handle_bare_site_urls(self):
        a = RssSitemapAdapter()
        self.assertTrue(a.can_handle("https://example.com/"))
        self.assertTrue(a.can_handle("https://blog.example.com/"))
        # known adapters still own their URLs
        self.assertFalse(a.can_handle("https://github.com/o/r"))
        self.assertFalse(a.can_handle("https://www.npmjs.com/package/x"))
        self.assertFalse(a.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_fetches_rss_feed_and_renders_items(self):
        site = "https://example.com/"
        get = FakeGet({site + "feed": RSS})
        res = RssSitemapAdapter().fetch(site, get)
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "rss")
        self.assertIn("Post One", res.markdown)
        self.assertIn("First post summary", res.markdown)
        self.assertEqual(res.metadata.get("items"), 2)

    def test_atom_feed_supported(self):
        site = "https://example.com/"
        get = FakeGet({site + "feed": ATOM})
        res = RssSitemapAdapter().fetch(site, get)
        self.assertIsNotNone(res)
        self.assertIn("Entry A", res.markdown)

    def test_sitemap_fallback_when_no_feed(self):
        site = "https://example.com/"
        get = FakeGet({site + "sitemap.xml": SITEMAP})
        res = RssSitemapAdapter().fetch(site, get)
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "sitemap")
        self.assertIn("https://example.com/page1", res.markdown)
        self.assertEqual(res.metadata.get("urls"), 2)

    def test_no_feed_or_sitemap_returns_none(self):
        get = FakeGet({})
        self.assertIsNone(RssSitemapAdapter().fetch("https://example.com/", get))


class TestRegistryRssLast(unittest.TestCase):
    def test_rss_is_last_fallback(self):
        names = [a.name for a in default_registry().adapters]
        self.assertEqual(
            names,
            ["npm", "github", "youtube-transcript", "oembed", "rss"])

    def test_bare_site_url_routes_to_rss(self):
        reg = default_registry()
        self.assertEqual(reg.match("https://example.com/").name, "rss")


if __name__ == "__main__":
    unittest.main()


class TestCommonFeedPaths(unittest.TestCase):
    def test_rss_bare_path_probed(self):
        # news.ycombinator.com serves its feed at /rss (bare, no .xml).
        site = "https://news.ycombinator.com/"
        feed = site + "rss"
        get = FakeGet({feed: RSS})
        res = RssSitemapAdapter().fetch(site, get)
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "rss")
