import json
import unittest
from urllib.parse import quote

from src.browser_engine.platform_adapters import (
    ALLOWED_API_HOSTS,
    OEmbedAdapter,
    default_registry,
)


class FakeGet:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.routes.get(url)


class TestOEmbedKnownProviders(unittest.TestCase):
    def test_allow_list_includes_oembed_hosts(self):
        for host in ("www.youtube.com", "vimeo.com", "graph.facebook.com"):
            self.assertIn(host, ALLOWED_API_HOSTS)

    def test_unknown_host_is_not_claimed(self):
        a = OEmbedAdapter()
        self.assertFalse(a.can_handle("https://blog.example.com/post/1"))
        self.assertFalse(a.can_handle("https://www.npmjs.com/package/x"))

    def test_youtube_watch_uses_youtube_oembed_without_fetching_page(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ob = "https://www.youtube.com/oembed?url=" + quote(url, safe="") + "&format=json"
        get = FakeGet({ob: {"type": "video", "title": "Vid",
                            "author_name": "Chan", "provider_name": "YouTube"}})
        res = OEmbedAdapter().fetch(url, get)
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "oembed")
        self.assertIn("Vid", res.markdown)
        self.assertIn("Chan", res.markdown)
        self.assertEqual(get.calls, [ob])  # only the oEmbed endpoint

    def test_instagram_response_without_title_still_accepted(self):
        # Meta's live IG oEmbed returns provider_name/html but no title/author_name.
        url = "https://www.instagram.com/p/fA9uwTtkSN/"
        ob = ("https://graph.facebook.com/v26.0/instagram_oembed?url="
              + quote(url, safe=""))
        get = FakeGet({ob: {"version": "1.0", "provider_name": "Instagram",
                            "provider_url": "https://www.instagram.com/",
                            "type": "rich", "width": 658,
                            "html": "<blockquote class=\"instagram-media\"></blockquote>"}})
        res = OEmbedAdapter().fetch(url, get)
        self.assertIsNotNone(res)
        self.assertIn("Instagram", res.markdown)

    def test_instagram_post_uses_tokenless_graph_oembed(self):
        url = "https://www.instagram.com/p/fA9uwTtkSN/"
        ob = ("https://graph.facebook.com/v26.0/instagram_oembed?url="
              + quote(url, safe=""))
        get = FakeGet({ob: {"type": "rich", "author_name": "user1",
                            "provider_name": "Instagram"}})
        res = OEmbedAdapter().fetch(url, get)
        self.assertIsNotNone(res)
        self.assertIn("user1", res.markdown)
        self.assertIn("Instagram", res.markdown)

    def test_vimeo_uses_vimeo_oembed(self):
        url = "https://vimeo.com/12345"
        ob = "https://vimeo.com/api/oembed.json?url=" + quote(url, safe="")
        get = FakeGet({ob: {"type": "video", "title": "Vim", "author_name": "VUser"}})
        res = OEmbedAdapter().fetch(url, get)
        self.assertIsNotNone(res)
        self.assertIn("Vim", res.markdown)

    def test_endpoint_failure_returns_none(self):
        url = "https://vimeo.com/999"
        self.assertIsNone(OEmbedAdapter().fetch(url, FakeGet({})))


class TestRegistryOrder(unittest.TestCase):
    def test_registry_has_npm_github_oembed(self):
        names = [a.name for a in default_registry().adapters]
        self.assertEqual(names, ["npm", "github", "oembed"])

    def test_each_url_routes_to_its_adapter(self):
        reg = default_registry()
        self.assertEqual(reg.match("https://github.com/o/r").name, "github")
        self.assertEqual(reg.match("https://www.npmjs.com/package/x").name, "npm")
        self.assertEqual(reg.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ").name, "oembed")
        self.assertIsNone(reg.match("https://blog.example.com/p"))


if __name__ == "__main__":
    unittest.main()
