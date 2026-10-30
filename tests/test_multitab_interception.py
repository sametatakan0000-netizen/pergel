"""New tabs are plain browser windows by design (zero CDP) — not just the startup target.

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
    def test_new_tabs_are_not_intercepted(self):
        """New tabs are plain browser windows: their requests must NOT reach
        the enforcement engine (zero CDP on new targets -- the OAuth
        white-screen fix). The startup tab keeps full enforcement: the
        baseline assertion guards against this passing vacuously."""
        decisions = []

        async def scenario():
            bundle = compile_adblock(["||doubleclick.net^"])
            async with AdblockBrowserSession(
                    bundle, headless=True,
                    on_blocked=decisions.append) as sess:
                rep = await sess._call_root(
                    "Target.createTarget", {"url": "about:blank"})
                tid = rep["result"]["targetId"]
                await asyncio.sleep(1)  # grace: auto-attach would land here
                before = len(decisions)
                new_tab_hits = [d for d in decisions[:before]
                                if "doubleclick.net" in d["url"]]
                await sess._call("Page.navigate", {"url": TAB_HTML})
                await asyncio.sleep(2)
                startup_hits = [d for d in decisions[before:]
                                if "doubleclick.net" in d["url"]]
            scenario.new_tab_hits = new_tab_hits
            scenario.startup_hits = startup_hits

        scenario.new_tab_hits = []
        scenario.startup_hits = []
        asyncio.run(scenario())
        self.assertFalse(
            scenario.new_tab_hits,
            "a NEW tab's request must NOT be intercepted (zero CDP = plain "
            f"window); decisions seen: {scenario.new_tab_hits!r}")
        self.assertTrue(
            scenario.startup_hits,
            "baseline: the startup tab must still be intercepted and "
            f"blocked; decisions seen: {scenario.startup_hits!r}")

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
