"""Gerçek tarayıcı motorları: tier-1 lightpanda (Zig/V8, `fetch --dump html`) ve
tier-2 Chromium (Playwright headless shell). tier-3 camofox bilinçli olarak ertelendi
(stealth, hukuki/ToS riski) ve düz-HTTP yedeğine düşer.

Politika değişmezleri: robots.txt HER motordan ÖNCE kontrol edilir; politika bloğu
FetchBlocked fırlatır ve eskalasyon asla bypass edemez. 2 MB gövde sınırı korunur.
"""
import atexit
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from src.browser_engine.worker import (
    MAX_BODY_BYTES,
    FetchBlocked,
    _allowed_by_robots,
    _default_url_driver,
)

LIGHTPANDA_TIMEOUT_S = 30
CHROMIUM_TIMEOUT_S = 30
_UA_BASE = "HermesBrowserFarm/1.0"


def _egress_enforce() -> bool:
    """Egress enforcement opt-in (netns + proxy). Default OFF so plain use
    stays simple; production sets ORACLE_EGRESS_ENFORCE=1 to activate."""
    return os.environ.get("ORACLE_EGRESS_ENFORCE", "").strip().lower() in ("1", "true", "yes")


def _chromium_launch_args() -> list:
    """Chromium args pinning egress to the proxy; [] when enforcement is off.

    When on, the engine is also expected to run inside the netns whose only
    route is the proxy (see netns.plan_netns) — these flags are defense in
    depth for Chromium's raw-DNS paths.
    """
    if not _egress_enforce():
        return []
    _ensure_egress_guard()
    host = os.environ.get("ORACLE_EGRESS_PROXY_HOST", "10.255.255.1")
    port = int(os.environ.get("ORACLE_EGRESS_PROXY_PORT", "8899"))
    from src.browser_engine.netns import chromium_proxy_args
    return chromium_proxy_args(proxy_host=host, proxy_port=port)


def _ensure_egress_guard() -> None:
    """Start the live egress proxy once per process (serving-path wiring)."""
    from src.browser_engine import egress_guard
    if egress_guard._current_guard is None:
        egress_guard.start_egress_guard(
            use_netns=os.environ.get("ORACLE_EGRESS_NETNS", "1") == "1",
            proxy_port=int(os.environ.get("ORACLE_EGRESS_PROXY_PORT", "8899")))


class EngineUnavailable(RuntimeError):
    """Engine missing or failed -> worker escalates to the next tier."""


def _lightpanda_bin() -> Optional[str]:
    cand = (os.environ.get("LIGHTPANDA_BIN")
            or shutil.which("lightpanda")
            or os.path.expanduser("~/.local/bin/lightpanda"))
    return cand if cand and os.path.exists(cand) else None


def _lightpanda_html(url: str, session_name: str) -> str:
    binary = _lightpanda_bin()
    if not binary:
        raise EngineUnavailable("lightpanda binary not installed")
    proc = subprocess.run(
        [binary, "fetch", url, "--dump", "html"],
        capture_output=True, timeout=LIGHTPANDA_TIMEOUT_S,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0 or not out.strip():
        raise EngineUnavailable(f"lightpanda fetch failed (rc={proc.returncode})")
    return out[:MAX_BODY_BYTES]


class _ChromiumPool:
    """Kalıcı headless Chromium; tek işçi thread'i sahiplenir, her fetch yeni page açar.
    sync Playwright oluşturan thread'e bağlı olduğu için havuz, tüm çağrıları tek
    ThreadPoolExecutor işçisine yollar (ThreadingHTTPServer thread'leri arası güvenli)."""

    def __init__(self) -> None:
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chromium-pool")
        self._pw = None
        self._browser = None

    def fetch(self, url: str, user_agent: str) -> str:
        future = self._exec.submit(self._fetch_on_worker, url, user_agent)
        # shortcut: a hung navigation blocks the single worker; result timeout only unblocks the caller
        return future.result(timeout=CHROMIUM_TIMEOUT_S + 30)

    def _fetch_on_worker(self, url: str, user_agent: str) -> str:
        try:
            return self._fetch_once(url, user_agent)
        finally:
            browser = self._browser
            if browser is not None and hasattr(browser, "is_connected") and not browser.is_connected():
                self._reset()  # dead engine -> fresh launch on next fetch

    def _fetch_once(self, url: str, user_agent: str) -> str:
        browser = self._browser
        if browser is not None and hasattr(browser, "is_connected") and not browser.is_connected():
            self._reset()  # engine died between fetches -> fresh launch
        if self._pw is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:  # shortcut: optional dep like trafilatura
                raise EngineUnavailable("playwright not installed") from exc
            self._pw = sync_playwright().start()
            launch_args = _chromium_launch_args()
            self._browser = (self._pw.chromium.launch(headless=True, args=launch_args)
                             if launch_args else self._pw.chromium.launch(headless=True))
        page = self._browser.new_page(user_agent=user_agent)
        page.goto(url, timeout=CHROMIUM_TIMEOUT_S * 1000, wait_until="load")
        return page.content()[:MAX_BODY_BYTES]

    def _reset(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._browser = None


chromium_pool = _ChromiumPool()


def shutdown_pools() -> None:
    """Stop pooled engines (atexit / tests)."""
    chromium_pool._reset()


atexit.register(shutdown_pools)


def _chromium_html(url: str, session_name: str) -> str:
    return chromium_pool.fetch(url, user_agent=f"{_UA_BASE} (chromium-browser-use; {session_name})")


def engine_driver(engine: str, url: str, session_name: str) -> str:
    """`BrowserWorker.driver_fn` contract: raw HTML string, exception on failure."""
    if not _allowed_by_robots(url, "HermesBrowserFarm"):
        raise FetchBlocked(f"robots.txt disallows {url}")
    if engine == "lightpanda":
        return _lightpanda_html(url, session_name)
    if engine == "chromium-browser-use":
        return _chromium_html(url, session_name)
    # shortcut: camofox deferred (stealth opt-in + legal review), plain-HTTP until then
    return _default_url_driver(engine, url, session_name)
