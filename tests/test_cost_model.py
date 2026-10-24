import os
import sqlite3
import tempfile
import unittest

from src.router.cost_model import cached_tokens_from, turn_cost_usd
from src.router.live_router import LiveRouter
from src.router.model_registry import VerifiedProfile


def prof(cin=2.0, cout=10.0, cache=0.2):
    return VerifiedProfile(model_id="v/m", status="verified_metadata", portal_cost_in=cin,
                           portal_cost_out=cout, list_cost_in=cin, list_cost_out=cout,
                           list_cost_cache_read=cache)


class CostModelTests(unittest.TestCase):
    def test_no_cache_info_is_full_input_price_upper_bound(self):
        self.assertAlmostEqual(turn_cost_usd(prof(), 100_000, 1000), 0.21, places=6)

    def test_cached_tokens_use_cache_read_price(self):
        self.assertAlmostEqual(turn_cost_usd(prof(), 100_000, 1000, cached=80_000),
                               20_000 * 2.0 / 1e6 + 80_000 * 0.2 / 1e6 + 1000 * 10.0 / 1e6, places=6)

    def test_unknown_cache_price_falls_back_to_input_price(self):
        self.assertAlmostEqual(turn_cost_usd(prof(cache=None), 100_000, 0, cached=80_000), 0.2, places=6)

    def test_cached_is_clamped_to_prompt(self):
        self.assertAlmostEqual(turn_cost_usd(prof(), 1000, 0, cached=5000), 1000 * 0.2 / 1e6, places=9)

    def test_extract_cached_tokens_from_usage(self):
        self.assertEqual(cached_tokens_from({"prompt_tokens_details": {"cached_tokens": 7}}), 7)
        self.assertEqual(cached_tokens_from({}), None)
        self.assertEqual(cached_tokens_from({"prompt_tokens_details": None}), None)


class CachedPersistenceTests(unittest.TestCase):
    def test_record_upstream_persists_cached_tokens_and_spend_uses_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "r.db")
            r = LiveRouter(db, {"v/m": prof()}, explore_epsilon=0)
            r.record_upstream("v/m", 200, 10, 100_000, 1000, cached_tokens=80_000, now=1000.0)
            r.record_upstream("v/m", 200, 10, 100_000, 1000, now=1001.0)  # no cache info -> upper bound
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute("SELECT cached_tokens FROM upstream_events ORDER BY id").fetchall(),
                                 [(80_000,), (None,)])
            expected = turn_cost_usd(prof(), 100_000, 1000, cached=80_000) + turn_cost_usd(prof(), 100_000, 1000)
            self.assertAlmostEqual(r.spent_since(0, now=2000.0), expected, places=6)

    def test_old_database_without_the_column_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "old.db")
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE upstream_events (id INTEGER PRIMARY KEY AUTOINCREMENT, model_id TEXT NOT NULL, "
                          "status INTEGER NOT NULL, latency_ms INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, ts REAL NOT NULL)")
                c.execute("INSERT INTO upstream_events (model_id,status,prompt_tokens,completion_tokens,ts) VALUES ('v/m',200,1000,10,5)")
            r = LiveRouter(db, {"v/m": prof()}, explore_epsilon=0)
            r.record_upstream("v/m", 200, 1, 50, 5, cached_tokens=40, now=6.0)
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute("SELECT cached_tokens FROM upstream_events ORDER BY id").fetchall(), [(None,), (40,)])
