"""Çok Kademeli Self-Evolving Dinamik Model Yönlendirme (Cascading), Canlı Nous Portal 57+ Model Kataloğu ve OpenAI-Compatible Custom Proxy Motoru."""
from dataclasses import asdict, dataclass
import json
import math
import os
import re
import sqlite3
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.devtools.self_evolution_engine import distill_evolution_record


@dataclass
class OracleSignal:
    passed: bool
    channel: str = "strong"  # "strong" (weight 1.0) or "weak" (weight 0.25)
    reason: str = ""


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    provider: str
    tier: int
    default_reasoning_effort: str  # "low" | "medium" | "high" | "xhigh"
    default_temperature: float
    input_cost_per_mtok: float
    output_cost_per_mtok: float
    supports_vision: bool
    supports_tools: bool
    sale_badge: str = ""
    is_silent_default: bool = False
    role_persona: str = ""
    strengths: Tuple[str, ...] = ()
    context_window: int = 0
    discount_pct: int = -1

    def __post_init__(self) -> None:
        lower = self.model_id.lower()
        if not self.role_persona:
            if "argon" in lower:
                persona = "Baş Mimar & Multimodal Amiral Gemisi (50% OFF Flagship)"
            elif "fable" in lower or "opus" in lower or "astra" in lower:
                persona = "Apex Derin Muhakeme & Tersine Mühendislik (Tier 4 Hakemi)"
            elif "deepseek" in lower and "pro" in lower:
                persona = "Kıdemli Kodlama & Exploit Sentez Uzmanı"
            elif "glm-5.2" in lower:
                persona = "Nous Portal Sessiz Varsayılan Ajan & MCP Orkestratörü"
            elif self.input_cost_per_mtok == 0.0:
                persona = "Sıfır Maliyetli Yüksek Hızlı Yardımcı (Free Portal Model)"
            elif self.tier == 1:
                persona = "Düşük Gecikmeli Ön Eleme, Özetleme & Sınıflandırma Ajanı"
            elif self.tier == 2:
                persona = "Çok Adımlı Ajan Kodlama & Araç Çağrısı Uzmanı"
            else:
                persona = "Üst Kademe Mimari Sentez & Doğrulama Modeli"
            object.__setattr__(self, "role_persona", persona)

        if not self.strengths:
            tags = ["tool_calling"] if self.supports_tools else []
            if self.supports_vision:
                tags.append("multimodal_vision")
            if self.input_cost_per_mtok == 0.0:
                tags.append("zero_cost_free")
            if "deepseek" in lower or "qwen" in lower or "sol" in lower:
                tags.append("code_generation")
            if self.tier >= 3:
                tags.append("deep_architecture")
            object.__setattr__(self, "strengths", tuple(tags))

        if self.context_window <= 0:
            if "argon" in lower or "gemini" in lower:
                ctx = 1000000
            elif "sol" in lower:
                ctx = 900000
            elif "claude" in lower or "gpt-" in lower or "grok" in lower:
                ctx = 256000
            else:
                ctx = 128000
            object.__setattr__(self, "context_window", ctx)

        if self.discount_pct < 0:
            m = re.search(r"(\d+)%\s*OFF", self.sale_badge, re.IGNORECASE)
            if m:
                disc = int(m.group(1))
            elif "50% Promo" in self.sale_badge:
                disc = 50
            elif self.input_cost_per_mtok == 0.0:
                disc = 100
            else:
                disc = 0
            object.__setattr__(self, "discount_pct", disc)


