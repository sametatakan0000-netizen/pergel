import unittest
from unittest import mock

from src.browser_engine.platform_adapters import RedditOAuthAdapter, default_registry


class FakeGet:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.routes.get(url)


CREDS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "username": "test-user",
    "password": "test-pass",
}


class TestCanHandle(unittest.TestCase):
    def test_reddit_urls(self):
        a = RedditOAuthAdapter()
        self.assertTrue(a.can_handle("https://www.reddit.com/r/Python/"))
        self.assertTrue(a.can_handle("https://reddit.com/user/spez/about.json"))

    def test_not_other_urls(self):
        self.assertFalse(RedditOAuthAdapter().can_handle("https://example.com/"))
        self.assertFalse(RedditOAuthAdapter().can_handle("https://www.linkedin.com/posts/x"))


class TestNoCredentials(unittest.TestCase):
    def test_returns_none_when_no_creds(self):
        with mock.patch("src.browser_engine.platform_adapters._reddit_oauth_creds", return_value=None):
            res = RedditOAuthAdapter().fetch("https://www.reddit.com/r/Python/", lambda u: None)
        self.assertIsNone(res)


class TestWithCredentials(unittest.TestCase):
    def test_token_exchange_then_api_call(self):
        listing = {"kind": "Listing", "data": {"children": [
            {"data": {"title": "Top Post", "selftext": "body here"}}]}}
        a = RedditOAuthAdapter()
        with mock.patch("src.browser_engine.platform_adapters._reddit_oauth_creds", return_value=CREDS), \
             mock.patch.object(a, "_exchange_token", return_value="tok-123") as ex:
            with mock.patch.object(a, "_api_get", return_value=listing) as ag:
                res = a.fetch("https://www.reddit.com/r/Python/", FakeGet({}))
        ag.assert_called_once()
        self.assertEqual(ag.call_args[0][0], "https://oauth.reddit.com/r/Python/hot.json")
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "reddit-oauth")
        self.assertIn("Top Post", res.markdown)
        ex.assert_called_once()

    def test_token_expired_refreshed(self):
        # If the cached token is expired, _exchange_token must be called again.
        a = RedditOAuthAdapter()
        a._token = "old"
        a._token_expiry = 0  # already expired
        with mock.patch("src.browser_engine.platform_adapters._reddit_oauth_creds", return_value=CREDS), \
             mock.patch.object(a, "_exchange_token", return_value="new-tok") as ex:
            tok = a._get_token()
        ex.assert_called_once()
        self.assertEqual(tok, "new-tok")


class TestRedditBeforeWayback(unittest.TestCase):
    def test_registry_order(self):
        names = [a.name for a in default_registry().adapters]
        self.assertIn("reddit-oauth", names)
        self.assertLess(names.index("reddit-oauth"), names.index("wayback"))


if __name__ == "__main__":
    unittest.main()
