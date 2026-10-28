"""RED: Vane shield stats — live blocked-counter backend for the shield panel.

The shield panel polls a loopback endpoint while the user browses; it must
receive JSON with the running total and top blocked rules. The panel may run
from a ``file://`` document (origin ``null``), so the endpoint must answer
CORS-permissive (``Access-Control-Allow-Origin: *``) on loopback only.
"""
import json
import threading
import unittest
import urllib.request

from src.brand.stats import ShieldStats, serve_stats


class TestShieldStats(unittest.TestCase):
    def test_records_blocked_decisions(self):
        st = ShieldStats()
        st.record({"action": "block", "rule_id": "||ads^"})
        st.record({"action": "block", "rule_id": "||ads^"})
        st.record({"action": "redirect", "rule_id": "||track^"})
        st.record({"action": "allow", "rule_id": None})
        self.assertEqual(st.snapshot()["blocked_total"], 3)

    def test_top_rules_sorted_by_count(self):
        st = ShieldStats()
        for rid in ("||a^", "||b^", "||b^"):
            st.record({"action": "block", "rule_id": rid})
        top = st.snapshot()["top_rules"]
        self.assertEqual(top[0], {"rule": "||b^", "count": 2})

    def test_unknown_rule_labeled_generic(self):
        st = ShieldStats()
        st.record({"action": "block", "rule_id": None})
        self.assertEqual(st.snapshot()["top_rules"][0]["rule"], "genel kural")


class TestStatsEndpoint(unittest.TestCase):
    def test_serves_json_snapshot_with_cors(self):
        stop, port = serve_stats(host="127.0.0.1", port=0)
        try:
            st_ok = threading.Event()  # keep linter honest about threading use
            st_ok.set()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/stats")
            with urllib.request.urlopen(req, timeout=3) as r:
                self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
                body = json.load(r)
            self.assertIn("blocked_total", body)
            self.assertIn("top_rules", body)
        finally:
            stop()

    def test_server_binds_loopback_only(self):
        stop, port = serve_stats(host="127.0.0.1", port=0)
        try:
            with open("/proc/net/tcp") as f:
                rows = [ln.split() for ln in f.read().splitlines()[1:]]
            listening = [r for r in rows if int(r[1].split(":")[1], 16) == port]
            self.assertTrue(listening, "stats port must be listening")
            for r in listening:
                ip_hex = r[1].split(":")[0]
                self.assertEqual(ip_hex, "0100007F", "loopback only (127.0.0.1)")
        finally:
            stop()


if __name__ == "__main__":
    unittest.main()