# Resmi https://hermes-agent.nousresearch.com/docs/api/model-catalog.json -> providers.nous.models (57 Küratörlü Ajan Modeli)
NOUS_CURATED_CATALOG_IDS: List[str] = [
    "anthropic/claude-fable-5.1",
    "anthropic/claude-fable-5",
    "anthropic/claude-opus-5.5",
    "anthropic/claude-opus-5",
    "anthropic/claude-opus-4.8",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-sonnet-5",
    "anthropic/claude-haiku-5.5",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-6-astra",
    "openai/gpt-6-astra-fast",
    "openai/gpt-6-astra-flex",
    "openai/gpt-6-astra-pro",
    "openai/gpt-6-astra-pro-fast",
    "openai/gpt-6-astra-pro-flex",
    "openai/gpt-6.1-sol",
    "openai/gpt-6.1-sol-pro",
    "openai/gpt-6-sol",
    "openai/gpt-6-sol-pro",
    "openai/gpt-6-luna",
    "openai/gpt-6-luna-pro",
    "openai/gpt-5.5",
    "openai/gpt-5.5-pro",
    "openai/gpt-5.4-mini",
    "google/gemini-4-argon",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3.8-flash",
    "google/gemini-3.7-flash",
    "x-ai/grok-4.7",
    "x-ai/grok-4.6",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-pro-0813",
    "deepseek/deepseek-v4.1-flash",
    "deepseek/deepseek-v4.1-flash-1017",
    "deepseek/deepseek-v4-flash-0731",
    "qwen/qwen3.8-max-0902",
    "qwen/qwen3.8-flash",
    "moonshotai/kimi-k3",
    "minimax/minimax-m3",
    "z-ai/glm-5.3",
    "z-ai/glm-5.3-flash",
    "z-ai/glm-5.3-flashx",
    "z-ai/glm-5.2",
    "xiaomi/mimo-v2.6-pro",
    "xiaomi/mimo-v2.6-flash",
    "xiaomi/mimo-v2.6-pro-ultraspeed",
    "xiaomi/mimo-v2.5-pro",
    "tencent/hy4-preview",
    "tencent/hy3",
    "stepfun/step-3.7-flash",
    "nvidia/nemotron-3-super-120b-a12b",
    "meta/muse-spark-1.2",
    "meta/muse-spark-1.3",
    "sakana/fugu-ultra",
    "upstage/solar-pro4",
    "upstage/solar-mini4",
    "stealth/space-bunny-alpha",
]

