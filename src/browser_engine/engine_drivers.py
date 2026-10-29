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

from src.browser_engine.egress_proxy import EgressPolicy
from src.browser_engine.worker import (
    is_user_directed,
    MAX_BODY_BYTES,
    FetchBlocked,
    _allowed_by_robots,
    _check_hop,
    _default_url_driver,
    _egress_policy,
)

LIGHTPANDA_TIMEOUT_S = 30
CHROMIUM_TIMEOUT_S = 30
_UA_BASE = "HermesBrowserFarm/1.0"


def _egress_enforce() -> bool:
    """Egress enforcement opt-in (netns + proxy). Default OFF so plain use
    stays simple; production sets ORACLE_EGRESS_ENFORCE=1 to activate."""
    return os.environ.get("ORACLE_EGRESS_ENFORCE", "").strip().lower() in ("1", "true", "yes")


def _chromium_launch_args(need_relay=None) -> list:
    """Chromium args pinning egress to the validating relay; [] when direct.

    ``need_relay``: a bool, an ``EgressPolicy`` (``_relay_required`` decides),
    or ``None`` for the legacy env semantics (relay under
    ORACLE_EGRESS_ENFORCE=1 only). Serving paths pass the request's policy so
    strict requests are relay-pinned even without the global mode. When on, the
    engine may also run inside the netns (see netns.plan_netns) — the proxy
    flags are defense in depth for Chromium's raw-DNS paths.
    """
    if not _as_need_relay(need_relay):
        return []
    guard = _ensure_egress_guard()
    host, port = _relay_endpoint(guard)
    from src.browser_engine.netns import chromium_proxy_args
    args = chromium_proxy_args(proxy_host=host, proxy_port=port)
    if not _netns_enabled():
        # Without netns the relay is the ONLY enforcement: Chromium implicitly
        # bypasses proxies for loopback literals, so a redirect to
        # http://127.0.0.1/ would skip the relay. <-loopback> disables that.
        args.append("--proxy-bypass-list=<-loopback>")
    return args


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


def _ensure_egress_guard(*, use_netns: Optional[bool] = None):
    """Start the live egress proxy once per process and return the guard.

    ``use_netns`` defaults to ``_netns_enabled()``: on under enforcement, off for
    request-driven strict relaying (which must not require sudo).
    """
    from src.browser_engine import egress_guard
    # Reuse a guard that is already live in this process (e.g. started by the
    # caller) instead of binding the same port a second time.
    if egress_guard._current_guard is None:
        if use_netns is None:
            use_netns = _netns_enabled()
        egress_guard.start_egress_guard(
            use_netns=use_netns,
            proxy_port=int(os.environ.get("ORACLE_EGRESS_PROXY_PORT", "8899")))
    return egress_guard._current_guard


def _netns_enabled() -> bool:
    """netns isolation on? Explicit ORACLE_EGRESS_NETNS wins; default is on under
    enforcement, off for request-driven relay (no sudo in serving threads)."""
    return os.environ.get(
        "ORACLE_EGRESS_NETNS", "1" if _egress_enforce() else "0") == "1"


def _relay_endpoint(guard) -> tuple:
    """Host:port the engines must proxy to: env override, else the guard's own
    bind (netns 10.255.255.1 vs loopback), else the legacy netns default."""
    host = os.environ.get("ORACLE_EGRESS_PROXY_HOST")
    port = os.environ.get("ORACLE_EGRESS_PROXY_PORT")
    if guard is not None:
        listen = getattr(guard, "listen_host", None)
        if not host and isinstance(listen, str) and listen:
            host = listen
        gport = getattr(guard, "port", None)
        if not port and isinstance(gport, int):
            port = str(gport)
    return host or "10.255.255.1", int(port or 8899)


def _relay_required(policy: Optional[EgressPolicy] = None) -> bool:
    """Must this request's engine traffic traverse the validating EgressRelay?

    True under global enforcement, and for strict requests (no
    ``private_targets_allowed()`` opt-in): sub-process engines resolve DNS and
    follow redirects themselves, so only the relay validates every hop and pins
    dial-outs to the validated IP. Private-allowed dev fetches stay direct —
    the relay's strict policy would deny them.
    """
    if _egress_enforce():
        return True
    if policy is None:
        policy = _egress_policy()
    return not policy.allows_private


class EngineUnavailable(RuntimeError):
    """Engine missing or failed -> worker escalates to the next tier."""


def _lightpanda_bin() -> Optional[str]:
    cand = (os.environ.get("LIGHTPANDA_BIN")
            or shutil.which("lightpanda")
            or os.path.expanduser("~/.local/bin/lightpanda"))
    return cand if cand and os.path.exists(cand) else None


def _as_need_relay(need_relay) -> bool:
    """Normalize the relay-routing decision.

    Accepts a bool, an ``EgressPolicy`` (strict -> relay, private-allowed ->
    direct), or ``None`` (legacy env semantics). Sub-process engines follow
    redirects themselves, so a strict request must traverse the validating
    relay to keep the SSRF guarantees on every hop.
    """
    if need_relay is None:
        return _egress_enforce()
    if isinstance(need_relay, EgressPolicy):
        return _relay_required(need_relay)
    return bool(need_relay)


