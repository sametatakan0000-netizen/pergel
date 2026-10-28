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
import subprocess
import tempfile
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from .extension_host import ExtensionHost  # noqa: F401 (type only)
from .adblock_session import AdblockBundle, build_injection
from .cdp_bridge import CDPBridge, _action_of, _rule_id_of, decide_cdp_response

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


class AdblockBrowserSession:
    """One enforced Chromium session; async context manager."""

    def __init__(self, bundle: AdblockBundle, browser_path: Optional[str] = None,
                 extensions: Optional["ExtensionHost"] = None,
                 headless: bool = True, keep_open: bool = False,
                 on_blocked: Optional[Callable[[dict], None]] = None):
        self.bundle = bundle
        self._browser_path = browser_path or _chromium()
        self._headless = headless
        self._keep_open = keep_open
        self._on_blocked = on_blocked
        self._tmp = tempfile.mkdtemp()
        self._proc = None
        self._ws = None
        self._sid = None
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._pump: Optional[asyncio.Task] = None
        self._load_evt = asyncio.Event() if websockets else None
        # Extension rules join the ad-block network rules at enforcement time
        # via CompositeEngine, so both decide on every request.
        source = (bundle.network, extensions) if extensions is not None \
            else bundle.network
        self._bridge = CDPBridge(source, send=lambda m: None)

    # --- lifecycle -------------------------------------------------------
    def _build_command(self) -> list:
        """The Chromium argv for this session (headless flag honours ``headless``)."""
        cmd = [self._browser_path]
        if self._headless:
            cmd.append("--headless=new")
        cmd += ["--no-sandbox", "--disable-gpu",
                "--remote-debugging-port=0", "--user-data-dir=" + self._tmp,
                "about:blank"]
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
        return self

    async def __aexit__(self, *exc):
        if self._pump:
            self._pump.cancel()
        if self._ws:
            await self._ws.close()
        # keep_open: the user is still driving the window; closing is the caller's job
        if self._proc and not self._keep_open:
            self._proc.terminate()

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
        self._seq += 1
        mid = self._seq
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        msg = {"id": mid, "method": method, "params": params or {}}
        if self._sid:
            msg["sessionId"] = self._sid
        await self._ws.send(json.dumps(msg))
        return await fut

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
                        extensions: Optional["ExtensionHost"] = None):
    """Sync ``driver_fn(engine, url, session_name) -> raw_html`` for ``BrowserWorker``.

    Fetches the URL through one enforced Chromium session and returns the
    cleaned rendered HTML (enforcement-hidden nodes removed), so the worker's
    ``html_to_clean_markdown`` produces ad-free content.
    """

    def driver(engine: str, url: str, session_name: str) -> str:
        async def go():
            async with AdblockBrowserSession(bundle, browser_path,
                                             extensions=extensions) as sess:
                return await sess.fetch(url, host=None, timeout=30.0)

        body = asyncio.run(go())
        html = body.get("html", [""])
        return html[0] if isinstance(html, list) else html

    return driver
