import unittest
from unittest import mock
from src.browser_engine import worker as w


class RobotsTTL(unittest.TestCase):
    def test_expired_entry_is_refetched(self):
        w._ROBOTS_CACHE.clear()
        calls = []

        def fake_fetch(url, policy, timeout=15, headers=None, egress=None, **kw):
            calls.append(1)
            raise OSError("down")
        with mock.patch.object(w, "_pinned_fetch", fake_fetch):
            w._allowed_by_robots("http://h.test/a", "UA")
            w._allowed_by_robots("http://h.test/b", "UA")
            self.assertEqual(len(calls), 1)
            rp, ts = w._ROBOTS_CACHE["http://h.test"]
            w._ROBOTS_CACHE["http://h.test"] = (rp, ts - w.ROBOTS_TTL_S - 1)
            w._allowed_by_robots("http://h.test/c", "UA")
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
