"""RED: every page tab is intercepted — not just the startup target.

The product is a real browser: users open tabs. Today the session enables
``Fetch`` on ONE page target (the last one at startup), so (a) the startup
attach race can leave the visible tab entirely unguarded — observed live as a
window with 0 blocks — and (b) any tab opened later is never intercepted at
all. Every page target, present and future, must run the enforcement engine.
"""
import asyncio
import unittest

from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession

AD_URL = "https://ad.doubleclick.net/x.png"
TAB_HTML = f"data:text/html,<img src={AD_URL}>"


class TestEveryTabIntercepted(unittest.TestCase):
    def test_new_tabs_requests_reach_the_engine(self):
        decisions = []

        async def scenario():
            bundle = compile_adblock(["||doubleclick.net^"])
            async with AdblockBrowserSession(
                    bundle, headless=True,
                    on_blocked=decisions.append) as sess:
                rep = await sess._call_root(
                    "Target.createTarget", {"url": "about:blank"})
                tid = rep["result"]["targetId"]
                sid = await sess.wait_session_for(tid, timeout=5)
                await sess._send_on(sid, "Page.navigate", {"url": TAB_HTML})
                await asyncio.sleep(2)

        asyncio.run(scenario())
        hits = [d for d in decisions if "doubleclick.net" in d["url"]]
        self.assertTrue(
            hits,
            "a NEW tab's ad request must be intercepted and surfaced; "
            f"decisions seen: {decisions!r}")

    def test_new_tabs_have_no_cdp_session(self):
        """New tabs must NOT be auto-armed — zero CDP means OAuth popups
        work as plain browser windows (no debugger-pause)."""
        seen = {}

        async def scenario():
            bundle = compile_adblock(["||doubleclick.net^"])
            async with AdblockBrowserSession(bundle, headless=True) as sess:
                rep = await sess._call_root(
                    "Target.createTarget", {"url": "about:blank"})
                tid = rep["result"]["targetId"]
                seen["tid"] = tid
                seen["tracked"] = sess.page_sessions.get(tid)

        asyncio.run(scenario())
        self.assertIsNone(
            seen["tracked"],
            "new tab targets must NOT have CDP enforcement sessions "
            "(zero CDP = OAuth popups work correctly)")


if __name__ == "__main__":
    unittest.main()
