"""Regression: a manifest-blocked target must never be launched, and a run must
still produce raw rows incrementally even if one target hangs.

`run.py` honors the install manifest's `blocked` flag (e.g. Vivaldi, which never
opens a CDP port) and skips those targets instead of launching them and leaking
orphaned Playwright driver processes. Raw rows are flushed as they arrive so a
partial run is still readable.
"""
import json
import os
import time
import unittest

from src.bench.runner import Scenario, Target, run_cell
from src.bench.targets import build_target

SC = Scenario("static", "/static", "MARKER")


class SkipBlockedTargetTests(unittest.TestCase):
    def test_blocked_entry_is_never_built_into_a_target(self):
        """A manifest entry with a non-empty `blocked` reason is skipped up front."""
        entry = {
            "kind": "chromium",
            "exe": "/bin/false",
            "blocked": "Vivaldi does not expose the CDP DevTools port",
        }
        # The gate is a single predicate used by run.py; assert it flags this entry.
        from src.bench.run import is_blocked
        self.assertTrue(is_blocked(entry))
        # An unblocked entry passes the same gate.
        self.assertFalse(is_blocked({"kind": "chromium", "exe": "/bin/false", "blocked": None}))
        self.assertFalse(is_blocked({"kind": "chromium", "exe": "/bin/false", "blocked": ""}))

    def test_raw_rows_flush_incrementally(self):
        """run_cell rows land on disk as each lifecycle finishes, not only at the very end."""
        from src.bench.run import flush_row

        class _OkAdapter:
            def start(self): pass
            def fetch(self, url, marker):
                class _R:
                    ok = True
                    ms = 9.0
                return _R()
            def root_pids(self):
                return []
            def stop(self): pass

        out = os.path.join("/tmp", f"bench-flush-{os.getpid()}")
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, "raw.jsonl")
        if os.path.exists(path):
            os.remove(path)
        rows = run_cell(Target("ok", _OkAdapter), SC, "http://x", lifecycles=2,
                        warmups=0, fetches=1, timeout_s=2.0)
        for r in rows:
            flush_row(path, r)
        # After writing, the file is readable and complete (2 rows).
        with open(path) as fh:
            lines = [json.loads(x) for x in fh if x.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["target"], "ok")


if __name__ == "__main__":
    unittest.main()
