"""Self-evolving routing signals from real traffic — zero extra inference cost.

Signals (all observable at the proxy):
  * structural: malformed tool-call JSON, calls to tools the request did not offer, empty
    answers -> immediate negative. A well-formed response alone is *not* counted as a win.
  * implicit user feedback, attributed when the next user message in the session arrives:
      - same last user message re-sent with no new history (regenerate/retry) -> -1.0
      - correction phrasing ("yanlış", "olmadı", "that's wrong", ...)          -> -0.5
      - conversation continues after a final answer                           -> +0.5
    Tool-loop iterations (next message is a tool result) are neutral.

What is learned (exponentially decayed evidence, default half-life 14 days):
  * reliability(model, bucket)        -> reorders candidates inside a price tier;
  * start tier per bucket             -> the crude keyword guess is raised when a tier keeps
    failing for that bucket; decay and epsilon-exploration (one tier lower) let it come back
    down when the evidence fades or cheaper tiers start succeeding.
Every floor change is written to ``evolution_events`` ("remember the decision").
"""
import contextlib
import hashlib
import json
import os
import random
import re
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.router.request_features import estimate_tokens, has_image, last_user_message, message_text

CORRECTION_RE = re.compile(
    r"\b(yanl[ıi]ş|olmad[ıi]|hatal[ıi]|çal[ıi]şm[ıi]yor|calismiyor|hay[ıi]r|değil|degil|"
    r"wrong|incorrect|doesn'?t work|not working|that'?s not)\b",
    re.IGNORECASE,
)

MIN_EVIDENCE = 5.0        # decayed observations before a tier floor may move
FLOOR_THRESHOLD = 0.4     # bucket-tier reliability below this raises the floor
WEIGHTS = {"user_retry": 1.0, "user_correction": 0.5, "continued": 0.5}


def is_correction(text: str) -> bool:
    return bool(CORRECTION_RE.search(text or ""))


def bucket_for(payload: Dict[str, Any], keyword_tier: int) -> str:
    messages = payload.get("messages") or []
    tokens = estimate_tokens(payload)
    size = "s" if tokens < 16000 else "m" if tokens < 64000 else "l"
    return f"t{keyword_tier}:{'img' if has_image(messages) else 'txt'}:{size}"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join((p.get("text") or "") for p in content if isinstance(p, dict)).strip()
    return ""


def analyze_response(body: Dict[str, Any], tools: Optional[List[Dict[str, Any]]]) -> Tuple[bool, bool, str]:
    """Return (structurally_ok, is_final_answer, reason)."""
    choices = body.get("choices") if isinstance(body, dict) else None
    if not choices:
        return False, False, "no_choices"
    message = choices[0].get("message") or {}
    calls = message.get("tool_calls") or []
    if calls:
        allowed = {t.get("function", {}).get("name") for t in tools or [] if isinstance(t, dict)}
        for call in calls:
            fn = call.get("function") or {}
            if allowed and fn.get("name") not in allowed:
                return False, False, "unknown_tool"
            try:
                if not isinstance(json.loads(fn.get("arguments") or "{}"), dict):
                    return False, False, "malformed_tool_arguments"
            except ValueError:
                return False, False, "malformed_tool_arguments"
        return True, False, "tool_calls_ok"
    if _text_of(message.get("content")):
        return True, True, "answer"
    return False, False, "empty_answer"


class StreamAccumulator:
    """Rebuilds the final assistant message from OpenAI SSE chunks."""

    def __init__(self) -> None:
        self.content: List[str] = []
        self.calls: Dict[int, Dict[str, Any]] = {}
        self.finish_reason: Optional[str] = None

    def feed(self, line: bytes) -> None:
        line = line.strip()
        if not line.startswith(b"data:"):
            return
        data = line[5:].strip()
        if not data or data == b"[DONE]":
            return
        try:
            chunk = json.loads(data)
        except ValueError:
            return
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                self.content.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                slot = self.calls.setdefault(int(tc.get("index", 0)), {"function": {"name": "", "arguments": ""}})
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if isinstance(fn.get("arguments"), str):
                    slot["function"]["arguments"] += fn["arguments"]
            self.finish_reason = choice.get("finish_reason") or self.finish_reason

    def as_response(self) -> Dict[str, Any]:
        message: Dict[str, Any] = {"role": "assistant", "content": "".join(self.content) or None}
        if self.calls:
            message["tool_calls"] = [self.calls[i] for i in sorted(self.calls)]
        return {"choices": [{"message": message, "finish_reason": self.finish_reason}]}


