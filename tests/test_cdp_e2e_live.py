"""End-to-end smoke test: a real Chromium talks to the CDP bridge.

Starts headless Chromium with remote debugging, enables Fetch, and drives
Fetch.requestPaused through decide_cdp_response. Skips cleanly when no
Chromium/Playwright binary is available, so the suite stays hermetic.

Wiring test only — the hard correctness lives in test_cdp_bridge.py and
test_rule_engine.py. This proves the transport actually works against a
browser, not just against dicts.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request

try:
    import websockets
    import asyncio
except ImportError:  # pragma: no cover
    websockets = None

from src.browser_engine.cdp_bridge import CDPBridge, decide_cdp_response
from src.browser_engine.rule_engine import compile_rules


def _find_chromium():
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


class TestLiveCDPBridge(unittest.TestCase):
    """Real browser, real WebSocket — the whole vertical slice."""

    @classmethod
    def setUpClass(cls):
        cls.chromium = _find_chromium()
        if cls.chromium is None or websockets is None:
            raise unittest.SkipTest("no chromium binary or websockets lib")
        cls.tmp = tempfile.mkdtemp(prefix="cdp-e2e-")
        cls.port = 9333
        cls.proc = subprocess.Popen(
            [cls.chromium, "--headless=new", "--no-sandbox",
             f"--remote-debugging-port={cls.port}", "--user-data-dir=" + cls.tmp,
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.ws_url = None
        for _ in range(80):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{cls.port}/json/version", timeout=1) as r:
                    cls.ws_url = json.load(r)["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.25)
        if cls.ws_url is None:
            cls.proc.terminate()
            raise unittest.SkipTest("chromium CDP endpoint did not come up")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except Exception:
            cls.proc.kill()

    def _run_session(self, engine, url, expect):
        """Connect, enable Fetch, load a page whose subresource is ``url``.

        ``expect`` is a predicate on the message dict the bridge dispatches.
        """
        captured = []

        async def main():
            async with websockets.connect(self.ws_url, max_size=2**24) as ws:
                bridge = CDPBridge(engine, lambda msg: captured.append(msg))

                async def call(method, params=None, _id=[0]):
                    _id[0] += 1
                    await ws.send(json.dumps(
                        {"id": _id[0], "method": method, "params": params or {}}))
                    while True:
                        m = json.loads(await ws.recv())
                        if m.get("id") == _id[0]:
                            return m

                await call("Target.createTarget", {"url": "about:blank"})
                # Find the new target and attach flat.
                targets = await call("Target.getTargets")
                page = [t for t in targets["result"]["targetInfos"]
                        if t["type"] == "page"][-1]
                sess = await call("Target.attachToTarget",
                                  {"targetId": page["targetId"], "flatten": True})
                sid = sess["result"]["sessionId"]

                async def call_s(method, params=None, _id=[1000]):
                    _id[0] += 1
                    await ws.send(json.dumps(
                        {"id": _id[0], "method": method,
                         "params": params or {}, "sessionId": sid}))
                    while True:
                        m = json.loads(await ws.recv())
                        if m.get("id") == _id[0]:
                            return m
                        if m.get("method") == "Fetch.requestPaused":
                            out = bridge.on_request_paused(m["params"])
                            await ws.send(json.dumps({**out, "sessionId": sid}))

                await call_s("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
                await call_s("Page.enable")
                # A data: page that requests the target URL as an image/script.
                html = f'<img src="{url}"><script src="{url}"></script>'
                await call_s("Page.navigate",
                             {"url": "data:text/html," + html.replace("<", "%3C")})
                for _ in range(40):
                    if captured:
                        break
                    await asyncio.sleep(0.1)
                await call_s("Fetch.disable")

        asyncio.run(main())
        return captured

    def test_block_reaches_real_browser(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        captured = self._run_session(
            engine, "https://ad.doubleclick.net/x.gif",
            lambda m: m["method"] == "Fetch.failRequest")
        self.assertTrue(any(m["method"] == "Fetch.failRequest" for m in captured),
                        f"no failRequest dispatched; got {[m['method'] for m in captured]}")

    def test_allow_reaches_real_browser(self):
        engine = compile_rules([
            {"id": 1, "priority": 1, "action": {"type": "block"},
             "condition": {"requestDomains": ["doubleclick.net"], "resourceTypes": ["image"]}},
        ])
        captured = self._run_session(
            engine, "https://example.org/main.css", lambda m: True)
        self.assertTrue(captured)
        self.assertTrue(all(m["method"] == "Fetch.continueRequest" for m in captured),
                        [m["method"] for m in captured])

    def test_redirect_carries_new_url_to_real_browser(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "redirect", "redirect": {"url": "https://replacement.invalid/ok.gif"}},
             "condition": {"requestDomains": ["ads.example"], "resourceTypes": ["image"]}},
        ])
        captured = self._run_session(
            engine, "https://ads.example/x.gif", lambda m: True)
        redirects = [m for m in captured if m["params"].get("url") == "https://replacement.invalid/ok.gif"]
        self.assertTrue(redirects, f"no redirect dispatched; got {captured}")

    def test_modify_headers_carries_rewritten_headers_to_real_browser(self):
        engine = compile_rules([
            {"id": 1, "priority": 1,
             "action": {"type": "modifyHeaders", "requestHeaders": [
                 {"header": "X-Lab", "operation": "set", "value": "1"}]},
             "condition": {"requestDomains": ["hdr.example"], "resourceTypes": ["image"]}},
        ])
        captured = self._run_session(
            engine, "https://hdr.example/x.gif", lambda m: True)
        mods = [m for m in captured if any(
            h["name"] == "X-Lab" and h["value"] == "1" for h in m["params"].get("headers", []))]
        self.assertTrue(mods, f"no rewritten header dispatched; got {captured}")

    def test_cosmetic_css_hides_element_in_real_browser(self):
        from src.browser_engine.cosmetic import cosmetic_css

        rules = [{"selector": ".sponsored-ad", "domains": [], "exceptions": []}]
        css = cosmetic_css(rules, host="news.example")

        async def main():
            async with websockets.connect(self.ws_url, max_size=2**24) as ws:
                seq = [0]

                async def call(method, params=None, sid=None):
                    seq[0] += 1
                    msg = {"id": seq[0], "method": method, "params": params or {}}
                    if sid:
                        msg["sessionId"] = sid
                    await ws.send(json.dumps(msg))
                    while True:
                        m = json.loads(await ws.recv())
                        if m.get("id") == seq[0]:
                            return m

                await call("Target.createTarget", {"url": "about:blank"})
                targets = await call("Target.getTargets")
                page = [t for t in targets["result"]["targetInfos"]
                        if t["type"] == "page"][-1]
                sess = await call("Target.attachToTarget",
                                  {"targetId": page["targetId"], "flatten": True})
                sid = sess["result"]["sessionId"]
                await call("Page.enable", sid=sid)
                html = '<html><body><div class="sponsored-ad">buy stuff</div></body></html>'
                await call("Page.navigate", {"url": "data:text/html," + html}, sid=sid)
                await asyncio.sleep(0.5)
                await call("Runtime.evaluate", {
                    "expression": "(() => { const s = document.createElement('style');"
                                  f" s.textContent = {css!r};"
                                  " document.head.appendChild(s); })()"}, sid=sid)
                res = await call("Runtime.evaluate", {
                    "expression": "getComputedStyle(document.querySelector('.sponsored-ad')).display",
                    "returnByValue": True}, sid=sid)
                return res["result"]["result"]["value"]

        display = asyncio.run(main())
        self.assertEqual(display, "none", "cosmetic CSS did not hide the element")


if __name__ == "__main__":
    unittest.main()

