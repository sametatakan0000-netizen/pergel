"""document-start cosmetic timing: the element must NEVER paint.

A style injected after first paint causes a flash of unstyled ad content
(FOUC). The correct enforcement point is `Page.addScriptToEvaluateOnNewDocument`
/ content-script `run_at: document_start`, so the <style> exists before the
first layout. This test measures visibility DURING load, not after.
"""
import asyncio
import json
import time
import unittest

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None

from tests.test_cdp_e2e_live import _find_chromium, _free_port
from src.browser_engine.cosmetic import cosmetic_css

# A page that reports visibility every 50ms while loading, and holds an
# ad element plus a slow-loading subresource so the page stays busy long
# enough to observe frames before the style would have been injected late.
_PAGE = """<html><head>
<style>.sponsored-ad { width: 300px; height: 90px; background: red; }</style>
</head><body>
<div class="sponsored-ad">buy stuff</div>
<script>
window.__sawVisible = false;
window.__probe = setInterval(() => {
  const el = document.querySelector('.sponsored-ad');
  if (el) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden') {
      window.__sawVisible = true;
    }
  }
}, 25);
</script>
</body></html>"""


def _pick_page_target(target_infos, created_target_id=None):
    """Choose the page target to drive after ``Target.createTarget``.

    ``Target.getTargets`` ordering is NOT guaranteed to place the freshly
    created target last (observed live: 2/5 trials), so the id returned by
    ``Target.createTarget`` is authoritative and only the newest page is a
    fallback.
    """
    pages = [t for t in target_infos if t.get("type") == "page"]
    if created_target_id is not None:
        for t in pages:
            if t.get("targetId") == created_target_id:
                return t
    return pages[-1] if pages else None


class TestCosmeticDocumentStart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if websockets is None or _find_chromium() is None:
            raise unittest.SkipTest("no chromium or websockets")
        import subprocess, tempfile, time, urllib.request
        cls.tmp = tempfile.mkdtemp(prefix="cdp-fov-")
        cls.port = _free_port()
        cls.proc = subprocess.Popen(
            [_find_chromium(), "--headless=new", "--no-sandbox",
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
            raise unittest.SkipTest("CDP endpoint did not come up")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except Exception:
            cls.proc.kill()

    def _run(self, inject_at_document_start: bool):
        css = cosmetic_css(
            [{"selector": ".sponsored-ad", "domains": [], "exceptions": []}],
            host="news.example")

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

                created = await call("Target.createTarget", {"url": "about:blank"})
                created_id = created["result"]["targetId"]
                targets = await call("Target.getTargets")
                page = _pick_page_target(targets["result"]["targetInfos"],
                                         created_id)
                sess = await call("Target.attachToTarget",
                                  {"targetId": page["targetId"], "flatten": True})
                sid = sess["result"]["sessionId"]
                await call("Page.enable", sid=sid)
                inject = ("(() => { const s = document.createElement('style');"
                          " s.setAttribute('data-cosmetic','1');"
                          f" s.textContent = {json.dumps(css)};"
                          " const d = document.documentElement || document.head;"
                          " if (d) { d.appendChild(s); }"
                          " else { document.addEventListener('DOMContentLoaded',"
                          "   () => (document.head || document.documentElement).appendChild(s)); }"
                          " })()")
                if inject_at_document_start:
                    await call("Page.addScriptToEvaluateOnNewDocument",
                               {"source": inject}, sid=sid)
                await call("Page.navigate",
                           {"url": "data:text/html," + _PAGE.replace("#", "%23")},
                           sid=sid)
                # Wait for the page's inline probe script to initialise so
                # window.__sawVisible is a real boolean, not undefined. Without
                # this the final evaluate races the parser (intermittent flake).
                ready_ok = False
                for _ in range(100):
                    ready = await call("Runtime.evaluate",
                                       {"expression": "typeof window.__sawVisible === 'boolean'",
                                        "returnByValue": True}, sid=sid)
                    if ready["result"]["result"].get("value"):
                        ready_ok = True
                        break
                    await asyncio.sleep(0.02)
                if not ready_ok:
                    raise AssertionError(
                        "probe script never initialised on the target "
                        "(window.__sawVisible is not a boolean)")
                if not inject_at_document_start:
                    await asyncio.sleep(0.5)  # late injection: after load
                    await call("Runtime.evaluate", {"expression": inject}, sid=sid)
                # Poll instead of one fixed-latency read: headless tabs can
                # throttle the 25ms probe interval, so give the flag up to
                # 2.5s to flip. The flag is sticky-true once set.
                deadline = time.monotonic() + 2.5
                while True:
                    res = await call("Runtime.evaluate",
                                     {"expression": "window.__sawVisible === true",
                                      "returnByValue": True}, sid=sid)
                    if res["result"]["result"].get("value"):
                        return True
                    if time.monotonic() >= deadline:
                        return False
                    await asyncio.sleep(0.05)

        return asyncio.run(main())

    def test_document_start_style_prevents_ever_visible(self):
        self.assertFalse(self._run(True),
                         "element was visible at some point despite document-start CSS")

    def test_late_injection_is_observable(self):
        # Sanity: the probe actually detects a visible ad. Without the guard
        # the element must have been seen — otherwise the other test is vacuous.
        self.assertTrue(self._run(False),
                        "probe never saw the ad even with late injection; "
                        "the visibility check is not measuring anything")


class TestPickPageTarget(unittest.TestCase):
    """Pure-logic guard for the flaky live test: Target.getTargets ordering is
    NOT guaranteed to place the freshly created target last (observed live:
    2/5 trials), so a positional [-1] pick drives a stale about:blank where
    window.__sawVisible is undefined and the sanity assertion misfires."""

    def test_created_target_preferred_even_when_not_last(self):
        old = {"targetId": "AAAA", "type": "page"}
        new = {"targetId": "BBBB", "type": "page"}
        iframe = {"targetId": "CCCC", "type": "iframe"}
        picked = _pick_page_target([new, old, iframe], created_target_id="BBBB")
        self.assertIsNotNone(picked)
        self.assertEqual(picked["targetId"], "BBBB")

    def test_falls_back_to_last_page_when_created_id_absent(self):
        old = {"targetId": "AAAA", "type": "page"}
        new = {"targetId": "BBBB", "type": "page"}
        picked = _pick_page_target([old, new], created_target_id="ZZZZ")
        self.assertEqual(picked["targetId"], "BBBB")

    def test_no_pages_returns_none(self):
        self.assertIsNone(_pick_page_target([{"targetId": "C", "type": "iframe"}],
                                            created_target_id="C"))


if __name__ == "__main__":
    unittest.main()