# Canlı https://portal.nousresearch.com/models fiyat, indirim (Active Promos) ve Free (Ücretsiz) model verileri
_EXPLICIT_PORTAL_PROFILES: Dict[str, ModelProfile] = {
    # FREE & ULTRA-CHEAP PROMO TIER (Tier 1)
    "meituan/longcat-2.5-preview": ModelProfile(
        "meituan/longcat-2.5-preview", "nous", 1, "low", 0.3, 0.0, 0.0, False, True, "FREE (#1 Usage)"
    ),
    "upstage/solar-mini4": ModelProfile(
        "upstage/solar-mini4", "nous", 1, "low", 0.3, 0.0, 0.0, False, True, "FREE / 50% Promo"
    ),
    "poolside/laguna-s-2.1": ModelProfile(
        "poolside/laguna-s-2.1", "nous", 1, "low", 0.25, 0.0, 0.0, False, True, "FREE"
    ),
    "poolside/laguna-xs-2.1": ModelProfile(
        "poolside/laguna-xs-2.1", "nous", 1, "low", 0.25, 0.0, 0.0, False, True, "FREE"
    ),
    "reflection/beam-1.0-501b-a23b": ModelProfile(
        "reflection/beam-1.0-501b-a23b", "nous", 1, "low", 0.25, 0.0, 0.0, False, True, "FREE"
    ),
    "ornith/ornith-1.5-122b": ModelProfile(
        "ornith/ornith-1.5-122b", "nous", 1, "low", 0.25, 0.0, 0.0, False, True, "FREE"
    ),
    "stealth/space-bunny-alpha": ModelProfile(
        "stealth/space-bunny-alpha", "nous", 1, "low", 0.25, 0.0, 0.0, False, True, "FREE Stealth"
    ),
    "google/gemini-3.7-flash:free": ModelProfile(
        "google/gemini-3.7-flash:free", "nous", 1, "low", 0.3, 0.0, 0.0, True, True, "FREE Alias"
    ),
    "qwen/qwen3.8-27b": ModelProfile(
        "qwen/qwen3.8-27b", "nous", 1, "low", 0.25, 0.02, 0.50, False, True, "95% OFF Promo"
    ),
    "qwen/qwen3.6-27b": ModelProfile(
        "qwen/qwen3.6-27b", "nous", 1, "low", 0.25, 0.25, 2.00, False, True, "44% OFF Promo"
    ),
    "deepseek/deepseek-v4.1-flash-1017": ModelProfile(
        "deepseek/deepseek-v4.1-flash-1017", "nous", 1, "low", 0.2, 0.07, 0.50, False, True, "53% OFF (#2 Usage)"
    ),
    "deepseek/deepseek-v4-flash-0731": ModelProfile(
        "deepseek/deepseek-v4-flash-0731", "nous", 1, "low", 0.2, 0.05, 0.45, False, True, ""
    ),
    "deepseek/deepseek-v4.1-flash": ModelProfile(
        "deepseek/deepseek-v4.1-flash", "nous", 1, "low", 0.2, 0.11, 0.51, False, True, ""
    ),
    "openai/gpt-6-luna": ModelProfile(
        "openai/gpt-6-luna", "nous", 1, "low", 0.25, 0.10, 0.50, True, True, ""
    ),
    "openai/gpt-6-luna-pro": ModelProfile(
        "openai/gpt-6-luna-pro", "nous", 1, "low", 0.25, 0.10, 0.50, True, True, ""
    ),
    "anthropic/claude-haiku-5.5": ModelProfile(
        "anthropic/claude-haiku-5.5", "nous", 1, "low", 0.25, 0.10, 0.50, True, True, ""
    ),
    "anthropic/claude-haiku-4.5": ModelProfile(
        "anthropic/claude-haiku-4.5", "nous", 1, "low", 0.25, 0.10, 0.50, True, True, ""
    ),
    "xiaomi/mimo-v2.6-flash": ModelProfile(
        "xiaomi/mimo-v2.6-flash", "nous", 1, "low", 0.25, 0.10, 0.28, False, True, "29% OFF"
    ),
    "z-ai/glm-5.3-flash": ModelProfile(
        "z-ai/glm-5.3-flash", "nous", 1, "low", 0.25, 0.12, 0.40, False, True, "20% OFF"
    ),
    "qwen/qwen3.8-flash": ModelProfile(
        "qwen/qwen3.8-flash", "nous", 1, "low", 0.25, 0.15, 0.47, False, True, ""
    ),
    "upstage/solar-pro4": ModelProfile(
        "upstage/solar-pro4", "nous", 1, "low", 0.25, 0.15, 0.60, False, True, "50% OFF"
    ),
    "tencent/hy3": ModelProfile(
        "tencent/hy3", "nous", 1, "low", 0.25, 0.08, 0.33, False, True, ""
    ),
    # SPECIALIST CODING & AGENTIC TIER (Tier 2)
    "deepseek/deepseek-v4-pro": ModelProfile(
        "deepseek/deepseek-v4-pro", "nous", 2, "medium", 0.2, 0.13, 1.89, False, True, "Specialist Coder"
    ),
    "deepseek/deepseek-v4-pro-0813": ModelProfile(
        "deepseek/deepseek-v4-pro-0813", "nous", 2, "medium", 0.2, 0.13, 8.00, False, True, ""
    ),
    "minimax/minimax-m3": ModelProfile(
        "minimax/minimax-m3", "nous", 2, "medium", 0.2, 0.23, 0.96, False, True, "23% OFF"
    ),
    "moonshotai/kimi-k3": ModelProfile(
        "moonshotai/kimi-k3", "nous", 2, "medium", 0.2, 0.24, 24.00, False, True, "Recommended"
    ),
    "xiaomi/mimo-v2.6-pro": ModelProfile(
        "xiaomi/mimo-v2.6-pro", "nous", 2, "medium", 0.2, 0.37, 0.74, False, True, "15% OFF"
    ),
    "tencent/hy4-preview": ModelProfile(
        "tencent/hy4-preview", "nous", 2, "medium", 0.2, 0.42, 1.25, False, True, "44% OFF"
    ),
    "google/gemini-3.8-flash": ModelProfile(
        "google/gemini-3.8-flash", "nous", 2, "medium", 0.2, 0.75, 3.75, True, True, "50% OFF"
    ),
    "google/gemini-3.7-flash": ModelProfile(
        "google/gemini-3.7-flash", "nous", 2, "medium", 0.2, 0.75, 3.75, True, True, "50% OFF"
    ),
    "z-ai/glm-5.2": ModelProfile(
        "z-ai/glm-5.2", "nous", 2, "medium", 0.2, 0.90, 2.83, False, True, "Silent Default", is_silent_default=True
    ),
    "z-ai/glm-5.3": ModelProfile(
        "z-ai/glm-5.3", "nous", 2, "medium", 0.2, 0.91, 2.86, False, True, ""
    ),
    "openai/gpt-6-sol": ModelProfile(
        "openai/gpt-6-sol", "nous", 2, "medium", 0.2, 2.00, 10.00, True, True, ""
    ),
    "anthropic/claude-sonnet-5.5": ModelProfile(
        "anthropic/claude-sonnet-5.5", "nous", 2, "medium", 0.2, 2.00, 10.00, True, True, ""
    ),
    # FLAGSHIP MULTIMODAL & ARCHITECTURE TIER (Tier 3)
    "google/gemini-4-argon": ModelProfile(
        "google/gemini-4-argon", "nous", 3, "high", 0.2, 2.00, 10.00, True, True, "50% OFF Flagship"
    ),
    "openai/gpt-6.1-sol": ModelProfile(
        "openai/gpt-6.1-sol", "nous", 3, "high", 0.2, 2.00, 10.00, True, True, "900k Capable"
    ),
    "openai/gpt-6.1-sol-pro": ModelProfile(
        "openai/gpt-6.1-sol-pro", "nous", 3, "high", 0.15, 2.00, 10.00, True, True, ""
    ),
    "qwen/qwen3.8-max-0902": ModelProfile(
        "qwen/qwen3.8-max-0902", "nous", 3, "high", 0.2, 2.00, 6.00, True, True, ""
    ),
    "x-ai/grok-4.7": ModelProfile(
        "x-ai/grok-4.7", "nous", 3, "high", 0.2, 2.00, 6.00, True, True, ""
    ),
    # APEX RESERVE TIER (Tier 4)
    "anthropic/claude-opus-5.5": ModelProfile(
        "anthropic/claude-opus-5.5", "nous", 4, "high", 0.15, 4.00, 20.00, True, True, ""
    ),
    "anthropic/claude-opus-5": ModelProfile(
        "anthropic/claude-opus-5", "nous", 4, "high", 0.15, 5.00, 25.00, True, True, ""
    ),
    "anthropic/claude-opus-4.8": ModelProfile(
        "anthropic/claude-opus-4.8", "nous", 4, "high", 0.15, 5.00, 25.00, True, True, ""
    ),
    "openai/gpt-6-astra": ModelProfile(
        "openai/gpt-6-astra", "nous", 4, "high", 0.15, 10.00, 50.00, True, True, ""
    ),
    "anthropic/claude-fable-5": ModelProfile(
        "anthropic/claude-fable-5", "nous", 4, "xhigh", 0.1, 10.00, 50.00, True, True, ""
    ),
    "anthropic/claude-fable-5.1": ModelProfile(
        "anthropic/claude-fable-5.1", "nous", 4, "xhigh", 0.1, 10.00, 50.00, True, True, ""
    ),
}


