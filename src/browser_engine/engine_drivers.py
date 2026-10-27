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
import threading
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from typing import Optional

from src.browser_engine.worker import (
    is_user_directed,
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


NETNS_NAME = "bf_engine"


def _netns_chromium_wrapper(chrome_bin: str, namespace: str = NETNS_NAME) -> str:
    """Write a tiny wrapper script that execs Chromium inside the netns.

    Contains no secrets. sudo is NOT invoked here: the netns is created
    beforehand by EgressGuard, and this wrapper only enters it, so the
    process runs as the caller user via a privileged `ip netns exec` that
    the host sudoers policy must allow for this exact command.
    """
    import tempfile
    body = (
        "#!/bin/sh\n"
        "# generated: run Chromium inside the egress namespace (fail-closed).\n"
        "# Uses the setuid helper bf_netns_exec (no sudo) so Playwright pipe\n"
        "# fds 3,4 survive; sudo-rs closes fd 3+ and breaks the pipe protocol.\n"
        "# The helper must be built static: after setresuid its own interpreter\n"
        "# is unavailable, and a dynamic binary dies before execv (execvp ENOENT).\n"
        f'exec /usr/local/bin/bf_netns_exec "{chrome_bin}" "$@"\n'
    )
    fd, path = tempfile.mkstemp(prefix="bf_chrome_", suffix=".sh")
    with os.fdopen(fd, "w") as fh:
        fh.write(body)
    os.chmod(path, 0o700)
    return path


def _launch_kwargs(chrome_bin: Optional[str] = None) -> dict:
    """Playwright launch kwargs. {} when enforcement is off (plain launch)."""
    if not _egress_enforce():
        return {}
    _ensure_egress_guard()
    args = _chromium_launch_args()
    kw: dict = {"args": args}
    if os.environ.get("ORACLE_EGRESS_NETNS", "1") == "1":
        if not chrome_bin:
            raise EngineUnavailable("netns enforcement needs an explicit chrome binary")
        kw["executable_path"] = _netns_chromium_wrapper(chrome_bin)
    return kw


def _ensure_egress_guard() -> None:
    """Start the live egress proxy once per process (serving-path wiring)."""
    from src.browser_engine import egress_guard
    # Reuse a guard that is already live in this process (e.g. started by the
    # caller) instead of binding the same port a second time.
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


class _WorkerHung(TimeoutError):
    """Caller-side hang: the worker thread never finished within the budget.

    Distinct from a task-raised TimeoutError (navigation timeout): a hung
    worker must be replaced, a timed-out navigation must not recycle the
    healthy engine."""


class _ChromiumWorker:
    """One executor thread owning one (playwright, browser) generation.

    A generation is abandoned as a unit on hang so a stuck Playwright call
    can never wedge the pool again."""

    def __init__(self) -> None:
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chromium-pool")
        self._pw = None
        self._browser = None
        self._abandoned = False

    def fetch(self, url: str, user_agent: str, timeout_s: float) -> str:
        future = self._exec.submit(self._fetch_on_worker, url, user_agent)
        done, _ = futures_wait([future], timeout=timeout_s)
        if not done:
            raise _WorkerHung(f"chromium worker hung >{timeout_s}s on {url}")
        return future.result()  # task exceptions (incl. TimeoutError) re-raise as-is

    def abandon(self) -> None:
        """Caller-side hang: drop this generation; it self-cleans when it wakes."""
        self._abandoned = True
        self._kill_browser()  # never leak a hung chromium subprocess
        self._exec.shutdown(wait=False)

    def _kill_browser(self) -> None:
        """Force-kill the engine subprocess even when the worker is wedged."""
        br = self._browser
        self._browser = None
        if br is None:
            return
        # Playwright's Browser.close() can block on a wedged connection; kill()
        # is the hard stop. Fall back to close() when the driver has no kill().
        try:
            kill = getattr(br, "kill", None)
            if callable(kill):
                kill()
                return
        except Exception:
            return
        try:
            br.close()
        except Exception:
            pass

    def _fetch_on_worker(self, url: str, user_agent: str) -> str:
        try:
            return self._fetch_once(url, user_agent)
        finally:
            browser = self._browser
            if self._abandoned or (browser is not None and hasattr(browser, "is_connected") and not browser.is_connected()):
                self._reset()  # dead/abandoned generation -> close own engine only

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


class _ChromiumPool:
    """Kalıcı headless Chromium; tek işçi thread'i sahiplenir, her fetch yeni page açar.
    sync Playwright oluşturan thread'e bağlı olduğu için havuz, tüm çağrıları tek
    ThreadPoolExecutor işçisine yollar (ThreadingHTTPServer thread'leri arası güvenli).
    Takılan bir işçi kuşak değiştirilerek kenara atılır: havuz bir daha kalıcı kilitlenmez."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker = _ChromiumWorker()
        self._abandoned: list[_ChromiumWorker] = []

    def fetch(self, url: str, user_agent: str, timeout_s: Optional[float] = None) -> str:
        if timeout_s is None:
            timeout_s = CHROMIUM_TIMEOUT_S + 30
        with self._lock:
            worker = self._worker
        try:
            return worker.fetch(url, user_agent, timeout_s)
        except _WorkerHung:
            with self._lock:
                if self._worker is worker:
                    worker.abandon()
                    self._abandoned.append(worker)  # reaped by reap()/shutdown
                    self._worker = _ChromiumWorker()  # fresh generation for next fetch
            raise

    def reap(self) -> None:
        """Force-kill any abandoned (hung) workers' engine subprocesses."""
        with self._lock:
            pending, self._abandoned = self._abandoned, []
        for w in pending:
            w._kill_browser()

    def _reset(self) -> None:
        self.reap()  # never leak a hung generation's chromium subprocess
        with self._lock:
            self._worker._reset()


chromium_pool = _ChromiumPool()


def shutdown_pools() -> None:
    """Stop pooled engines (atexit / tests)."""
    chromium_pool._reset()


atexit.register(shutdown_pools)


def _chromium_html(url: str, session_name: str) -> str:
    return chromium_pool.fetch(url, user_agent=f"{_UA_BASE} (chromium-browser-use; {session_name})")


def engine_driver(engine: str, url: str, session_name: str,
                  user_directed: Optional[bool] = None) -> str:
    """`BrowserWorker.driver_fn` contract: raw HTML string, exception on failure.

    Honors robots.txt for automated crawl. ``user_directed=True`` (or the
    worker's contextvar) marks an explicit single-URL user request: robots is
    then skipped and reported as a note, while site refusals still surface.
    """
    if user_directed is None:
        user_directed = is_user_directed()
    if not user_directed and not _allowed_by_robots(url, "HermesBrowserFarm"):
        raise FetchBlocked(f"robots.txt disallows {url}", code="robots_disallowed")
    if engine == "lightpanda":
        return _lightpanda_html(url, session_name)
    if engine == "chromium-browser-use":
        return _chromium_html(url, session_name)
    # shortcut: camofox deferred (stealth opt-in + legal review), plain-HTTP until then
    return _default_url_driver(engine, url, session_name)
