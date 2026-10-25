"""Live Chromium e2e: the four adblock layers work together on a real page.

This is the integration receipt. One headless Chromium, one filter list, one
page carrying an ad in every layer's shape:

- network   : ``||ads.example.com^`` blocks the tracking pixel (CDP ``Fetch``)
- cosmetic  : ``test.com##.sponsored-ad`` hides the banner div (injected CSS)
- scriptlet : ``test.com##+js(set-constant, __adBlockEnabled, true)`` sets a flag
- procedural: ``test.com#?#.slot:has-text(Sponsored)`` hides only the sponsored slot

Skips cleanly without Chromium/websockets so the suite stays hermetic.
"""
import asyncio
import json
import subprocess
import tempfile
import unittest
import urllib.request

from tests.test_cdp_e2e_live import _find_chromium, websockets
from src.browser_engine.adblock_session import build_injection, compile_adblock
from src.browser_engine.cdp_bridge import CDPBridge

LIVE_LIST = [
    "||ads.example.com^",                                  # network block
    "test.com##.sponsored-ad",                             # cosmetic hide
    "test.com##+js(set-constant, __adBlockEnabled, true)",  # scriptlet
    "test.com#?#.slot:has-text(Sponsored)",                # procedural
]

PAGE = (
    "<html><body>"
    "<div class='sponsored-ad' style='width:300px;height:90px'>Buy now</div>"
    "<div class='slot' style='width:200px;height:20px'>Sponsored content</div>"
    "<div class='slot' style='width:200px;height:20px'>Organic content</div>"
    "<img src='https://ads.example.com/pixel.gif'>"
    "</body></html>"
)

# Host the injection is scoped to (the page is a data: URL with no host).
HOST = "test.com"


class TestAdblockLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _find_chromium() is None or websockets is None:
            raise unittest.SkipTest("no chromium binary or websockets lib")
        cls.tmp = tempfile.mkdtemp()
        cls.port = 9531
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

    def test_all_four_layers_enforce_on_real_page(self):
        bundle = compile_adblock(LIVE_LIST)
        js = build_injection(bundle, HOST)

        async def go():
            async with websockets.connect(self.ws_url, max_size=2**24) as ws:
                seq = [0]
                sent = []          # every message the bridge dispatches

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
                await call("Fetch.enable", sid=sid)
                await call("Page.enable", sid=sid)
                await call("Runtime.enable", sid=sid)
                await call("Page.addScriptToEvaluateOnNewDocument",
                           {"source": js}, sid=sid)

                bridge = CDPBridge(bundle.network,
                                   send=lambda m: sent.append(m))

                await call("Page.navigate",
                           {"url": "data:text/html," + PAGE}, sid=sid)

                # Pump events: answer every Fetch.requestPaused via the bridge.
                for _ in range(40):
                    try:
                        evt = json.loads(await asyncio.wait_for(ws.recv(), 0.1))
                    except Exception:
                        continue
                    if evt.get("method") == "Fetch.requestPaused":
                        msg = bridge.on_request_paused(evt["params"])
                        reply = {"id": f"resume-{seq[0]}", "method": msg["method"],
                                 "params": msg["params"]}
                        seq[0] += 1
                        await ws.send(json.dumps(reply))

                r = await call("Runtime.evaluate", {
                    "expression": (
                        "JSON.stringify({"
                        "adHidden: getComputedStyle("
                        "  document.querySelector('.sponsored-ad')).display === 'none',"
                        "adFlag: window.__adBlockEnabled === true,"
                        "slots: [...document.querySelectorAll('.slot')].map(e =>"
                        "  getComputedStyle(e).display)"
                        "})"
                    ), "returnByValue": True}, sid=sid)
                return sent, json.loads(r["result"]["result"]["value"])

        sent, dom = asyncio.run(go())

        # 1) network layer: the tracking pixel was failed at the CDP Fetch seam
        block_urls = [m["params"].get("url") for m in sent
                      if m["method"] == "Fetch.failRequest"]
        self.assertTrue(
            any(m["method"] == "Fetch.failRequest" for m in sent),
            f"no network block dispatched; sent={sent}")
        # failRequest carries no url; assert the errorReason is the block reason
        self.assertTrue(any(
            m["params"].get("errorReason") == "BlockedByClient"
            for m in sent if m["method"] == "Fetch.failRequest"))

        # 2) cosmetic layer: the banner is hidden by injected CSS
        self.assertTrue(dom["adHidden"], f"cosmetic did not hide banner: {dom}")
        # 3) scriptlet layer: the flag was set at document-start
        self.assertTrue(dom["adFlag"], f"scriptlet did not fire: {dom}")
        # 4) procedural layer: sponsored slot hidden, organic slot kept
        self.assertEqual(dom["slots"], ["none", "block"],
                         f"procedural hid wrong slots: {dom}")


if __name__ == "__main__":
    unittest.main()