def _build_full_nous_inventory() -> Dict[str, ModelProfile]:
    inv: Dict[str, ModelProfile] = dict(_EXPLICIT_PORTAL_PROFILES)
    for mid in NOUS_CURATED_CATALOG_IDS:
        if mid in inv:
            continue
        lower = mid.lower()
        supports_vision = any(
            v in lower for v in ("gemini", "gpt-", "claude", "grok", "vision")
        )
        if any(k in lower for k in ("flash", "mini", "haiku", "luna", "space-bunny")):
            tier, effort, temp, in_c, out_c = 1, "low", 0.25, 0.15, 0.50
        elif any(k in lower for k in ("astra", "opus", "fable")):
            tier, effort, temp, in_c, out_c = 4, "high", 0.15, 5.00, 25.00
        elif any(k in lower for k in ("argon", "sol", "grok", "max", "3.1-pro")):
            tier, effort, temp, in_c, out_c = 3, "high", 0.20, 2.00, 10.00
        else:
            tier, effort, temp, in_c, out_c = 2, "medium", 0.20, 0.50, 2.00

        inv[mid] = ModelProfile(
            model_id=mid,
            provider="nous",
            tier=tier,
            default_reasoning_effort=effort,
            default_temperature=temp,
            input_cost_per_mtok=in_c,
            output_cost_per_mtok=out_c,
            supports_vision=supports_vision,
            supports_tools=True,
        )
    return inv


