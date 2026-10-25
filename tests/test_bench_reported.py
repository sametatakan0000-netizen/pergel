import json
import os
import re
import unittest

from src.bench.report import load_reported, render_reported

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTED_PATH = os.path.join(REPO_ROOT, "bench", "reported.json")

VALID = {
    "claim": "a claim",
    "value": "42",
    "source_url": "https://example.com/bench",
    "retrieved": "2026-10-25",
    "measured_by": "vendor",
}


class TestReportedNumbersLoader(unittest.TestCase):
    """Task 3.5 — reported-numbers table: cited vendor/third-party figures only."""

    def _load_one(self, entry):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump([entry], fh)
            path = fh.name
        try:
            return load_reported(path)
        finally:
            os.unlink(path)

    def test_repo_seed_table_loads(self):
        entries = load_reported(REPORTED_PATH)
        self.assertGreaterEqual(len(entries), 8)
        for entry in entries:
            self.assertTrue(entry["source_url"].startswith("https://"))
            self.assertIn(entry["measured_by"], ("vendor", "third-party"))
            self.assertRegex(entry["retrieved"], r"^\d{4}-\d{2}-\d{2}$")

    def test_entry_missing_source_url_rejected(self):
        bad = dict(VALID, source_url="")
        with self.assertRaises(ValueError) as ctx:
            self._load_one(bad)
        self.assertIn("source_url", str(ctx.exception))

    def test_entry_missing_retrieved_rejected(self):
        bad = dict(VALID, retrieved="")
        with self.assertRaises(ValueError) as ctx:
            self._load_one(bad)
        self.assertIn("retrieved", str(ctx.exception))

    def test_bad_measured_by_rejected(self):
        self.assertRaises(ValueError, self._load_one, dict(VALID, measured_by="ours"))

    def test_renderer_separates_reported_from_ours(self):
        text = render_reported(load_reported(REPORTED_PATH))
        self.assertIn("Reported by others — not reproduced here", text)
        self.assertIn("123.0 MB", text)
        self.assertIn("Speedometer 3.1 record score", text)


if __name__ == "__main__":
    unittest.main()
