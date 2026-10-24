"""Uniform engine adapters. Every CDP engine (Chromium family + Lightpanda) is driven the same
way: spawn the binary ourselves (so we own the pid for PSS) and attach Playwright over CDP."""
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.bench.procmem import pids_with_exe_prefix


@dataclass
class FetchResult:
    ok: bool
    ms: float
    html_len: int
    error: str = ""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def chromium_argv(exe: str, port: int, profile: str) -> List[str]:
    # shortcut: --no-sandbox on every Chromium-family target (Ubuntu AppArmor restricts unprivileged userns
    #   for extracted binaries); identical for all vendors so the comparison stays fair. Upgrade: sandboxed run.
    return [exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "--no-sandbox", "--disable-gpu", "about:blank"]


def lightpanda_argv(exe: str, port: int) -> List[str]:
    return [exe, "serve", "--host", "127.0.0.1", "--port", str(port)]


def _on_affine_thread(self, fn, *args, **kwargs):
    """Every Playwright call for one adapter runs on the SAME thread (sync API is thread-local)."""
    if not hasattr(self, "_affinity"):
        self._affinity = _SingleThreadExecutor()
    return self._affinity.submit(fn, *args, **kwargs)


class _SingleThreadExecutor:
    def __init__(self):
        self._q = __import__("queue").Queue()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self):
        while True:
            fn, args, kwargs, box = self._q.get()
            try:
                box["out"] = fn(*args, **kwargs)
            except Exception as exc:
                box["err"] = exc
            box["done"].set()

    def submit(self, fn, *args, **kwargs):
        box = {"done": threading.Event()}
        self._q.put((fn, args, kwargs, box))
        box["done"].wait()
        if "err" in box:
            raise box["err"]
        return box.get("out")


def _in_thread(fn, *args, **kwargs):
    """Playwright sync API is thread-local; a second session in an existing asyncio loop raises.
    Running each session in its own dedicated thread keeps adapters independent and reentrant."""
    box = {}

    def _run():
        try:
            box["out"] = fn(*args, **kwargs)
        except Exception as exc:
            box["err"] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join()
    if "err" in box:
        raise box["err"]
    return box["out"]


def _fetch(self, url: str, marker: str, timeout_s: float = 30.0) -> FetchResult:
    """Shared measurement code path for every adapter: goto, then poll content until marker shows."""
    return _on_affine_thread(self, self._fetch_impl, url, marker, timeout_s)


def _fetch_impl(self, url: str, marker: str, timeout_s: float = 30.0) -> FetchResult:
    t0 = time.perf_counter()
    ctx = None
    try:
        ctx = self._browser.new_context()
        page = ctx.new_page()
        page.goto(url, wait_until="load", timeout=timeout_s * 1000)
        deadline = time.monotonic() + timeout_s
        html = page.content()
        while marker not in html and time.monotonic() < deadline:
            time.sleep(self.POLL_S)
            html = page.content()
        return FetchResult(marker in html, (time.perf_counter() - t0) * 1000, len(html))
    except Exception as exc:  # engine crash/unsupported API counts as a failed fetch, not a harness error
        return FetchResult(False, (time.perf_counter() - t0) * 1000, 0, type(exc).__name__)
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass


class CdpAdapter:
    POLL_S = 0.02  # marker polling quantum; same for every engine (documented in methodology)
    fetch = _fetch
    _fetch_impl = _fetch_impl

    def __init__(self, target_id: str, argv_fn: Callable[[int, str], List[str]]) -> None:
        self.id, self._argv_fn = target_id, argv_fn
        self._proc: Optional[subprocess.Popen] = None
        self._pw = self._browser = None
        self._profile = ""

    def start(self) -> None:
        _on_affine_thread(self, self._start_impl)

    def _start_impl(self) -> None:
        port, self._profile = free_port(), tempfile.mkdtemp(prefix="bench-prof-")
        self._proc = subprocess.Popen(self._argv_fn(port, self._profile),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5).read()
                break
            except Exception:
                time.sleep(0.02)
        else:
            raise RuntimeError(f"{self.id}: CDP endpoint did not come up")
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

    def root_pids(self) -> List[int]:
        return [self._proc.pid] if self._proc else []

    def stop(self) -> None:
        _on_affine_thread(self, self._stop_impl)

    def _stop_impl(self) -> None:
        for closer in (lambda: self._browser.close(), lambda: self._pw.stop()):
            try:
                closer()
            except Exception:
                pass
        if self._proc:
            self._proc.kill()
            self._proc.wait()
        shutil.rmtree(self._profile, ignore_errors=True)


class PlaywrightAdapter:
    """Gecko / WebKit: Playwright launches its own patched builds (disclosed in every report).
    # shortcut: patched Firefox/WebKit, not vendor Firefox/Safari. Upgrade: Firefox via WebDriver BiDi."""
    POLL_S = CdpAdapter.POLL_S
    fetch = _fetch
    _fetch_impl = _fetch_impl

    def __init__(self, target_id: str, browser_name: str, exe_prefix: str) -> None:
        self.id, self._name, self._prefix = target_id, browser_name, exe_prefix
        self._pw = self._browser = None

    def start(self) -> None:
        _on_affine_thread(self, self._start_impl)

    def _start_impl(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = getattr(self._pw, self._name).launch(headless=True)

    def root_pids(self) -> List[int]:
        return pids_with_exe_prefix(self._prefix)

    def stop(self) -> None:
        _on_affine_thread(self, self._stop_impl)

    def _stop_impl(self) -> None:
        for closer in (lambda: self._browser.close(), lambda: self._pw.stop()):
            try:
                closer()
            except Exception:
                pass
