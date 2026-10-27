"""Chromium pool: one persistent browser owned by a dedicated worker thread."""
import sys
import subprocess
import threading
import time
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


class _HangingPlaywright:
    """Fake whose navigation blocks until `release` is set (a truly hung engine)."""

    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        self._started = started
        self._release = release
        self.stopped = 0
        self.browser_killed = False
        # Real child process standing in for the chromium subprocess: killing it
        # in `kill()` is the observable leak-prevention behavior under test.
        self.child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )

    def start(self):
        return self

    def stop(self):
        self.stopped += 1

    @property
    def sync_playwright(self):
        return lambda: self

    @property
    def chromium(self):
        outer = self

        class _Page:
            def goto(self, url: str, **kw):
                outer._started.set()
                outer._release.wait(30)  # bounded so a broken test cannot hang the suite

            def content(self) -> str:
                return "<html>hung</html>"

        class _Browser:
            def is_connected(self) -> bool:
                return True

            def new_page(self, user_agent: str = "") -> "_Page":
                return _Page()

            def close(self):
                pass

            def kill(self):
                outer.browser_killed = True
                try:
                    outer.child.kill()
                    # Reap synchronously so poll() reflects death immediately.
                    outer.child.wait(timeout=5)
                except Exception:
                    pass

        class _Chromium:
            def launch(self, headless: bool):
                return _Browser()

        return _Chromium()


def _install_fake_playwright_factory(fakes):
    """One fake per pool generation: `sync_playwright()` pops the next fake."""
    it = iter(fakes)
    last = fakes[-1]

    def factory():
        try:
            return next(it)
        except StopIteration:
            return last

    module = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = factory
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

    def test_hung_worker_is_replaced_and_pool_recovers(self):
        started = threading.Event()
        release = threading.Event()
        hung = _HangingPlaywright(started, release)
        ok = _FakePlaywright()
        with _install_fake_playwright_factory([hung, ok]):
            with self.assertRaises(TimeoutError):
                self.ed.chromium_pool.fetch("https://hang.example/", "s1", timeout_s=0.5)
            self.assertTrue(started.wait(5), "hung worker never began navigation")
            out = self.ed.chromium_pool.fetch("https://b.example/", "s2", timeout_s=5)
        self.assertEqual(out, "<html>content-1</html>")
        self.assertEqual(ok.browser.launch_count, 1)
        release.set()  # hung worker wakes; must clean up ONLY its own generation
        deadline = time.time() + 5
        while hung.stopped == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(hung.stopped, 1)
        self.assertEqual(ok.stopped, 0)

    def test_navigation_timeout_still_reuses_live_worker(self):
        # Task-side TimeoutError is NOT a hung worker: the worker thread stays
        # healthy and the browser must not be recycled (covered above); this
        # guards the caller/task timeout distinction explicitly.
        fake = _FakePlaywright()
        with _install_fake_playwright(fake):
            with self.assertRaises(TimeoutError):
                self.ed.chromium_pool.fetch("https://timeout/", "s1", timeout_s=5)
            self.assertEqual(fake.browser.launch_count, 1)
            out = self.ed.chromium_pool.fetch("https://b.example/", "s2", timeout_s=5)
        self.assertEqual(out, "<html>content-1</html>")
        self.assertEqual(fake.browser.launch_count, 1)


    def test_hung_worker_abandon_kills_browser_subprocess(self):
        # Regression for the `# shortcut:` note: a never-waking worker used to
        # leak its chromium subprocess. abandon() must kill it immediately.
        started = threading.Event()
        release = threading.Event()
        hung = _HangingPlaywright(started, release)
        with _install_fake_playwright_factory([hung]):
            with self.assertRaises(TimeoutError):
                self.ed.chromium_pool.fetch("https://hang.example/", "s1", timeout_s=0.5)
        # abandon() must have killed the fake's child process (the chromium stand-in)
        deadline = time.time() + 5
        while hung.child.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        self.assertIsNotNone(hung.child.poll(), "abandon() must kill the hung browser subprocess")
        release.set()
        deadline = time.time() + 5
        while hung.stopped == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(hung.stopped, 1)
        try:
            hung.child.kill()
        except Exception:
            pass

    def test_shutdown_pools_reaps_abandoned_subprocess(self):
        # A hung generation left behind (even after pool reset) must not leak.
        started = threading.Event()
        release = threading.Event()
        hung = _HangingPlaywright(started, release)
        with _install_fake_playwright_factory([hung]):
            with self.assertRaises(TimeoutError):
                self.ed.chromium_pool.fetch("https://hang.example/", "s1", timeout_s=0.5)
            self.ed.shutdown_pools()
        self.assertTrue(hung.child.poll() is not None, "shutdown must reap the abandoned subprocess")
        release.set()
        deadline = time.time() + 5
        while hung.stopped == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(hung.stopped, 1)
        try:
            hung.child.kill()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
