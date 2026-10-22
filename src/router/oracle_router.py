"""Çok Kademeli Dinamik Model Yönlendirme (Cascading), Oracle ve Yarı Ömürlü Sönümleme Motoru."""
import math
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class OracleSignal:
    passed: bool
    channel: str = "strong"  # "strong" (weight 1.0) or "weak" (weight 0.25)
    reason: str = ""


class DynamicOracleRouter:
    """3 Kademeli Model Yönlendirici ve Yarı Ömürlü Sönümlü İstatistiksel Öğrenme Motoru."""

    CHANNEL_WEIGHTS = {
        "strong": 1.0,
        "weak": 0.25,
    }

    DEFAULT_TIERS: List[List[str]] = [
        ["google/gemini-3.7-flash:free", "qwen/qwen3.6-27b"],
        ["deepseek/deepseek-v4-pro", "openai/gpt-6-sol"],
        ["google/gemini-4-argon"],
    ]

    def __init__(
        self,
        db_path: str = ":memory:",
        half_life_seconds: float = 3600.0,
        tiers: Optional[List[List[str]]] = None,
    ) -> None:
        self.db_path = db_path
        self.half_life_seconds = max(1.0, float(half_life_seconds))
        self.tiers = tiers or [list(t) for t in self.DEFAULT_TIERS]
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.commit()

    def record_outcome(
        self,
        model_id: str,
        passed: bool,
        channel: str = "strong",
        timestamp: Optional[float] = None,
    ) -> None:
        ts = time.time() if timestamp is None else float(timestamp)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO model_outcomes (model_id, passed, channel, timestamp) VALUES (?, ?, ?, ?)",
                (model_id, 1 if passed else 0, channel, ts),
            )
            conn.commit()

    def get_model_score(self, model_id: str, now: Optional[float] = None) -> float:
        """Yarı ömürlü sönümleme ($2^{-\\Delta t / T_{1/2}}$) ile güncel başarı puanını hesaplar."""
        current_time = time.time() if now is None else float(now)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT passed, channel, timestamp FROM model_outcomes WHERE model_id = ?",
                (model_id,),
            ).fetchall()

        if not rows:
            return 0.0

        weighted_sum = 0.0
        for passed, channel, ts in rows:
            age = max(0.0, current_time - float(ts))
            decay = math.pow(2.0, -age / self.half_life_seconds)
            ch_weight = self.CHANNEL_WEIGHTS.get(channel, 0.25)
            direction = 1.0 if passed else -1.0
            weighted_sum += direction * ch_weight * decay

        return weighted_sum

    def select_best_in_tier(self, tier_models: List[str], now: Optional[float] = None) -> str:
        return max(tier_models, key=lambda m: self.get_model_score(m, now=now))

    def route_and_execute(
        self,
        prompt: str,
        task_type: str,
        executor: Callable[[str, str], str],
        oracle_validator: Callable[[str], OracleSignal],
    ) -> Dict[str, Any]:
        """En düşük maliyetli kademeden başlayarak Oracle doğrulaması geçene kadar kademeli yükseltir."""
        attempts: List[Dict[str, Any]] = []
        now = time.time()

        for tier_index, tier_models in enumerate(self.tiers, start=1):
            candidate = self.select_best_in_tier(tier_models, now=now)
            output = executor(candidate, prompt)
            signal = oracle_validator(output)
            self.record_outcome(
                candidate, passed=signal.passed, channel=signal.channel, timestamp=now
            )
            attempts.append(
                {
                    "tier": tier_index,
                    "model": candidate,
                    "passed": signal.passed,
                    "channel": signal.channel,
                }
            )
            if signal.passed:
                return {
                    "final_model": candidate,
                    "tier_reached": tier_index,
                    "output": output,
                    "attempts": attempts,
                }

        return {
            "final_model": attempts[-1]["model"] if attempts else "",
            "tier_reached": len(self.tiers),
            "output": output if attempts else "",
            "attempts": attempts,
        }
