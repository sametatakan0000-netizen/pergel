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
  3. Inventory filter: a candidate that another candidate Pareto-dominates (no better on any
     verified axis: price in/out, intelligence index, context window — strictly worse on at
     least one) is demoted to a last-resort fallback and can only run when the primary pool
     is exhausted. Unknown values never dominate: no fabricated quality claims. Only a model
     with a real 200 on record may dominate — untried metadata promising a half-price twin
     must never demote a working model (observed: unserved ``:batch`` variants 404 upstream).
  4. Order: tiers >= start (ascending), then intelligence bands — adjusted Artificial
     Analysis indexes within QUALITY_TOLERANCE points count as EQUAL — inside a band a model
     with a proven 200 leads never-served candidates, then lower price (in, out). Lower tiers
     follow as last-resort fallbacks. Models cooling down after 429/5xx/404 move to the end;
     repeated 404s back off exponentially.
  5. Session affinity is persisted in SQLite. The pin survives while the turn demands a
     comparable price tier (STICKY_TIER_GRACE) and no cheaper candidate sits within
     QUALITY_TOLERANCE of it (prompt-cache survival); easier turns release the pin instead
     of riding an expensive model for the rest of the session.
"""
import contextlib
import copy
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from src.router.model_registry import VerifiedProfile, clamp_effort
from src.router.context_governor import advised_context_length
from src.router.outcome_learning import OutcomeLearner, bucket_for
from src.router.request_features import estimate_tokens, has_image, keyword_tier

# Advertised to the client picker: one id. Everything else is an alias kept for
# compatibility/forcing, not a feature — plan() decides the band on its own.
ADVERTISED_MODELS = ("oracle/auto",)

VIRTUAL_PROFILES = {
    "oracle/auto": None,  # classified per request
    "oracle/eco": 1,
    "oracle/agentic": 2,
    "oracle/premium": 4,
    "oracle/free": 0,     # special: zero list price only
}

COOLDOWN_SECONDS = {429: 300, 404: 3600}
SERVER_ERROR_COOLDOWN = 300
MAX_COOLDOWN_SECONDS = 86400  # repeated 404s back off exponentially up to one day
QUALITY_TOLERANCE = 5.0       # AA intelligence-index points: inside a band, price decides
STICKY_TIER_GRACE = 1         # a pinned model survives turns at most one price tier easier

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


def adjusted_quality(profile: VerifiedProfile, learned: Dict[str, float]) -> float:
    """Published benchmark scaled by learned reliability for this request bucket:
    0.5 (no evidence) keeps the benchmark; real failures/successes move it."""
    quality = profile.intelligence_index if profile.intelligence_index is not None else UNKNOWN_QUALITY
    return quality * (0.5 + learned.get(profile.model_id, 0.5))


def dominates(q: VerifiedProfile, p: VerifiedProfile) -> bool:
    """True when ``q`` Pareto-dominates ``p``: no worse on every verified axis and strictly
    better on at least one. Unknown benchmark/prices/window never dominate (no guesses)."""
    if None in (q.intelligence_index, p.intelligence_index, q.billed_cost_in, p.billed_cost_in,
                q.billed_cost_out, p.billed_cost_out, q.context_window, p.context_window):
        return False
    no_worse = (q.intelligence_index >= p.intelligence_index and q.billed_cost_in <= p.billed_cost_in
                and q.billed_cost_out <= p.billed_cost_out and q.context_window >= p.context_window)
    strictly_better = (q.intelligence_index > p.intelligence_index or q.billed_cost_in < p.billed_cost_in
                       or q.billed_cost_out < p.billed_cost_out or q.context_window > p.context_window)
    return no_worse and strictly_better


def prune_dominated(pool: List[VerifiedProfile], dead: Optional[set] = None,
                    served: Optional[set] = None):
    """Split the pool into (primary, dominated). Dominated models are never worth picking
    while their dominator runs, so they stay reachable only as very last resort. Only served
    models (a real 200 on record, unless ``served`` is None) may dominate; ``dead`` models
    (all-404, never served) may not. Metadata alone cannot demote a working model — phantom
    half-price variants must not push proven models out of the primary pool."""
    dead = dead or set()
    dominators = [p for p in pool
                  if p.model_id not in dead and (served is None or p.model_id in served)]
    primary: List[VerifiedProfile] = []
    dominated: List[VerifiedProfile] = []
    for p in pool:
        if any(dominates(q, p) for q in dominators if q is not p):
            dominated.append(p)
        else:
            primary.append(p)
    return primary, dominated


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
            if cooldown and status == 404:
                # A model that keeps 404ing upstream (e.g. unserved variants) backs off
                # exponentially up to a day instead of re-probing every hour forever.
                streak = 0
                for (s,) in conn.execute(
                        "SELECT status FROM upstream_events WHERE model_id=? ORDER BY id DESC LIMIT 50",
                        (model_id,)).fetchall():
                    if s != 404:
                        break
                    streak += 1
                cooldown = min(cooldown * 2 ** (streak - 1), MAX_COOLDOWN_SECONDS)
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

    def dead_models(self) -> set:
        """Models with at least one 404 and zero successes on record: the upstream does not
        serve them (observed fact, e.g. unserved variants). They cannot dominate in the
        inventory filter; a single later 200 revives them."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT model_id, SUM(status = 200), SUM(status = 404) FROM upstream_events "
                "GROUP BY model_id").fetchall()
        return {mid for mid, wins, misses in rows if not wins and misses}

    def served_models(self) -> set:
        """Models with at least one real 200: the only ones trusted to dominate peers or to
        outrank never-tried candidates inside a tolerance band."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT model_id FROM upstream_events WHERE status = 200").fetchall()
        return {r[0] for r in rows}

    def spent_since(self, since: float, now: Optional[float] = None) -> float:
        """USD actually billed since ``since``, from recorded usage and known prices.

        Only 200 events with token counts count; a model without published prices is
        skipped rather than guessed, so the figure is a lower bound on real spend.
        """
        now = time.time() if now is None else now
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT model_id, COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0) "
                "FROM upstream_events WHERE status = 200 AND ts >= ? AND ts <= ? GROUP BY model_id",
                (since, now)).fetchall()
        total = 0.0
        for model_id, prompt_tokens, completion_tokens in rows:
            profile = self.profiles.get(model_id)
            if profile is None or profile.billed_cost_in is None or profile.billed_cost_out is None:
                continue
            total += (prompt_tokens * profile.billed_cost_in
                      + completion_tokens * profile.billed_cost_out) / 1_000_000
        return total

    def spent_today(self, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        midnight = now - (now % 86400)  # UTC day boundary
        return self.spent_since(midnight, now=now)

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
    def _overpaying(self, sticky: VerifiedProfile, natural: VerifiedProfile,
                    learned: Dict[str, float]) -> bool:
        """True when the natural pick is strictly cheaper and statistically indistinguishable
        from the pinned model (within QUALITY_TOLERANCE on adjusted quality): the pin would
        only buy a benchmark difference nobody can see, at a price everybody can."""
        if (price_tier(sticky), sticky.billed_cost_in or 0.0, sticky.billed_cost_out or 0.0) <= \
                (price_tier(natural), natural.billed_cost_in or 0.0, natural.billed_cost_out or 0.0):
            return False
        return abs(adjusted_quality(sticky, learned) - adjusted_quality(natural, learned)) \
            <= QUALITY_TOLERANCE

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
        """Window advertised for a virtual profile: pool maximum capped at ORACLE_EFFECTIVE_CONTEXT
        (default 200K) so Hermes compresses at an economic size, not at the 1M+ real maximum."""
        pool = self._pool(free_only=VIRTUAL_PROFILES.get(profile_name) == 0)
        return advised_context_length([p.context_window for p in pool])

    def _ordered(self, start_tier: int, needs_vision: bool, free_only: bool, min_context: int = 0,
                 learned: Optional[Dict[str, float]] = None) -> List[str]:
        pool = self._pool(free_only, needs_vision, min_context)
        served = self.served_models()
        primary, dominated = prune_dominated(pool, self.dead_models(), served)
        learned = learned or {}

        def key(p: VerifiedProfile):
            # Inside a tolerance band: a model that actually served beats never-tried
            # candidates first (phantom cheap variants must not lead while proven ones work).
            return (price_tier(p), 0 if p.model_id in served else 1,
                    p.billed_cost_in or 0.0, p.billed_cost_out or 0.0,
                    -adjusted_quality(p, learned), p.model_id)

        def band_sorted(models: List[VerifiedProfile]) -> List[VerifiedProfile]:
            """Group near-equal adjusted quality into bands (leader - member <=
            QUALITY_TOLERANCE); inside a band the cheaper model wins. A 2-point
            benchmark lead must not justify a 2x price."""
            ranked = sorted(models, key=lambda p: (-adjusted_quality(p, learned), p.model_id))
            bands: List[List[VerifiedProfile]] = []
            for p in ranked:
                if bands and adjusted_quality(bands[0][0], learned) - adjusted_quality(p, learned) \
                        <= QUALITY_TOLERANCE:
                    bands[-1].append(p)
                else:
                    bands.append([p])
            return [p for band in bands for p in sorted(band, key=key)]

        def segment(models: List[VerifiedProfile]) -> List[VerifiedProfile]:
            # Price tier stays the primary key across tiers (the difficulty classifier is the
            # spend dial); tolerance bands only arbitrate INSIDE a tier. Tiers >= start come
            # first ascending; cheaper tiers follow as last-resort fallbacks.
            def by_tier(pool_: List[VerifiedProfile], descending: bool = False) -> List[VerifiedProfile]:
                out: List[VerifiedProfile] = []
                for t in sorted({price_tier(p) for p in pool_}, reverse=descending):
                    out += band_sorted([p for p in pool_ if price_tier(p) == t])
                return out

            return (by_tier([p for p in models if price_tier(p) >= start_tier])
                    + by_tier([p for p in models if price_tier(p) < start_tier], descending=True))

        return [p.model_id for p in segment(primary) + segment(dominated)]

    def plan(self, payload: Dict[str, Any], session_id: Optional[str] = None,
             now: Optional[float] = None) -> List[str]:
        return self.plan_with_context(payload, session_id, now)[0]

    def normalize_model(self, model: Optional[str]) -> str:
        """Strip leaked client-side provider prefixes (``custom:``, ``oracle-router:``).

        Only *leading* ``name:`` segments without ``/`` are removed, and only while the
        current string is unknown — suffixes like ``:free``/``:batch`` stay intact.
        """
        m = model or "oracle/auto"
        while m not in VIRTUAL_PROFILES and m not in self.profiles and ":" in m:
            head, rest = m.split(":", 1)
            if "/" in head or not rest:
                break
            m = rest
        return m

    def plan_with_context(self, payload: Dict[str, Any], session_id: Optional[str] = None,
                          now: Optional[float] = None):
        """Return (ordered candidates, bucket, start tier). Raises KeyError for unknown models."""
        requested = self.normalize_model(payload.get("model"))
        messages = payload.get("messages") or []
        kw_tier = keyword_tier(messages)
        bucket = bucket_for(payload, kw_tier)
        if requested not in VIRTUAL_PROFILES:
            if requested not in self.profiles:
                raise KeyError(requested)
            return [requested], bucket, kw_tier

        needs_vision = has_image(messages)
        fixed = VIRTUAL_PROFILES[requested]
        learned = self.learner.reliability_map(bucket) if bucket else {}
        # oracle/auto: crude keyword guess, corrected by learned per-bucket floors + exploration.
        start = self.learner.start_tier(bucket, kw_tier, now=now) if fixed is None else max(fixed, 1)
        order = self._ordered(start, needs_vision, free_only=(fixed == 0),
                              min_context=estimate_tokens(payload), learned=learned)

        cooling = self.cooling_down(now)
        sticky = self.sticky_model(session_id)
        profile = self.profiles.get(sticky) if sticky else None
        if (profile and profile.auto_eligible and sticky in order and sticky not in cooling
                and (not needs_vision or profile.supports_vision)
                and start <= price_tier(profile) <= start + STICKY_TIER_GRACE
                and not self._overpaying(profile, self.profiles[order[0]], learned)):
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
