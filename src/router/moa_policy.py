"""Adaptive MoA policy: decide per request bucket whether Amiral+subagents is worth its cost.

Evidence comes only from implicit feedback the learner already gets (regenerate, correction,
continued). Each eligible turn is tagged with its arm ("moa" or "single") and bucket; when the
next user turn settles the feedback, the outcome is counted for that arm.

Decision per bucket, from the two arms' bad-outcome rates (bad = retry or correction):
  * cold (either arm has < MIN_OBS observations): explore MoA with rate COLD_EXPLORE.
  * MoA clearly better (advantage >= MARGIN): MoA with rate 1 - DECIDED_SINGLE_PROBE,
    single-model probes keep the comparison honest.
  * MoA clearly worse (advantage <= -MARGIN): single with rate 1 - DECIDED_MOA_PROBE.
  * otherwise (undecided): explore MoA with rate COLD_EXPLORE.

The exploration rates are the only fixed numbers and they are explicit, configurable knobs.
Spend control is not here: plan_moa() already refuses MoA above the dynamic cap, and the
server passes spend_today into it, so a spent budget closes MoA regardless of evidence.
"""
import contextlib
import random
import sqlite3
import time
from typing import Any, Dict, Optional

NEGATIVE = {"user_retry", "user_correction"}
POSITIVE = {"continued"}

MIN_OBS = 20            # per arm before the comparison counts
MARGIN = 0.05           # bad-rate advantage needed to decide
COLD_EXPLORE = 0.10     # undecided buckets: share of eligible turns sent to MoA
DECIDED_SINGLE_PROBE = 0.05
DECIDED_MOA_PROBE = 0.10


class MoaPolicy:
    def __init__(self, db_path: str, rng: Optional[random.Random] = None,
                 cold_explore: float = COLD_EXPLORE) -> None:
        self.db_path = db_path
        self.rng = rng or random.Random()
        self.cold_explore = cold_explore
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS moa_pending (
                    session_id TEXT PRIMARY KEY, bucket TEXT NOT NULL, mode TEXT NOT NULL,
                    ts REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS moa_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, bucket TEXT NOT NULL,
                    mode TEXT NOT NULL, bad INTEGER NOT NULL, signal TEXT NOT NULL, ts REAL NOT NULL);
                """
            )

    @contextlib.contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            with conn:  # commit/rollback
                yield conn
        finally:
            conn.close()

    # ---- evidence ----------------------------------------------------------------------
    def counts(self, bucket: str) -> Dict[str, Dict[str, float]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT mode, COUNT(*), COALESCE(SUM(bad),0) FROM moa_outcomes WHERE bucket=? "
                "GROUP BY mode", (bucket,)).fetchall()
        out = {"moa": {"n": 0, "bad": 0}, "single": {"n": 0, "bad": 0}}
        for mode, n, bad in rows:
            out[mode] = {"n": n, "bad": bad}
        return out

    def bad_rates(self, bucket: str) -> Dict[str, Optional[float]]:
        c = self.counts(bucket)
        return {m: (c[m]["bad"] / c[m]["n"] if c[m]["n"] else None) for m in c}

    # ---- decision ----------------------------------------------------------------------
    def explore_rate(self, bucket: str) -> float:
        """Share of eligible turns that should run MoA in this bucket."""
        c = self.counts(bucket)
        if c["moa"]["n"] < MIN_OBS or c["single"]["n"] < MIN_OBS:
            return self.cold_explore
        rate_moa = c["moa"]["bad"] / c["moa"]["n"]
        rate_single = c["single"]["bad"] / c["single"]["n"]
        advantage = rate_single - rate_moa  # positive = MoA has fewer bad outcomes
        if advantage >= MARGIN:
            return 1.0 - DECIDED_SINGLE_PROBE
        if advantage <= -MARGIN:
            return DECIDED_MOA_PROBE
        return self.cold_explore

    def choose(self, bucket: str) -> str:
        return "moa" if self.rng.random() < self.explore_rate(bucket) else "single"

    # ---- bookkeeping -------------------------------------------------------------------
    def remember(self, session_id: str, bucket: str, mode: str, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO moa_pending VALUES (?, ?, ?, ?)",
                         (session_id, bucket, mode, now))

    def settle(self, session_id: Optional[str], signal: Optional[str],
               now: Optional[float] = None) -> Optional[str]:
        """Attribute the feedback signal to the arm that produced the previous answer.
        Returns the mode settled, or None when nothing was pending or the signal is neutral."""
        if not session_id:
            return None
        now = time.time() if now is None else now
        with self._conn() as conn:
            row = conn.execute("SELECT bucket, mode FROM moa_pending WHERE session_id=?",
                               (session_id,)).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM moa_pending WHERE session_id=?", (session_id,))
            bucket, mode = row
            if signal in NEGATIVE:
                bad = 1
            elif signal in POSITIVE:
                bad = 0
            else:
                return None
            conn.execute("INSERT INTO moa_outcomes (bucket, mode, bad, signal, ts) VALUES (?, ?, ?, ?, ?)",
                         (bucket, mode, bad, signal, now))
        return mode

    def summary(self) -> Dict[str, Any]:
        with self._conn() as conn:
            buckets = [r[0] for r in conn.execute("SELECT DISTINCT bucket FROM moa_outcomes").fetchall()]
        return {b: {"counts": self.counts(b), "bad_rate": self.bad_rates(b),
                    "explore_rate": self.explore_rate(b)} for b in buckets}
