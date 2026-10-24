"""Chromium pool: one persistent browser owned by a dedicated worker thread."""
import sys
import types
import unittest
from unittest import mock


class _FakePage:
    def __init__(self, content: str) -> None:
        self._content = content
        self.goto_calls: list = []

    def goto(self, url: str, **kw):
        self.goto_calls.append(url)
        if "timeout" in url:
            raise TimeoutError("navigation timeout")

    def content(self) -> str:
        return self._content


class _FakeBrowser:
    def __init__(self) -> None:
        self.launch_count = 0
        self.connected = True
        self.pages: list = []

    def is_connected(self) -> bool:
        return self.connected

    def new_page(self, user_agent: str = "") -> _FakePage:
        page = _FakePage(f"<html>content-{self.launch_count}</html>")
        self.pages.append(page)
        return page

    def close(self):
        self.connected = False


class _FakePlaywright:
    def __init__(self) -> None:
        self.browser = _FakeBrowser()
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1
        return self

    def stop(self):
        self.stopped += 1

    @property
    def sync_playwright(self):
        return lambda: self

    @property
    def chromium(self):
        outer = self

        class _Chromium:
            def launch(self, headless: bool):
                outer.browser.launch_count += 1
                return outer.browser

        return _Chromium()


def _install_fake_playwright(fake: _FakePlaywright):
    module = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: fake
    module.sync_api = sync_api
    return mock.patch.dict(sys.modules, {"playwright": module, "playwright.sync_api": sync_api})


class ChromiumPoolTests(unittest.TestCase):
    def setUp(self):
        import importlib
        import src.browser_engine.engine_drivers as ed
        self.ed = importlib.reload(ed)  # fresh pool per test

    def test_browser_is_launched_once_and_reused(self):
        fake = _FakePlaywright()
        with _install_fake_playwright(fake):
            out1 = self.ed.chromium_pool.fetch("https://a.example/", "s1")
            out2 = self.ed.chromium_pool.fetch("https://b.example/", "s2")
        self.assertEqual(out1, "<html>content-1</html>")
        self.assertEqual(out2, "<html>content-1</html>")
        self.assertEqual(fake.browser.launch_count, 1)
        self.assertEqual(len(fake.browser.pages), 2)
        self.assertEqual(fake.started, 1)
        self.assertEqual(fake.stopped, 0)

    def test_dead_browser_is_relaunched_on_next_fetch(self):
        fake = _FakePlaywright()
        with _install_fake_playwright(fake):
            self.ed.chromium_pool.fetch("https://a.example/", "s1")
            fake.browser.connected = False  # simulate engine crash
            out = self.ed.chromium_pool.fetch("https://b.example/", "s2")
        self.assertEqual(out, "<html>content-2</html>")
        self.assertEqual(fake.browser.launch_count, 2)

    def test_navigation_timeout_does_not_recycle_browser(self):
        fake = _FakePlaywright()
        with _install_fake_playwright(fake):
            with self.assertRaises(TimeoutError):
                self.ed.chromium_pool.fetch("https://timeout/", "s1")
            self.assertEqual(fake.browser.launch_count, 1)
            out = self.ed.chromium_pool.fetch("https://b.example/", "s2")
        self.assertEqual(out, "<html>content-1</html>")

    def test_pool_shutdown_stops_playwright(self):
        fake = _FakePlaywright()
        with _install_fake_playwright(fake):
            self.ed.chromium_pool.fetch("https://a.example/", "s1")
            self.ed.shutdown_pools()
        self.assertEqual(fake.stopped, 1)

    def test_missing_playwright_raises_engine_unavailable(self):
        with mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
            with self.assertRaises(self.ed.EngineUnavailable):
                self.ed.chromium_pool.fetch("https://a.example/", "s1")


if __name__ == "__main__":
    unittest.main()
