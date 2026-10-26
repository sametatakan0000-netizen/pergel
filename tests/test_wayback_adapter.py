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

    def test_reddit_url_falls_through_to_wayback_without_creds(self):
        # reddit-oauth is tried first but returns None when no user creds are
        # configured, so a Reddit URL is ultimately handled by the wayback adapter.
        from unittest import mock

        reg = default_registry()
        url = "https://www.reddit.com/r/python/comments/abc/"
        matched = reg.match(url)
        self.assertEqual(matched.name, "reddit-oauth")

        # Fake HTTP returning a wayback availability payload so the wayback
        # adapter has something to parse.
        def fake_get(u):
            if "archive.org/wayback/available" in u:
                return {"archived_snapshots": {"closest": {
                    "available": True,
                    "url": "http://web.archive.org/web/20240101000000/" + url,
                    "timestamp": "20240101000000", "status": "200"}}}
            return "<html><body><p>archived reddit page</p></body></html>"

        with mock.patch("src.browser_engine.platform_adapters._reddit_oauth_creds", return_value=None):
            for a in reg.adapters:
                if a.can_handle(url):
                    res = a.fetch(url, fake_get)
                    if res is not None:
                        self.assertEqual(res.adapter, "wayback")
                        return
        self.fail("no adapter produced a result for the reddit url")


if __name__ == "__main__":
    unittest.main()


class TestWaybackUsesTextGetter(unittest.TestCase):
    def test_default_getter_returns_text_not_json(self):
        # The replay body is HTML, not JSON — the default JSON getter would
        # return None and silently drop a valid snapshot.
        adapter = WaybackAdapter()
        self.assertTrue(hasattr(adapter, "default_getter"))
        self.assertIs(adapter.default_getter, __import__(
            "src.browser_engine.platform_adapters", fromlist=["_http_get_text"])._http_get_text)