def _lightpanda_proxy_args(need_relay=None) -> list:
    """Lightpanda argv routing egress through the relay; [] when direct.

    Lightpanda follows redirects itself (no CDP interception), so when routing
    is required its traffic must traverse the validating EgressRelay — every
    request, including redirect hops, is re-checked there (parity with
    _chromium_launch_args). ``need_relay`` may be a bool, an ``EgressPolicy``
    (``_relay_required`` decides), or ``None`` for the legacy env semantics.
    """
    if not _as_need_relay(need_relay):
        return []
    guard = _ensure_egress_guard()
    host, port = _relay_endpoint(guard)
    return ["--http-proxy", f"http://{host}:{port}"]


def _lightpanda_html(url: str, session_name: str,
                     need_relay: Optional[bool] = None) -> str:
    binary = _lightpanda_bin()
    if not binary:
        raise EngineUnavailable("lightpanda binary not installed")
    proc = subprocess.run(
        [binary, "fetch", url, "--dump", "html", *_lightpanda_proxy_args(need_relay)],
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
        # Relay routing is a LAUNCH flag: record what this generation was
        # launched with so a mode change can drop and relaunch it.
        self._relay_mode: Optional[bool] = None

    def fetch(self, url: str, user_agent: str, timeout_s: float,
              need_relay: Optional[bool] = None) -> str:
        future = self._exec.submit(self._fetch_on_worker, url, user_agent, need_relay)
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

    def _fetch_on_worker(self, url: str, user_agent: str,
                         need_relay: Optional[bool] = None) -> str:
        try:
            return self._fetch_once(url, user_agent, need_relay)
        finally:
            browser = self._browser
            if self._abandoned or (browser is not None and hasattr(browser, "is_connected") and not browser.is_connected()):
                self._reset()  # dead/abandoned generation -> close own engine only

    def _fetch_once(self, url: str, user_agent: str,
                    need_relay: Optional[bool] = None) -> str:
        wanted = _egress_enforce() if need_relay is None else bool(need_relay)
        browser = self._browser
        if browser is not None and hasattr(browser, "is_connected") and not browser.is_connected():
            self._reset()  # engine died between fetches -> fresh launch
        if self._pw is not None and self._relay_mode != wanted:
            self._reset()  # relay routing is a launch flag -> fresh generation
        if self._pw is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:  # shortcut: optional dep like trafilatura
                raise EngineUnavailable("playwright not installed") from exc
            self._pw = sync_playwright().start()
            self._relay_mode = wanted
            launch_args = _chromium_launch_args(wanted)
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
        self._relay_mode = None
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

    def fetch(self, url: str, user_agent: str, timeout_s: Optional[float] = None,
              need_relay: Optional[bool] = None) -> str:
        if timeout_s is None:
            timeout_s = CHROMIUM_TIMEOUT_S + 30
        with self._lock:
            worker = self._worker
        try:
            return worker.fetch(url, user_agent, timeout_s, need_relay)
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


def _chromium_html(url: str, session_name: str,
                   need_relay: Optional[bool] = None) -> str:
    return chromium_pool.fetch(
        url, user_agent=f"{_UA_BASE} (chromium-browser-use; {session_name})",
        need_relay=need_relay)


def engine_driver(engine: str, url: str, session_name: str,
                  user_directed: Optional[bool] = None,
                  policy: Optional[EgressPolicy] = None) -> str:
    """`BrowserWorker.driver_fn` contract: raw HTML string, exception on failure.

    Honors robots.txt for automated crawl. ``user_directed=True`` (or the
    worker's contextvar) marks an explicit single-URL user request: robots is
    then skipped and reported as a note, while site refusals still surface.

    ``policy`` overrides the egress policy for the SSRF pre-flight (tests /
    custom deployments); default is the live policy, which honors
    ``private_targets_allowed()``.
    """
    if user_directed is None:
        user_directed = is_user_directed()
    policy = policy or _egress_policy()
    # Sub-process engines resolve DNS and follow redirects themselves: route
    # strict requests through the validating EgressRelay (every hop re-checked,
    # dial-outs pinned to the validated IP) — private_targets_allowed() dev
    # fetches stay direct (the relay's strict policy would deny them).
    # shortcut: direct dev fetches trust the engine's own resolve (narrow
    # rebinding window on private targets only); force the relay when exposing.
    need_relay = _relay_required(policy)
    egress = None
    if engine in ("lightpanda", "chromium-browser-use"):
        # SSRF-pre-flight the target with the plain-HTTP fallback's rules.
        egress = _check_hop(url, policy)
    if not user_directed and not _allowed_by_robots(url, "HermesBrowserFarm",
                                                    egress=egress, policy=policy):
        raise FetchBlocked(f"robots.txt disallows {url}", code="robots_disallowed")
    if engine == "lightpanda":
        return _lightpanda_html(url, session_name, need_relay=need_relay)
    if engine == "chromium-browser-use":
        return _chromium_html(url, session_name, need_relay=need_relay)
    # shortcut: camofox deferred (stealth opt-in + legal review), plain-HTTP until then
    return _default_url_driver(engine, url, session_name, policy=policy)
