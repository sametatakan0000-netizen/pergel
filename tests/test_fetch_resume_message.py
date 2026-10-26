"""Regression: Fetch pause/reply must resume the intercepted request exactly.

Before this fix, the resume message sent back to Chromium carried a stale
``sessionId`` even when the pause event already had one, and the command id
was synthesized as ``resume-{seq}`` instead of being the request's own id.
The result: navigation hangs under ``Fetch.enable`` (the request is never
resumed). A real Chromium run of ``Page.navigate`` to a local page timed out
until this was fixed.
"""
import unittest

from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession


class FetchResumeMessageTests(unittest.TestCase):
    def test_reply_reuses_paused_request_id(self):
        reply = {"method": "Fetch.continueRequest",
                 "params": {"requestId": "PAUSED-123"}}
        out = AdblockBrowserSession._resume_message(reply, 5, event_sid="SID-A")
        self.assertEqual(out["method"], "Fetch.continueRequest")
        self.assertEqual(out["params"]["requestId"], "PAUSED-123")

    def test_reply_carries_event_session_id(self):
        reply = {"method": "Fetch.failRequest",
                 "params": {"requestId": "PAUSED-123", "errorReason": "BlockedByClient"}}
        out = AdblockBrowserSession._resume_message(reply, 5, event_sid="SID-A")
        self.assertEqual(out["sessionId"], "SID-A")
        self.assertEqual(out["id"], 5)  # commands must carry a unique integer id

    def test_reply_falls_back_to_session_sid(self):
        reply = {"method": "Fetch.continueRequest",
                 "params": {"requestId": "PAUSED-9"}}
        out = AdblockBrowserSession._resume_message(reply, 6, event_sid=None,
                                                     session_sid="SID-B")
        self.assertEqual(out["sessionId"], "SID-B")


if __name__ == "__main__":
    unittest.main()
