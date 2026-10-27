"""User-directed single-URL fetch may bypass robots.txt; automated crawl may not.

Policy (decided by the user, 2026-10-26):
- Automated/crawl path: robots.txt Disallow -> robots_disallowed (unchanged).
- User-directed single URL (explicit `user_directed=True`): the user is the
  requester, so robots is reported as a note but the fetch proceeds.
  Site-level refusals (403/429/captcha/paywall) are still surfaced, never bypassed.
"""
import unittest
from unittest import mock

from src.browser_engine import worker as w
from src.browser_engine.egress_proxy import EgressPolicy


DISALLOW_ALL = b"User-agent: *\nDisallow: /\n"


class _FakeResp:
    def __init__(self, body: bytes, ctype: str = "text/html; charset=utf-8"):
        self._body = body
        self.headers = {"Content-Type": ctype}

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_fetch_factory(robots_body: bytes, page_body: bytes):
    """Fake the pinned-fetch seam (robots.txt + page fetch)."""
    def fake_fetch(url, policy, timeout=15, headers=None, egress=None, **kw):
        if url.endswith("/robots.txt"):
            return _FakeResp(robots_body, "text/plain")
        return _FakeResp(page_body)
    return fake_fetch


# h.test never resolves; the policy's injected resolver pretends it maps to
# 127.0.0.1 so the egress check passes and only the fetch seam is mocked.
FAKE_POLICY = EgressPolicy(resolver=lambda host: ["127.0.0.1"], allow_literal=True)


class UserDirectedRobotsTests(unittest.TestCase):
    def setUp(self):
        w._ROBOTS_CACHE.clear()

    def test_automated_fetch_still_blocked_by_robots(self):
        fake = _fake_fetch_factory(DISALLOW_ALL, b"<html><body>hi</body></html>")
        with mock.patch.object(w, "_pinned_fetch", fake):
            with self.assertRaises(w.FetchBlocked) as ctx:
                w._default_url_raw("lightpanda", "http://h.test/page", "s", policy=FAKE_POLICY)
        self.assertEqual(ctx.exception.code, "robots_disallowed")

    def test_user_directed_fetch_bypasses_robots(self):
        fake = _fake_fetch_factory(DISALLOW_ALL, b"<html><body>hello world</body></html>")
        with mock.patch.object(w, "_pinned_fetch", fake):
            text = w._default_url_raw("lightpanda", "http://h.test/page", "s",
                                      user_directed=True, policy=FAKE_POLICY)
        self.assertIn("hello world", text)

    def test_user_directed_still_surfaces_site_refusal(self):
        # A 403 from the site is NOT a robots decision; it must still be reported.
        import urllib.error

        def fake_fetch(url, policy, timeout=15, headers=None, egress=None, **kw):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

        with mock.patch.object(w, "_pinned_fetch", fake_fetch):
            with self.assertRaises(w.FetchBlocked) as ctx:
                w._default_url_raw("lightpanda", "http://h.test/page", "s",
                                   user_directed=True, policy=FAKE_POLICY)
        self.assertEqual(ctx.exception.code, "blocked_by_site")

    def test_execute_task_forwards_user_directed(self):
        seen = {}

        def driver(engine, url, session):
            seen["called"] = True
            return "<html><body>ok</body></html>"

        bw = w.BrowserWorker(driver_fn=driver)
        bw.execute_task("job-1", "http://h.test/x", user_directed=True)
        self.assertTrue(seen.get("called"))

    def test_user_directed_flag_does_not_leak_beyond_execute_task(self):
        # A leaked user_directed=True would make LATER automated fetches skip
        # robots.txt too — a policy bypass. The flag is scoped to its request.
        def driver(engine, url, session):
            return "<html><body>ok</body></html>"

        bw = w.BrowserWorker(driver_fn=driver)
        bw.execute_task("job-1", "http://h.test/x", user_directed=True)
        self.assertFalse(w.is_user_directed())


if __name__ == "__main__":
    unittest.main()