class OutcomeLearner:
    def __init__(self, db_path: str, half_life_days: float = 14.0, epsilon: float = 0.05,
                 rng: Callable[[], float] = random.random,
                 clock: Callable[[], float] = time.time) -> None:
        self.db_path = db_path
        self.clock = clock
        self.half_life = half_life_days * 86400.0
        self.epsilon = epsilon
        self.rng = rng
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_bucket_stats (
                    model_id TEXT, bucket TEXT, pos REAL, neg REAL, updated_at REAL,
                    PRIMARY KEY (model_id, bucket));
                CREATE TABLE IF NOT EXISTS bucket_tier_stats (
                    bucket TEXT, tier INTEGER, pos REAL, neg REAL, updated_at REAL,
                    PRIMARY KEY (bucket, tier));
                CREATE TABLE IF NOT EXISTS bucket_floors (bucket TEXT PRIMARY KEY, floor INTEGER, updated_at REAL);
                CREATE TABLE IF NOT EXISTS pending_feedback (
                    session_id TEXT PRIMARY KEY, model_id TEXT, bucket TEXT, tier INTEGER,
                    final_answer INTEGER, user_hash TEXT, msg_count INTEGER, ts REAL);
                CREATE TABLE IF NOT EXISTS outcome_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, model_id TEXT, bucket TEXT,
                    tier INTEGER, pos REAL, neg REAL, reason TEXT);
                CREATE TABLE IF NOT EXISTS evolution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, bucket TEXT, detail TEXT);
                """
            )

    @contextlib.contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                yield conn
        finally:
            conn.close()

    # ---- evidence ----------------------------------------------------------------------
    def _decay(self, value: float, updated_at: float, now: float) -> float:
        return value * 0.5 ** (max(0.0, now - updated_at) / self.half_life)

    def _bump(self, conn, table: str, keys: Tuple[str, str], key_vals: tuple,
              pos: float, neg: float, now: float) -> None:
        where = f"{keys[0]}=? AND {keys[1]}=?"
        row = conn.execute(f"SELECT pos, neg, updated_at FROM {table} WHERE {where}", key_vals).fetchone()
        p = self._decay(row[0], row[2], now) + pos if row else pos
        n = self._decay(row[1], row[2], now) + neg if row else neg
        conn.execute(
            f"INSERT INTO {table} ({keys[0]}, {keys[1]}, pos, neg, updated_at) VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT({keys[0]}, {keys[1]}) DO UPDATE SET pos=excluded.pos, neg=excluded.neg, "
            f"updated_at=excluded.updated_at",
            (*key_vals, p, n, now),
        )

    def record(self, model_id: str, bucket: str, tier: int, pos: float = 0.0, neg: float = 0.0,
               reason: str = "", now: Optional[float] = None) -> None:
        now = self.clock() if now is None else now
        with self._conn() as conn:
            self._bump(conn, "model_bucket_stats", ("model_id", "bucket"), (model_id, bucket), pos, neg, now)
            self._bump(conn, "bucket_tier_stats", ("bucket", "tier"), (bucket, tier), pos, neg, now)
            conn.execute("INSERT INTO outcome_events (ts, model_id, bucket, tier, pos, neg, reason) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", (now, model_id, bucket, tier, pos, neg, reason))

    def _stats(self, table: str, keys: Tuple[str, str], key_vals: tuple, now: float) -> Tuple[float, float]:
        with self._conn() as conn:
            row = conn.execute(f"SELECT pos, neg, updated_at FROM {table} WHERE {keys[0]}=? AND {keys[1]}=?",
                               key_vals).fetchone()
        if not row:
            return 0.0, 0.0
        return self._decay(row[0], row[2], now), self._decay(row[1], row[2], now)

    def reliability(self, model_id: str, bucket: str, now: Optional[float] = None) -> float:
        """Posterior mean with a Beta(1,1) prior: 0.5 means 'no evidence either way'."""
        pos, neg = self._stats("model_bucket_stats", ("model_id", "bucket"), (model_id, bucket),
                               self.clock() if now is None else now)
        return (pos + 1.0) / (pos + neg + 2.0)

    def reliability_map(self, bucket: str, now: Optional[float] = None) -> Dict[str, float]:
        """All models with evidence in this bucket (one query, used on every routing decision)."""
        now = self.clock() if now is None else now
        with self._conn() as conn:
            rows = conn.execute("SELECT model_id, pos, neg, updated_at FROM model_bucket_stats WHERE bucket=?",
                                (bucket,)).fetchall()
        result = {}
        for mid, pos, neg, ts in rows:
            p, n = self._decay(pos, ts, now), self._decay(neg, ts, now)
            result[mid] = (p + 1.0) / (p + n + 2.0)
        return result

    # ---- tier floors -------------------------------------------------------------------
    def start_tier(self, bucket: str, keyword_tier: int, now: Optional[float] = None) -> int:
        now = self.clock() if now is None else now
        tier = keyword_tier
        while tier < 4:
            pos, neg = self._stats("bucket_tier_stats", ("bucket", "tier"), (bucket, tier), now)
            if pos + neg >= MIN_EVIDENCE and (pos + 1.0) / (pos + neg + 2.0) < FLOOR_THRESHOLD:
                tier += 1
            else:
                break
        self._remember_floor(bucket, keyword_tier, tier, now)
        if tier > 1 and self.rng() < self.epsilon:
            return tier - 1  # explore: lets an over-cautious floor earn its way back down
        return tier

    def _remember_floor(self, bucket: str, keyword_tier: int, floor: int, now: float) -> None:
        with self._conn() as conn:
            row = conn.execute("SELECT floor FROM bucket_floors WHERE bucket=?", (bucket,)).fetchone()
            previous = row[0] if row else keyword_tier
            if previous == floor and row:
                return
            conn.execute("INSERT INTO bucket_floors VALUES (?, ?, ?) ON CONFLICT(bucket) DO UPDATE "
                         "SET floor=excluded.floor, updated_at=excluded.updated_at", (bucket, floor, now))
            if floor != previous:
                kind = "floor_raised" if floor > previous else "floor_lowered"
                conn.execute("INSERT INTO evolution_events (ts, kind, bucket, detail) VALUES (?, ?, ?, ?)",
                             (now, kind, bucket, json.dumps({"from": previous, "to": floor,
                                                             "keyword_tier": keyword_tier})))

    def evolution_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT ts, kind, bucket, detail FROM evolution_events ORDER BY id DESC LIMIT ?",
                                (limit,)).fetchall()
        return [{"ts": r[0], "kind": r[1], "bucket": r[2], "detail": json.loads(r[3])} for r in rows]

    def summary(self, now: Optional[float] = None, limit: int = 50) -> Dict[str, Any]:
        now = self.clock() if now is None else now
        with self._conn() as conn:
            models = conn.execute("SELECT model_id, bucket, pos, neg, updated_at FROM model_bucket_stats").fetchall()
            floors = conn.execute("SELECT bucket, floor FROM bucket_floors").fetchall()
            recent = conn.execute("SELECT reason, COUNT(*) FROM outcome_events GROUP BY reason").fetchall()
        rows = []
        for mid, bucket, pos, neg, ts in models:
            p, n = self._decay(pos, ts, now), self._decay(neg, ts, now)
            rows.append({"model": mid, "bucket": bucket, "evidence": round(p + n, 2),
                         "reliability": round((p + 1) / (p + n + 2), 3)})
        rows.sort(key=lambda r: -r["evidence"])
        return {"model_bucket": rows[:limit], "floors": dict(floors), "signal_counts": dict(recent),
                "evolution_events": self.evolution_events(limit)}

    # ---- implicit feedback -------------------------------------------------------------
    @staticmethod
    def last_user_hash(messages: List[Dict[str, Any]]) -> str:
        return hashlib.sha256(message_text(last_user_message(messages)).encode("utf-8")).hexdigest()

    def on_response(self, session_id: Optional[str], model_id: str, bucket: str, tier: int,
                    structural_ok: bool, final_answer: bool, last_user_hash: str, msg_count: int,
                    reason: str = "", now: Optional[float] = None) -> None:
        now = self.clock() if now is None else now
        if not structural_ok:
            self.record(model_id, bucket, tier, neg=1.0, reason=reason or "structural_failure", now=now)
        if not session_id:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO pending_feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
                "model_id=excluded.model_id, bucket=excluded.bucket, tier=excluded.tier, "
                "final_answer=excluded.final_answer, user_hash=excluded.user_hash, "
                "msg_count=excluded.msg_count, ts=excluded.ts",
                (session_id, model_id, bucket, tier, int(final_answer and structural_ok),
                 last_user_hash, msg_count, now),
            )

    def on_request(self, session_id: Optional[str], payload: Dict[str, Any], now: Optional[float] = None) -> Optional[str]:
        """Attribute implicit feedback for the session's previous response. Returns the signal."""
        if not session_id:
            return None
        messages = payload.get("messages") or []
        if not messages or messages[-1].get("role") != "user":
            return None  # tool-loop iteration: neutral, keep pending state
        with self._conn() as conn:
            row = conn.execute("SELECT model_id, bucket, tier, final_answer, user_hash, msg_count "
                               "FROM pending_feedback WHERE session_id=?", (session_id,)).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM pending_feedback WHERE session_id=?", (session_id,))
        model_id, bucket, tier, final_answer, user_hash, msg_count = row
        signal = None
        if self.last_user_hash(messages) == user_hash and len(messages) <= msg_count:
            signal = "user_retry"
        elif is_correction(message_text(messages[-1])):
            signal = "user_correction"
        elif final_answer:
            signal = "continued"
        if signal:
            weight = WEIGHTS[signal]
            self.record(model_id, bucket, tier, pos=weight if signal == "continued" else 0.0,
                        neg=0.0 if signal == "continued" else weight, reason=signal, now=now)
        return signal
