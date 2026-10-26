import unittest
import urllib.parse

from src.browser_engine.platform_adapters import WaybackAdapter, default_registry


class FakeGet:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.routes.get(url)


class TestWaybackCanHandle(unittest.TestCase):
    def test_matches_any_url_with_archive_prefix_or_wildcard(self):
        a = WaybackAdapter()
        self.assertTrue(a.can_handle("web.archive.org/https://example.com/gone"))
        self.assertTrue(a.can_handle("https://web.archive.org/*/https://example.com/gone"))

    def test_reddit_linkedin_urls_trigger_wayback_fallback(self):
        # Reddit .json is 403 and LinkedIn has no read API -> archived path.
        a = WaybackAdapter()
        self.assertTrue(a.can_handle("https://www.reddit.com/r/python/comments/abc/"))
        self.assertTrue(a.can_handle("https://www.linkedin.com/posts/foo-123"))

    def test_other_urls_not_handled(self):
        self.assertFalse(WaybackAdapter().can_handle("https://example.com/"))


class TestWaybackFetch(unittest.TestCase):
    def _adapter(self, get):
        return WaybackAdapter()

    def test_availability_replay_fetched(self):
        target = "https://www.reddit.com/r/python/comments/abc/"
        avail = '{"archived_snapshots":{"closest":{"available":true,' \
                '"url":"https://web.archive.org/web/20240101120000/' + target + '",' \
                '"timestamp":"20240101120000","status":"200"}}}'
        raw = "<html><body><article><h1>Archived Post</h1><p>body text</p></article></body></html>"
        api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(target, safe="")
        get = FakeGet({
            api: avail,
            "https://web.archive.org/web/20240101120000id_/" + target: raw,
        })
        res = WaybackAdapter().fetch(target, get)
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "wayback")
        self.assertIn("Archived Post", res.markdown)
        self.assertEqual(res.metadata.get("timestamp"), "20240101120000")

    def test_no_snapshot_returns_none(self):
        target = "https://www.linkedin.com/posts/foo-123"
        api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(target, safe="")
        get = FakeGet({api: "{}"})
        self.assertIsNone(WaybackAdapter().fetch(target, get))


class TestRegistryWayback(unittest.TestCase):
    def test_wayback_registered_and_last(self):
        names = [a.name for a in default_registry().adapters]
        self.assertIn("wayback", names)
        self.assertEqual(names[-1], "wayback")

    def test_reddit_url_routes_to_wayback(self):
        reg = default_registry()
        a = reg.match("https://www.reddit.com/r/python/comments/abc/")
        self.assertEqual(a.name, "wayback")


if __name__ == "__main__":
    unittest.main()
