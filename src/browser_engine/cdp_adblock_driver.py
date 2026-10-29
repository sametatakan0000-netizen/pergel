"""CDP-backed fetch/browse driver wired to the adblock enforcement engine.

This is the product's real fetch seam. ``AdblockBrowserSession`` owns a
headless Chromium and a live CDP connection, and it enforces every layer before
the page is read:

- ``Fetch.enable`` -> every ``Fetch.requestPaused`` runs the network rule
  engine (block / allow / redirect / modifyHeaders) via ``decide_cdp_response``.
- ``Page.addScriptToEvaluateOnNewDocument`` -> the combined cosmetic CSS +
  scriptlets + procedural injection runs at ``document-start``, before render.

The extracted text is therefore the *enforced* page: hidden/removed ads do not
appear in ``innerText``. Returns bodies matching the worker's driver contract
(scrape body for ``fetch``, browse body with ``markdown`` for ``browse``).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from .extension_host import ExtensionHost  # noqa: F401 (type only)
from .adblock_session import AdblockBundle, build_injection
from .cdp_bridge import CDPBridge, _action_of, _rule_id_of, decide_cdp_response
from .egress_proxy import EgressDenied, EgressPolicy

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None


def _chromium() -> Optional[str]:
    import os
    import shutil
    for cand in (
        os.path.expanduser("~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome"),
        os.path.expanduser("~/.hermes/tools/chromium-1208/chrome-linux64/chrome"),
    ):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    for name in ("chromium", "google-chrome", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def browser_base_args(headless: bool = True) -> list:
    """Flags every launch needs. ``--no-sandbox`` only as root: the desktop
    user runs with the real sandbox (AppArmor userns profile).

    ``--disable-gpu`` is a headless-CI crutch ONLY: on a real desktop it
    forces software compositing and makes scrolling/navigation visibly
    laggy, so a visible Pergel window must get the GPU.
    """
    args = ["--remote-debugging-port=0"]
    if headless:
        args.insert(0, "--disable-gpu")
    if os.geteuid() == 0:
        args.insert(0, "--no-sandbox")
    # Anti-detection: hide automation markers so sites like Google
    # don't block the browser as "insecure" (navigator.webdriver etc.)
    args.append("--disable-blink-features=AutomationControlled")
    return args


def make_ssrf_guard(policy_factory: Optional[Callable[[], Any]] = None
                    ) -> Callable[[str], bool]:
    """Build the CDPBridge ``ssrf_guard`` bound to the request's egress policy.

    True marks an SSRF-risk target: a private/loopback literal or a host that
    resolves private (fail-closed on unresolvable). Non-network schemes
    (data:, blob:, chrome-extension:, about:) are not SSRF-able hops and pass —
    blocking them would break extension and startup resources. ``policy_factory``
    defaults to the live per-request policy (``_egress_policy()``), so
    ``private_targets_allowed()`` fetches are honoured. shortcut: the guard
    resolves per request (same as the pre-flight); cache if profiling shows cost.
    """
    def _guard(url: str) -> bool:
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False  # non-network scheme: not an SSRF-able hop
        from src.browser_engine.egress_proxy import EgressAddressError, EgressDenied
        from src.browser_engine.worker import _egress_policy
        factory = policy_factory or _egress_policy
        try:
            factory().check_url(url)
            return False
        except (EgressDenied, EgressAddressError):
            return True
        except Exception:
            return True  # fail closed on unexpected guard errors
    return _guard


class AdblockBrowserSession:
    """One enforced Chromium session; async context manager."""

    def __init__(self, bundle: AdblockBundle, browser_path: Optional[str] = None,
                 extensions: Optional["ExtensionHost"] = None,
                 headless: bool = True, keep_open: bool = False,
                 on_blocked: Optional[Callable[[dict], None]] = None,
                 user_data_dir: Optional[str] = None,
                 start_url: str = "about:blank",
                 extra_args: Optional[list] = None,
                 ssrf_guard: Optional[Callable[[str], bool]] = None):
        self.bundle = bundle
        self._browser_path = browser_path or _chromium()
        self._headless = headless
        self._keep_open = keep_open
        self._on_blocked = on_blocked
        self._start_url = start_url
        self._extra_args = list(extra_args or [])
        self._tmp = user_data_dir or tempfile.mkdtemp()
        self._proc = None
        self._ws = None
        self._sid = None
        # targetId -> enforcement sessionId, one per PAGE target (every tab)
        self.page_sessions: dict = {}
        self._arm_tasks: set = set()
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._pump: Optional[asyncio.Task] = None
        self._load_evt = asyncio.Event() if websockets else None
        # Extension rules join the ad-block network rules at enforcement time
        # via CompositeEngine, so both decide on every request.
        source = (bundle.network, extensions) if extensions is not None \
            else bundle.network
        self._bridge = CDPBridge(source, send=lambda m: None, ssrf_guard=ssrf_guard)

    # --- lifecycle -------------------------------------------------------
    def _build_command(self) -> list:
        """The Chromium argv for this session (headless flag honours ``headless``)."""
        cmd = [self._browser_path]
        if self._headless:
            cmd.append("--headless=new")
        cmd += browser_base_args(self._headless)
        cmd += ["--user-data-dir=" + self._tmp] + self._extra_args
        cmd.append(self._start_url)
        return cmd

    async def __aenter__(self) -> "AdblockBrowserSession":
        if websockets is None or self._browser_path is None:
            raise RuntimeError("websockets lib or chromium binary unavailable")
        self._proc = subprocess.Popen(
            self._build_command(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = self._wait_ws()
        self._ws = await websockets.connect(ws_url, max_size=2**24)
        self._pump = asyncio.create_task(self._run_pump())
        tg = await self._call("Target.getTargets")
        page = [t for t in tg["result"]["targetInfos"] if t["type"] == "page"][-1]
        sess = await self._call("Target.attachToTarget",
                                {"targetId": page["targetId"], "flatten": True})
        self._sid = sess["result"]["sessionId"]
        await self._call("Fetch.enable")
        await self._call("Page.enable")
        await self._call("Runtime.enable")
        # Standard Chrome UA (Playwright's default has automation tokens
        # that Google rejects at login). CDP is more reliable than the
        # --user-agent flag which can break extension loading.
        try:
            await self._call("Network.enable")
            await self._call("Network.setUserAgentOverride", {
                "userAgent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
                "acceptLanguage": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "platform": "Linux x86_64"})
        except Exception:
            pass  # non-fatal
        # Anti-detection: override navigator.webdriver so sites don't
        # identify us as an automated browser (Google blocks on this).
        try:
            await self._call("Page.addScriptToEvaluateOnNewDocument", {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver',"
                    " {get: () => undefined});"
                    " window.chrome = window.chrome || {runtime: {}};"
                    " Object.defineProperty(navigator, 'plugins',"
                    " {get: () => [1, 2, 3, 4, 5]});"
                    " Object.defineProperty(navigator, 'languages',"
                    " {get: () => ['tr-TR', 'tr', 'en-US', 'en']};"
                )})
        except Exception:
            pass  # non-fatal: browser still works without anti-detection
        self.page_sessions[page["targetId"]] = self._sid
        # Every OTHER page target that already exists must be enforced too —
        # the startup attach race is exactly why the visible window once came
        # up with zero interception.
        for t in tg["result"]["targetInfos"]:
            if t["type"] != "page" or t["targetId"] == page["targetId"]:
                continue
            s = await self._call_root(
                "Target.attachToTarget",
                {"targetId": t["targetId"], "flatten": True})
            await self._arm_page(t["targetId"], s["result"]["sessionId"])
        # and every page target created later (new tabs) auto-attaches and is
        # armed by the pump's Target.attachedToTarget handler
        await self._call_root("Target.setAutoAttach", {
            "autoAttach": True, "waitForDebuggerOnStart": False,
            "flatten": True})
        return self

    async def _arm_page(self, target_id: str, sid: str) -> None:
        """Enable enforcement on one page target's session."""
        await self._call_on(sid, "Fetch.enable")
        await self._call_on(sid, "Page.enable")
        self.page_sessions[target_id] = sid

    async def wait_session_for(self, target_id: str,
                               timeout: float = 5.0) -> str:
        """Resolve when ``target_id``'s enforcement session is armed."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if target_id in self.page_sessions:
                return self.page_sessions[target_id]
            await asyncio.sleep(0.05)
        raise TimeoutError(f"no enforcement session for target {target_id}")

    async def __aexit__(self, *exc):
        if self._pump:
            self._pump.cancel()
        if self._ws:
            await self._ws.close()
        # keep_open: the user is still driving the window; closing is the caller's job
        if self._proc and not self._keep_open:
            self._proc.terminate()
            # shortcut: reap the child so chrome cannot linger as <defunct> and
            # GC ResourceWarnings; terminate() alone never waits. when to
            # upgrade: process-group teardown if engines start grandchildren.
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)

    def _wait_ws(self) -> str:
        import glob
        import time
        # --remote-debugging-port=0 writes the chosen port to DevToolsActivePort
        marker = self._tmp + "/DevToolsActivePort"
        for _ in range(120):
            try:
                with open(marker) as f:
                    port = int(f.readline().strip())
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                    return json.load(r)["webSocketDebuggerUrl"]
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("chromium devtools did not come up")

    # --- CDP plumbing ----------------------------------------------------
    @staticmethod
    def _resume_message(reply: dict, seq: int, event_sid=None,
                        session_sid=None) -> dict:
        """Build the CDP command that resumes or fails an intercepted request.

        ``Fetch.continueRequest``/``Fetch.failRequest`` are COMMANDS, so the
        message must carry a unique integer ``id`` (without it Chromium replies
        ``-32600 Message must have integer 'id' property`` and the paused
        request never resumes — navigation hangs). It must run under the SAME
        session the pause arrived on.
        """
        out = {"id": seq, "method": reply["method"], "params": reply["params"]}
        sid = event_sid or session_sid
        if sid:
            out["sessionId"] = sid
        return out

    async def _call(self, method, params=None):
        return await self._call_on(self._sid, method, params)

    async def _call_on(self, sid, method, params=None):
        self._seq += 1
        mid = self._seq
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        msg = {"id": mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await self._ws.send(json.dumps(msg))
        return await fut

    async def _call_root(self, method, params=None):
        """Browser-level command (no session): target management."""
        return await self._call_on(None, method, params)

    async def _send_on(self, sid, method, params=None):
        """Fire-and-forget command on one session (no reply tracking)."""
        self._seq += 1
        msg = {"id": self._seq, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await self._ws.send(json.dumps(msg))

    async def _run_pump(self):
        try:
            async for raw in self._ws:
                m = json.loads(raw)
                if "id" in m and m["id"] in self._pending:
                    self._pending.pop(m["id"]).set_result(m)
                    continue
                if m.get("method") == "Fetch.requestPaused":
                    # surface the decision to the observer first (live counter),
                    # then dispatch the real enforcement reply
                    self._notify_decision(m["params"])
                    reply = self._bridge.on_request_paused(m["params"])
                    self._seq += 1
                    await self._ws.send(json.dumps(self._resume_message(
                        reply, self._seq, event_sid=m.get("sessionId"),
                        session_sid=self._sid)))
                elif m.get("method") == "Target.attachedToTarget":
                    # a new tab (or startup-raced page) attached via auto-attach
                    p = m["params"]
                    if p.get("targetInfo", {}).get("type") == "page":
                        task = asyncio.get_event_loop().create_task(
                            self._arm_page(p["targetInfo"]["targetId"],
                                           p["sessionId"]))
                        self._arm_tasks.add(task)
                        task.add_done_callback(self._arm_tasks.discard)
                elif m.get("method") in ("Page.loadEventFired",
                                         "Page.domContentEventFired"):
                    self._load_evt.set()
        except asyncio.CancelledError:
            pass

    # --- driver API ------------------------------------------------------
    def _notify_decision(self, params: dict) -> dict:
        """Compute the enforcement decision for a paused request and surface it.

        Pure message construction via ``decide_cdp_response`` (no socket send),
        so the ``on_blocked`` callback can observe every request's fate — the
        live block counter the user sees while driving the real window.
        """
        msg = decide_cdp_response(
            self._bridge.engine,
            request_id=params.get("requestId", ""),
            url=params.get("request", {}).get("url", ""),
            resource_type=params.get("resourceType", "Other"),
            request_headers=dict(params.get("request", {}).get("headers", {})),
            ssrf_guard=self._bridge._ssrf_guard,
        )
        payload = {"action": _action_of(msg),
                   "rule_id": _rule_id_of(msg),
                   "url": params.get("request", {}).get("url", "")}
        if self._on_blocked is not None:
            self._on_blocked(payload)
        return payload

    async def fetch(self, url: str, host: Optional[str] = None, timeout: float = 30.0):
        """Fetch a URL through the engine; return a scrape body.

        ``innerText`` reflects enforcement: cosmetic/procedural-hidden elements
        and network-blocked subresources are absent.
        """
        html = await self._render(url, host, timeout)
        return {"html": [html], "text": [self._last_text], "title": self._last_title}

    async def browse(self, url: str, host: Optional[str] = None, timeout: float = 30.0):
        """Browse a URL through the engine; return a browse body with markdown."""
        await self._render(url, host, timeout)
        return {"markdown": [self._last_text], "title": self._last_title}

    async def _render(self, url: str, host: Optional[str], timeout: float) -> str:
        scope = host if host is not None else (urlparse(url).hostname or "")
        js = build_injection(self.bundle, scope)
        self._load_evt.clear()
        await self._call("Page.addScriptToEvaluateOnNewDocument", {"source": js})
        await self._call("Page.navigate", {"url": url})
        try:
            await asyncio.wait_for(self._load_evt.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        r = await self._call("Runtime.evaluate", {
            "expression":
                # Remove every enforcement-hidden node so the raw HTML the worker
                # canonicalizes carries no hidden ad content. Cosmetic hides via a
                # <style> rule, procedural hides inline. Two guards matter:
                #   (1) collect-then-remove — never un-hide a cosmetic element by
                #       deleting its stylesheet before it is measured;
                #   (2) never delete <style>/<script>/<head> nodes — <style> is
                #       display:none in the UA sheet and would otherwise be culled,
                #       stripping the cosmetic rules and re-exposing the ads.
                "(() => {"
                " const hide = []; const body = document.body;"
                " if (body) {"
                "   for (const el of body.querySelectorAll('*')) {"
                "     const t = el.tagName;"
                "     if (t === 'STYLE' || t === 'SCRIPT' || t === 'LINK'"
                "         || t === 'META') continue;"
                "     if (getComputedStyle(el).display === 'none') hide.push(el);"
                "   }"
                " }"
                " for (const el of hide) el.remove();"
                " return JSON.stringify({title: document.title,"
                "  text: (document.body ? document.body.innerText : ''),"
                "  html: (document.documentElement"
                "         ? document.documentElement.outerHTML : '')});"
                "})()",
            "returnByValue": True})
        data = json.loads(r["result"]["result"]["value"])
        self._last_title = data.get("title", "")
        self._last_text = data.get("text", "")
        return data.get("html", "")


def make_adblock_driver(bundle: AdblockBundle, browser_path: Optional[str] = None,
                        extensions: Optional["ExtensionHost"] = None,
                        ssrf_guard: Optional[Callable[[str], bool]] = None):
    """Sync ``driver_fn(engine, url, session_name) -> raw_html`` for ``BrowserWorker``.

    Fetches the URL through one enforced Chromium session and returns the
    cleaned rendered HTML (enforcement-hidden nodes removed), so the worker's
    ``html_to_clean_markdown`` produces ad-free content. The session also
    enforces the request's egress policy: an SSRF guard on every intercepted
    request (default ``make_ssrf_guard()``, honours ``private_targets_allowed()``)
    and — for strict requests — the validating EgressRelay for the browser's
    own egress (pins dial-outs to validated IPs, re-checks every redirect hop).
    """

    def driver(engine: str, url: str, session_name: str) -> str:
        # Lazy import: engine_drivers must stay importable without a cycle.
        from src.browser_engine.engine_drivers import (
            _chromium_launch_args, _relay_required, _egress_policy,
        )
        guard = ssrf_guard if ssrf_guard is not None else make_ssrf_guard()
        # Strict requests route the browser through the validating relay;
        # private_targets_allowed() dev fetches stay direct (relay would deny).
        # An explicit ssrf_guard means the caller owns the gate (custom policy,
        # e.g. a loopback fixture) — don't second-guess it with relay routing.
        # shortcut: explicit guard opts out of relay routing, add a policy
        # param to make_adblock_driver if a caller ever needs both.
        extra = ([] if ssrf_guard is not None
                 else _chromium_launch_args(_relay_required(_egress_policy())))

        async def go():
            async with AdblockBrowserSession(bundle, browser_path,
                                             extensions=extensions,
                                             extra_args=extra,
                                             ssrf_guard=guard) as sess:
                return await sess.fetch(url, host=None, timeout=30.0)

        body = asyncio.run(go())
        html = body.get("html", [""])
        return html[0] if isinstance(html, list) else html

    return driver
