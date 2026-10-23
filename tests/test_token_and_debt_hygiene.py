import os
import tempfile
import unittest
from src.devtools.token_and_debt_hygiene import (
    compress_cli_output,
    scan_shortcut_debt,
)
from src.browser_engine.browser_orchestrator import BrowserFarmOrchestrator


class TestTokenAndDebtHygiene(unittest.TestCase):
    def test_compress_cli_output_reduces_repetitive_logs_by_over_60_percent(self):
        noisy_log = "\n".join(
            [f"PASS tests/test_mod_{i % 3}.py::test_case ... ok" for i in range(60)]
            + ["ERROR: Failed assertion in src/router/oracle_router.py:42"]
        )
        compressed = compress_cli_output(noisy_log, max_lines=15)
        self.assertLess(len(compressed), len(noisy_log) * 0.4)
        self.assertIn("ERROR: Failed assertion", compressed)
        self.assertIn("omitted", compressed)

    def test_scan_shortcut_debt_collects_ponytail_shortcut_and_todo_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_py = os.path.join(tmp, "sample.py")
            with open(sample_py, "w", encoding="utf-8") as f:
                f.write(
                    "def run():\n"
                    "    # shortcut: in-memory cache only, upgrade when concurrency > 50\n"
                    "    # TODO: add retry backoff\n"
                    "    return True\n"
                )
            items = scan_shortcut_debt(tmp)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["kind"], "shortcut")
            self.assertIn("concurrency > 50", items[0]["detail"])

    def test_scan_shortcut_debt_ignores_docstring_mentions_and_only_matches_comment_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_py = os.path.join(tmp, "doc_only.py")
            with open(sample_py, "w", encoding="utf-8") as f:
                f.write(
                    '"""Tarayıcı: `# shortcut:` ve `# TODO:` kayıtlarını toplar."""\n'
                    "def noop():\n"
                    '    msg = "# shortcut: not a comment"\n'
                    "    return msg\n"
                )
            items = scan_shortcut_debt(tmp)
            self.assertEqual(items, [])

    def test_browser_orchestrator_persists_domain_floors_and_apis_to_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "browser_memory.db")
            orch1 = BrowserFarmOrchestrator(db_path=db_path)
            orch1.record_domain_escalation(
                url="https://waf.example.com/login",
                attempted_engines=["lightpanda", "camofox"],
                final_engine="camofox",
                discovered_apis=["https://waf.example.com/api/v1/session.json"],
            )
            # Restart with fresh instance pointing to the same SQLite DB
            orch2 = BrowserFarmOrchestrator(db_path=db_path)
            self.assertEqual(
                orch2.select_engine(needs_vision=False, js_complexity="low", url="https://waf.example.com/dashboard"),
                "camofox",
            )
            self.assertEqual(
                orch2.domain_discovered_apis.get("waf.example.com"),
                ["https://waf.example.com/api/v1/session.json"],
            )
            self.assertGreaterEqual(len(orch2.evolution_ledger), 2)


if __name__ == "__main__":
    unittest.main()
