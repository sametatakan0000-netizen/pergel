"""Live Chromium e2e: scriptlet and procedural layers really work.

Reuses the harness from ``test_cdp_e2e_live`` — one headless Chromium per
class, real WebSocket CDP, real DOM assertions.
"""
import asyncio
import json
import os
import subprocess
import tempfile
import unittest
import urllib.request

from tests.test_cdp_e2e_live import _find_chromium
from src.browser_engine.procedural import compile_procedural, procedural_js
from src.browser_engine.scriptlets import compile_scriptlets, scriptlet_js


class TestScriptletLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.port = 9501
        cls.proc = subprocess.Popen(
            [_find_chromium(), "--headless=new", "--no-sandbox",
             f"--remote-debugging-port={cls.port}", "--user-data-dir=" + cls.tmp,
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{cls.port}/json/version", timeout=1) as r:
                    cls.ws_url = json.load(r)["webSocketDebuggerUrl"]
                    return
            except Exception:
                import time
                time.sleep(0.25)
        raise RuntimeError("chromium did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()

    def _run(self, js, page_html):
        async def go():
            import websockets
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
                tg = await call("Target.getTargets")
                page = [t for t in tg["result"]["targetInfos"]
                        if t["type"] == "page"][-1]
                sess = await call("Target.attachToTarget",
                                  {"targetId": page["targetId"], "flatten": True})
                sid = sess["result"]["sessionId"]
                await call("Page.enable", sid=sid)
                await call("Page.addScriptToEvaluateOnNewDocument",
                           {"source": js}, sid=sid)
                await call("Page.navigate",
                           {"url": "data:text/html," + page_html}, sid=sid)
                await asyncio.sleep(1.0)
                r = await call("Runtime.evaluate",
                               {"expression": "window.__result",
                                "returnByValue": True}, sid=sid)
                return r["result"]["result"].get("value")

        return asyncio.run(go())

    def test_set_constant_scriptlet_runs(self):
        js = scriptlet_js(
            compile_scriptlets(["example.com##+js(set-constant, __adBlockEnabled, true)"]),
            host="www.example.com")
        page = ("<html><body><script>"
                "window.__result = (window.__adBlockEnabled === true);"
                "</script></body></html>")
        self.assertTrue(self._run(js, page))

    def test_no_eval_blocks_eval(self):
        js = scriptlet_js(compile_scriptlets(["y.com##+js(noeval)"]), host="y.com")
        page = ("<html><body><script>"
                "try { window.eval('window.__result = \\\"ran\\\"'); } catch(e) {"
                "  window.__result = 'blocked:' + e.constructor.name; }"
                "</script></body></html>")
        self.assertEqual(self._run(js, page), "blocked:ReferenceError")

    def test_no_fetch_if_blocks_matching_request(self):
        js = scriptlet_js(
            compile_scriptlets(["y.com##+js(no-fetch-if, tracker)"]), host="y.com")
        page = ("<html><body><script>"
                "fetch('https://tracker.example/pixel')"
                "  .then(() => { window.__result = 'allowed'; })"
                "  .catch(e => { window.__result = 'blocked:' + e.constructor.name; });"
                "</script></body></html>")
        self.assertEqual(self._run(js, page), "blocked:ReferenceError")

    def test_no_webrtc_disables_peer_connection(self):
        js = scriptlet_js(compile_scriptlets(["y.com##+js(nowebrtc)"]), host="y.com")
        page = ("<html><body><script>"
                "try { new RTCPeerConnection(); window.__result = 'allowed'; }"
                "catch(e) { window.__result = 'blocked:' + e.constructor.name; }"
                "</script></body></html>")
        self.assertEqual(self._run(js, page), "blocked:ReferenceError")

    def test_abort_on_property_write_scriptlet(self):
        js = scriptlet_js(
            compile_scriptlets(["example.com##+js(aopw, __adBlockEnabled)"]),
            host="example.com")
        page = ("<html><body><script>"
                "let hit = false;"
                "try { window.__adBlockEnabled = 1; } catch (e) { hit = true; }"
                "window.__result = hit;"
                "</script></body></html>")
        self.assertTrue(self._run(js, page))

    def test_nowoif_blocks_window_open(self):
        js = scriptlet_js(
            compile_scriptlets(["example.com##+js(nowoif)"]), host="example.com")
        page = ("<html><body><script>"
                "window.__result = (window.open('http://x') === null);"
                "</script></body></html>")
        self.assertTrue(self._run(js, page))


class TestProceduralLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.port = 9502
        cls.proc = subprocess.Popen(
            [_find_chromium(), "--headless=new", "--no-sandbox",
             f"--remote-debugging-port={cls.port}", "--user-data-dir=" + cls.tmp,
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{cls.port}/json/version", timeout=1) as r:
                    cls.ws_url = json.load(r)["webSocketDebuggerUrl"]
                    return
            except Exception:
                import time
                time.sleep(0.25)
        raise RuntimeError("chromium did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()

    def _run(self, js, page_html, expr="window.__result", timeout=4.0):
        async def go():
            import websockets
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
                tg = await call("Target.getTargets")
                page = [t for t in tg["result"]["targetInfos"]
                        if t["type"] == "page"][-1]
                sess = await call("Target.attachToTarget",
                                  {"targetId": page["targetId"], "flatten": True})
                sid = sess["result"]["sessionId"]
                await call("Page.enable", sid=sid)
                await call("Page.addScriptToEvaluateOnNewDocument",
                           {"source": js}, sid=sid)
                await call("Page.navigate",
                           {"url": "data:text/html," + page_html}, sid=sid)
                deadline = timeout
                waited = 0.0
                while waited < deadline:
                    await asyncio.sleep(0.1)
                    waited += 0.1
                    r = await call("Runtime.evaluate",
                                   {"expression": expr,
                                    "returnByValue": True}, sid=sid)
                    val = r["result"]["result"].get("value")
                    if val is not None:
                        return val
                return None

        return asyncio.run(go())

    def test_has_text_hides_matching_element(self):
        js = procedural_js(
            compile_procedural(["news.com#?#.slot:has-text(Sponsored)"]),
            host="news.com")
        page = ("<html><body>"
                "<div class='slot'>Sponsored content</div>"
                "<div class='slot'>organic story</div>"
                "<script>"
                "setTimeout(() => {"
                "  const els = [...document.querySelectorAll('.slot')];"
                "  window.__result = els.map(e => getComputedStyle(e).display);"
                "}, 300);"
                "</script></body></html>")
        self.assertEqual(self._run(js, page), ["none", "block"])

    def test_has_subselector_hides_parent(self):
        js = procedural_js(
            compile_procedural(["x.com#?#.row:has(.adsbygoogle)"]), host="x.com")
        page = ("<html><body>"
                "<div class='row'><span class='adsbygoogle'>a</span></div>"
                "<div class='row'><span>clean</span></div>"
                "<script>"
                "setTimeout(() => {"
                "  window.__result = [...document.querySelectorAll('.row')]"
                "    .map(e => getComputedStyle(e).display);"
                "}, 300);"
                "</script></body></html>")
        self.assertEqual(self._run(js, page), ["none", "block"])

    def test_dynamic_node_is_caught(self):
        js = procedural_js(
            compile_procedural(["x.com#?#.slot:has-text(Sponsored)"]), host="x.com")
        page = ("<html><body><script>"
                "setTimeout(() => {"
                "  const d = document.createElement('div');"
                "  d.className = 'slot'; d.textContent = 'Sponsored here';"
                "  document.body.appendChild(d);"
                "  setTimeout(() => {"
                "    window.__result = getComputedStyle(d).display;"
                "  }, 300);"
                "}, 100);"
                "</script></body></html>")
        self.assertEqual(self._run(js, page), "none")


if __name__ == "__main__":
    unittest.main()