NOUS_PORTAL_INVENTORY: Dict[str, ModelProfile] = _build_full_nous_inventory()


class DynamicOracleRouter:
    """Nous Portal 57+ Model Kataloğu, İnce Ayar Adaptasyonu ve OpenAI-Compatible Proxy Yönlendiricisi."""

    CHANNEL_WEIGHTS = {
        "strong": 1.0,
        "weak": 0.25,
    }

    REASONING_LADDER = ["low", "medium", "high", "xhigh"]

    DEFAULT_TIERS: List[List[str]] = [
        [
            "upstage/solar-mini4",
            "meituan/longcat-2.5-preview",
            "qwen/qwen3.8-27b",
            "deepseek/deepseek-v4.1-flash-1017",
            "openai/gpt-6-luna",
            "anthropic/claude-haiku-5.5",
            "qwen/qwen3.6-27b",
        ],
        [
            "deepseek/deepseek-v4-pro",
            "z-ai/glm-5.2",
            "minimax/minimax-m3",
            "google/gemini-3.8-flash",
            "openai/gpt-6-sol",
            "anthropic/claude-sonnet-5.5",
        ],
        [
            "google/gemini-4-argon",
            "openai/gpt-6.1-sol",
            "qwen/qwen3.8-max-0902",
            "x-ai/grok-4.7",
        ],
        [
            "anthropic/claude-opus-5.5",
            "anthropic/claude-opus-4.8",
            "openai/gpt-6-astra",
            "anthropic/claude-fable-5.1",
        ],
    ]

    TIER_DEMOTION_THRESHOLD = -1.5

    def __init__(
        self,
        db_path: str = ":memory:",
        half_life_seconds: float = 3600.0,
        tiers: Optional[List[List[str]]] = None,
        inventory: Optional[Dict[str, ModelProfile]] = None,
    ) -> None:
        self.db_path = db_path
        self.half_life_seconds = max(1.0, float(half_life_seconds))
        self.inventory: Dict[str, ModelProfile] = dict(inventory or NOUS_PORTAL_INVENTORY)
        self.tiers = tiers or [list(t) for t in self.DEFAULT_TIERS]
        self.session_sticky_models: Dict[str, str] = {}
        self._conn: Optional[sqlite3.Connection] = (
            sqlite3.connect(":memory:") if self.db_path == ":memory:" else None
        )
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    task_type TEXT NOT NULL DEFAULT 'general',
                    passed INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_tier_floors (
                    task_type TEXT PRIMARY KEY,
                    min_tier INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    compact_entry TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS discovered_models (model_id TEXT PRIMARY KEY, first_seen REAL NOT NULL)"
            )
            conn.commit()
            for (mid,) in conn.execute("SELECT model_id FROM discovered_models"):
                if mid not in self.inventory:
                    self._add_unverified_model(mid)
        finally:
            if self._conn is None:
                conn.close()

    def _add_unverified_model(self, mid: str) -> None:
        self.inventory[mid] = ModelProfile(
            model_id=mid, provider="nous", tier=2,
            default_reasoning_effort="medium", default_temperature=0.2,
            input_cost_per_mtok=-1.0, output_cost_per_mtok=-1.0,
            supports_vision=False, supports_tools=False,
        )
        self.tiers[1].append(mid)

    def refresh_catalog(self, url: str = "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json") -> List[str]:
        """Fetch curated IDs; persist additions, but leave capabilities/pricing unknown."""
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.load(response)
        if payload.get("version") != 1:
            raise ValueError("Unsupported model catalog schema")
        return self.sync_live_model_catalog(payload)

    def sync_live_model_catalog(self, catalog_payload: Dict[str, Any]) -> List[str]:
        """https://hermes-agent.nousresearch.com/docs/api/model-catalog.json verisinden yeni Nous modellerini otonom ekler."""
        nous_block = catalog_payload.get("providers", {}).get("nous", {})
        models = nous_block.get("models", [])
        if not isinstance(models, list) or any(
            not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
            or not entry["id"].strip() for entry in models
        ):
            raise ValueError("Nous curated catalog must contain model ID objects")
        added: List[str] = []
        now = time.time()
        for entry in models:
            mid = entry.get("id") if isinstance(entry, dict) else str(entry)
            if not mid or mid in self.inventory:
                continue
            self._add_unverified_model(mid)
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO discovered_models (model_id, first_seen) VALUES (?, ?)",
                    (mid, now),
                )
                conn.commit()
            finally:
                if self._conn is None:
                    conn.close()
            added.append(mid)

        if added:
            self._record_evolution(
                mode="CAPTURED",
                source="NousPortal:model-catalog.json",
                decision=f"Ingested {len(added)} new Nous Portal models into DynamicOracleRouter",
                evidence=", ".join(added[:5]),
                timestamp=now,
            )
        return added

    def record_outcome(
        self,
        model_id: str,
        passed: bool,
        channel: str = "strong",
        timestamp: Optional[float] = None,
        task_type: str = "general",
    ) -> None:
        ts = time.time() if timestamp is None else float(timestamp)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO model_outcomes (model_id, task_type, passed, channel, timestamp) VALUES (?, ?, ?, ?, ?)",
                (model_id, task_type, 1 if passed else 0, channel, ts),
            )
            conn.commit()
        finally:
            if self._conn is None:
                conn.close()

    def get_model_score(
        self,
        model_id: str,
        now: Optional[float] = None,
        task_type: Optional[str] = None,
    ) -> float:
        """Yarı ömürlü sönümleme ($2^{-\\Delta t / T_{1/2}}$) ile güncel başarı puanını hesaplar."""
        current_time = time.time() if now is None else float(now)
        conn = self._connect()
        try:
            if task_type:
                rows = conn.execute(
                    "SELECT passed, channel, timestamp FROM model_outcomes WHERE model_id = ? AND task_type = ?",
                    (model_id, task_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT passed, channel, timestamp FROM model_outcomes WHERE model_id = ?",
                    (model_id,),
                ).fetchall()
        finally:
            if self._conn is None:
                conn.close()

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

    def get_adaptive_tuning(
        self,
        model_id: str,
        task_type: str = "general",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Modelin görevdeki sönümlü başarısına göre reasoning_effort, temperature ve wire ayarlarını adapte eder."""
        profile = self.inventory.get(
            model_id,
            ModelProfile(
                model_id=model_id,
                provider="nous",
                tier=2,
                default_reasoning_effort="medium",
                default_temperature=0.2,
                input_cost_per_mtok=1.0,
                output_cost_per_mtok=3.0,
                supports_vision=False,
                supports_tools=True,
            ),
        )
        task_score = self.get_model_score(model_id, now=now, task_type=task_type)
        base_idx = (
            self.REASONING_LADDER.index(profile.default_reasoning_effort)
            if profile.default_reasoning_effort in self.REASONING_LADDER
            else 1
        )

        if task_score < -0.2:
            adapted_idx = min(len(self.REASONING_LADDER) - 1, base_idx + 1)
            adapted_temp = max(0.05, round(profile.default_temperature - 0.1, 2))
        else:
            adapted_idx = base_idx
            adapted_temp = profile.default_temperature

        return {
            "model_id": model_id,
            "provider": profile.provider,
            "reasoning_effort": self.REASONING_LADDER[adapted_idx],
            "temperature": adapted_temp,
            "supports_vision": profile.supports_vision,
            "supports_tools": profile.supports_tools,
            "input_cost_per_mtok": profile.input_cost_per_mtok,
            "output_cost_per_mtok": profile.output_cost_per_mtok,
            "sale_badge": profile.sale_badge,
            "role_persona": profile.role_persona,
            "strengths": list(profile.strengths),
            "context_window": profile.context_window,
            "discount_pct": profile.discount_pct,
            "anthropic_wire": "chat" if model_id.startswith("anthropic/") else "openai_chat",
        }

    def export_model_profiles_json(
        self, output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Tüm Nous Portal modellerinin kim-kimdir (persona, fiyat, indirim, yetenek) sicilini JSON olarak dışa aktarır."""
        profiles_dict: Dict[str, Any] = {}
        for mid, prof in sorted(self.inventory.items(), key=lambda kv: (kv[1].tier, kv[1].input_cost_per_mtok, kv[0])):
            d = asdict(prof)
            d["strengths"] = list(prof.strengths)
            # Catalog membership is known, but prices/capabilities/personas here are guesses.
            d["metadata_status"] = "unverified"
            d["live_score"] = round(self.get_model_score(mid), 4)
            profiles_dict[mid] = d

        payload: Dict[str, Any] = {
            "total_models": len(profiles_dict),
            "curated_catalog_count": len(NOUS_CURATED_CATALOG_IDS),
            "free_models": [
                mid for mid, p in self.inventory.items() if p.input_cost_per_mtok == 0.0
            ],
            "active_promos": {
                mid: p.sale_badge
                for mid, p in self.inventory.items()
                if p.sale_badge
            },
            "profiles": profiles_dict,
        }
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload

    def get_task_tier_floor(self, task_type: str, now: Optional[float] = None) -> int:
        """Görev tipine göre öğrenilmiş minimum başlangıç kademesini döner."""
        current_time = time.time() if now is None else float(now)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT min_tier, updated_at FROM task_tier_floors WHERE task_type = ?",
                (task_type,),
            ).fetchone()
        finally:
            if self._conn is None:
                conn.close()

        if not row:
            return 1
        min_tier, updated_at = int(row[0]), float(row[1])
        if current_time - updated_at > 4.0 * self.half_life_seconds and min_tier > 1:
            return max(1, min_tier - 1)
        return max(1, min(min_tier, len(self.tiers)))

    def _record_evolution(
        self,
        mode: str,
        source: str,
        decision: str,
        evidence: str,
        timestamp: float,
    ) -> Dict[str, str]:
        rec = distill_evolution_record(
            mode=mode,
            source=source,
            decision=decision,
            evidence=evidence,
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO evolution_ledger (mode, source, decision, evidence, compact_entry, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["mode"],
                    rec["source"],
                    rec["decision"],
                    rec["evidence"],
                    rec["compact_entry"],
                    timestamp,
                ),
            )
            conn.commit()
        finally:
            if self._conn is None:
                conn.close()
        return rec

    def get_evolution_ledger(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT mode, source, decision, evidence, compact_entry, timestamp FROM evolution_ledger ORDER BY id ASC"
            ).fetchall()
        finally:
            if self._conn is None:
                conn.close()
        return [
            {
                "mode": r[0],
                "source": r[1],
                "decision": r[2],
                "evidence": r[3],
                "compact_entry": r[4],
                "timestamp": r[5],
            }
            for r in rows
        ]

    def _maybe_evolve_task_floor(
        self,
        task_type: str,
        winning_tier: int,
        now: float,
    ) -> None:
        current_floor = self.get_task_tier_floor(task_type, now=now)
        if winning_tier <= current_floor:
            return

        lower_tier_idx = winning_tier - 2
        lower_models = self.tiers[lower_tier_idx]
        tier_score = sum(
            self.get_model_score(m, now=now, task_type=task_type) for m in lower_models
        )
        if tier_score <= self.TIER_DEMOTION_THRESHOLD:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO task_tier_floors (task_type, min_tier, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(task_type) DO UPDATE SET
                        min_tier = excluded.min_tier,
                        updated_at = excluded.updated_at
                    """,
                    (task_type, winning_tier, now),
                )
                conn.commit()
            finally:
                if self._conn is None:
                    conn.close()

            self._record_evolution(
                mode="DERIVED",
                source=f"DynamicOracleRouter:{task_type}",
                decision=f"Promote starting tier floor for '{task_type}' from Tier {current_floor} to Tier {winning_tier}",
                evidence=f"Lower tier score={tier_score:.2f} <= {self.TIER_DEMOTION_THRESHOLD}",
                timestamp=now,
            )

    def select_best_in_tier(
        self,
        tier_models: List[str],
        now: Optional[float] = None,
        task_type: Optional[str] = None,
        needs_vision: bool = False,
    ) -> str:
        candidates = list(tier_models)
        if needs_vision:
            vision_only = [
                m
                for m in candidates
                if self.inventory.get(m) and self.inventory[m].supports_vision
            ]
            if vision_only:
                candidates = vision_only

        def combined_score(model_id: str) -> float:
            global_s = self.get_model_score(model_id, now=now)
            task_s = (
                self.get_model_score(model_id, now=now, task_type=task_type)
                if task_type
                else 0.0
            )
            prof = self.inventory.get(model_id)
            cost_bonus = (
                max(0.0, (20.0 - prof.input_cost_per_mtok)) * 0.001 if prof else 0.0
            )
            return global_s + task_s + cost_bonus

        return max(candidates, key=combined_score)

    def classify_chat_request(
        self,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Tuple[str, bool, int]:
        """OpenAI /v1/chat/completions isteğini analiz ederek (task_type, needs_vision, target_tier) belirler."""
        requested_model = str(payload.get("model", "oracle/auto"))
        messages = payload.get("messages", [])
        tools = payload.get("tools", [])
        has_vision = False
        combined_text_parts: List[str] = []

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in {"image_url", "input_image"}:
                            has_vision = True
                        elif part.get("type") == "text":
                            combined_text_parts.append(str(part.get("text", "")))
            elif isinstance(content, str):
                combined_text_parts.append(content)

        full_text = "\n".join(combined_text_parts).lower()
        if requested_model == "oracle/free":
            return ("free_fast", has_vision, 1)
        if requested_model == "oracle/eco":
            return ("eco_summary", has_vision, 1)

        if any(
            k in full_text
            for k in ("ghidra", "tersine mühendislik", "mimari", "decompile", "cloudflare", "exploit")
        ):
            task_type = "architecture_or_rea"
            base_tier = 3
        elif tools or any(k in full_text for k in ("python", "pytest", "class ", "def ", "json")):
            task_type = "agentic_coding"
            base_tier = 2
        else:
            task_type = "general_chat"
            base_tier = 1

        learned_floor = self.get_task_tier_floor(task_type)
        return (task_type, has_vision, max(base_tier, learned_floor))

    def route_and_execute(
        self,
        prompt: str,
        task_type: str,
        executor: Callable[[str, str], str],
        oracle_validator: Callable[[str], OracleSignal],
        needs_vision: bool = False,
    ) -> Dict[str, Any]:
        """Öğrenilmiş görev tabanından ve ince ayarlardan başlayarak Oracle doğrulaması geçene kadar kademeli yükseltir."""
        attempts: List[Dict[str, Any]] = []
        now = time.time()
        output = ""
        start_tier = self.get_task_tier_floor(task_type, now=now)
        last_tuning: Dict[str, Any] = {}

        for tier_index in range(start_tier, len(self.tiers) + 1):
            tier_models = self.tiers[tier_index - 1]
            candidate = self.select_best_in_tier(
                tier_models,
                now=now,
                task_type=task_type,
                needs_vision=needs_vision,
            )
            last_tuning = self.get_adaptive_tuning(
                candidate, task_type=task_type, now=now
            )
            output = executor(candidate, prompt)
            signal = oracle_validator(output)
            self.record_outcome(
                candidate,
                passed=signal.passed,
                channel=signal.channel,
                timestamp=now,
                task_type=task_type,
            )
            attempts.append(
                {
                    "tier": tier_index,
                    "model": candidate,
                    "passed": signal.passed,
                    "channel": signal.channel,
                    "tuning": last_tuning,
                }
            )
            if signal.passed:
                self._maybe_evolve_task_floor(
                    task_type=task_type, winning_tier=tier_index, now=now
                )
                return {
                    "final_model": candidate,
                    "tier_reached": tier_index,
                    "starting_tier": start_tier,
                    "selected_tuning": last_tuning,
                    "output": output,
                    "attempts": attempts,
                }

        return {
            "final_model": attempts[-1]["model"] if attempts else "",
            "tier_reached": len(self.tiers),
            "starting_tier": start_tier,
            "selected_tuning": last_tuning,
            "output": output,
            "attempts": attempts,
        }
