"""Live routing for the OpenAI-compatible proxy path.

Every decision uses only verifiable inputs:
  * model membership/capabilities/prices/benchmarks from ``model_registry`` (public data),
  * real upstream outcomes (HTTP status, latency, token usage) recorded per request.
No model is ever called just to "profile" it, and nothing here fabricates quality signals.

Selection policy (documented, deterministic):
  1. A virtual profile (``oracle/auto`` etc.) picks a starting price tier. ``oracle/auto``
     classifies only the latest user message; Hermes sends tool schemas on every turn, so
     tool presence is not a difficulty signal.
  2. Candidates must be routable (verified metadata + native tool calling); if any message
     in the conversation contains an image, candidates must accept images.
  3. Order: tiers >= start (ascending), within a tier the higher published Artificial
     Analysis intelligence index first (unknown last), then lower list price. Lower tiers
     follow as last-resort fallbacks. Models cooling down after 429/5xx/404 move to the end.
  4. Session affinity is persisted in SQLite. A session only escalates (never downgrades)
     so prompt caches survive restarts and easy follow-up turns.
"""
import contextlib
import copy
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from src.router.model_registry import VerifiedProfile, clamp_effort
from src.router.outcome_learning import OutcomeLearner, bucket_for
from src.router.request_features import estimate_tokens, has_image, keyword_tier

VIRTUAL_PROFILES = {
    "oracle/auto": None,  # classified per request
    "oracle/eco": 1,
    "oracle/agentic": 2,
    "oracle/premium": 4,
    "oracle/free": 0,     # special: zero list price only
}

COOLDOWN_SECONDS = {429: 300, 404: 3600}
SERVER_ERROR_COOLDOWN = 300

def price_tier(profile: VerifiedProfile) -> int:
    """Explicit billed-price bands (Portal price when known, else list; USD per 1M input tokens).
    A cost policy, not a quality claim."""
    cost = profile.billed_cost_in
    if cost is None:
        return 99
    if cost <= 0.3:
        return 1
    if cost <= 1.0:
        return 2
    if cost <= 3.0:
        return 3
    return 4


def classify_tier(messages: List[Dict[str, Any]]) -> int:
    return keyword_tier(messages)


UNKNOWN_QUALITY = 25.0  # stand-in AA index for models without published benchmarks (sorts low)


class LiveRouter:
    def __init__(self, db_path: str, profiles: Dict[str, VerifiedProfile],
                 learner: Optional[OutcomeLearner] = None, explore_epsilon: float = 0.05):
        self.db_path = db_path
        self.profiles = dict(profiles)
        self.learner = learner or OutcomeLearner(db_path, epsilon=explore_epsilon)
        directory = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(directory, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_affinity (
                    session_id TEXT PRIMARY KEY, model_id TEXT NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS upstream_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, model_id TEXT NOT NULL, status INTEGER NOT NULL,
                    latency_ms INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, ts REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS model_cooldowns (
                    model_id TEXT PRIMARY KEY, until REAL NOT NULL, status INTEGER NOT NULL);
                """
            )

    @contextlib.contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:  # commit / rollback
                yield conn
        finally:
            conn.close()

    def update_profiles(self, profiles: Dict[str, VerifiedProfile]) -> None:
        self.profiles = dict(profiles)

    # ---- persistence -------------------------------------------------------------------
    def commit_choice(self, session_id: Optional[str], model_id: str) -> None:
        if not session_id:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO session_affinity VALUES (?, ?, ?) ON CONFLICT(session_id) "
                "DO UPDATE SET model_id=excluded.model_id, updated_at=excluded.updated_at",
                (session_id, model_id, time.time()),
            )

    def clear_sticky(self, session_id: Optional[str]) -> None:
        if not session_id:
            return
        with self._conn() as conn:
            conn.execute("DELETE FROM session_affinity WHERE session_id=?", (session_id,))

    def sticky_model(self, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        with self._conn() as conn:
            row = conn.execute("SELECT model_id FROM session_affinity WHERE session_id=?", (session_id,)).fetchone()
        return row[0] if row else None

    def record_upstream(self, model_id: str, status: int, latency_ms: int,
                        prompt_tokens: Optional[int] = None, completion_tokens: Optional[int] = None,
                        now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        cooldown = COOLDOWN_SECONDS.get(status, SERVER_ERROR_COOLDOWN if status >= 500 else 0)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO upstream_events (model_id, status, latency_ms, prompt_tokens, completion_tokens, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (model_id, status, latency_ms, prompt_tokens, completion_tokens, now),
            )
            if cooldown:
                conn.execute(
                    "INSERT INTO model_cooldowns VALUES (?, ?, ?) ON CONFLICT(model_id) "
                    "DO UPDATE SET until=excluded.until, status=excluded.status",
                    (model_id, now + cooldown, status),
                )

    def cooling_down(self, now: Optional[float] = None) -> set:
        now = time.time() if now is None else now
        with self._conn() as conn:
            rows = conn.execute("SELECT model_id FROM model_cooldowns WHERE until > ?", (now,)).fetchall()
        return {r[0] for r in rows}

    def model_stats(self, model_id: str) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(status >= 400), COALESCE(SUM(prompt_tokens),0), "
                "COALESCE(SUM(completion_tokens),0), AVG(latency_ms) FROM upstream_events WHERE model_id=?",
                (model_id,),
            ).fetchone()
        return {"requests": row[0], "errors": row[1] or 0, "prompt_tokens": row[2],
                "completion_tokens": row[3], "avg_latency_ms": row[4]}

    # ---- selection ---------------------------------------------------------------------
    def _pool(self, free_only: bool, needs_vision: bool = False, min_context: int = 0) -> List[VerifiedProfile]:
        pool = [p for p in self.profiles.values()
                if p.auto_eligible and (not needs_vision or p.supports_vision)]
        if free_only:
            pool = [p for p in pool if p.billed_cost_in == 0 and p.billed_cost_out == 0]
        if min_context:
            fitting = [p for p in pool if (p.context_window or 0) >= min_context]
            # If nothing fits, keep the largest windows first rather than refusing outright.
            pool = fitting or sorted(pool, key=lambda p: -(p.context_window or 0))[:3]
        return pool

    def virtual_context_length(self, profile_name: str) -> Optional[int]:
        """Largest window a virtual profile can resolve to; plan() skips models a request outgrows."""
        pool = self._pool(free_only=VIRTUAL_PROFILES.get(profile_name) == 0)
        contexts = [p.context_window for p in pool if p.context_window]
        return max(contexts) if contexts else None

    def _ordered(self, start_tier: int, needs_vision: bool, free_only: bool, min_context: int = 0,
                 bucket: Optional[str] = None) -> List[str]:
        pool = self._pool(free_only, needs_vision, min_context)
        learned = self.learner.reliability_map(bucket) if bucket else {}

        def key(p: VerifiedProfile):
            # Published benchmark scaled by learned reliability for this kind of request:
            # 0.5 (no evidence) keeps the benchmark; real failures/successes move it.
            quality = p.intelligence_index if p.intelligence_index is not None else UNKNOWN_QUALITY
            adjusted = quality * (0.5 + learned.get(p.model_id, 0.5))
            return (price_tier(p), -adjusted, p.billed_cost_in or 0.0, p.model_id)

        upper = sorted((p for p in pool if price_tier(p) >= start_tier), key=key)
        lower = sorted((p for p in pool if price_tier(p) < start_tier),
                       key=lambda p: (-price_tier(p),) + key(p)[1:])
        return [p.model_id for p in upper + lower]

    def plan(self, payload: Dict[str, Any], session_id: Optional[str] = None,
             now: Optional[float] = None) -> List[str]:
        return self.plan_with_context(payload, session_id, now)[0]

    def plan_with_context(self, payload: Dict[str, Any], session_id: Optional[str] = None,
                          now: Optional[float] = None):
        """Return (ordered candidates, bucket, start tier). Raises KeyError for unknown models."""
        requested = payload.get("model") or "oracle/auto"
        messages = payload.get("messages") or []
        kw_tier = keyword_tier(messages)
        bucket = bucket_for(payload, kw_tier)
        if requested not in VIRTUAL_PROFILES:
            if requested not in self.profiles:
                raise KeyError(requested)
            return [requested], bucket, kw_tier

        needs_vision = has_image(messages)
        fixed = VIRTUAL_PROFILES[requested]
        # oracle/auto: crude keyword guess, corrected by learned per-bucket floors + exploration.
        start = self.learner.start_tier(bucket, kw_tier, now=now) if fixed is None else max(fixed, 1)
        order = self._ordered(start, needs_vision, free_only=(fixed == 0),
                              min_context=estimate_tokens(payload), bucket=bucket)

        cooling = self.cooling_down(now)
        sticky = self.sticky_model(session_id)
        profile = self.profiles.get(sticky) if sticky else None
        if (profile and profile.auto_eligible and sticky in order and sticky not in cooling
                and (not needs_vision or profile.supports_vision) and price_tier(profile) >= start):
            order = [sticky] + [m for m in order if m != sticky]

        ordered = [m for m in order if m not in cooling] + [m for m in order if m in cooling]
        return ordered, bucket, start

    def prepare_payload(self, payload: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        out = copy.deepcopy(payload)
        out["model"] = model_id
        profile = self.profiles.get(model_id)
        if not profile or profile.status != "verified_metadata":
            return out  # no verified contract: leave caller parameters untouched
        if "reasoning_effort" in out:
            clamped = clamp_effort(profile, out["reasoning_effort"])
            if clamped is None:
                out.pop("reasoning_effort")
            else:
                out["reasoning_effort"] = clamped
        reasoning = out.get("reasoning")
        if isinstance(reasoning, dict) and "effort" in reasoning:
            clamped = clamp_effort(profile, reasoning["effort"])
            if clamped is None:
                reasoning.pop("effort")
            else:
                reasoning["effort"] = clamped
        return out
