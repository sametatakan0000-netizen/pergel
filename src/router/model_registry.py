"""Verified model registry: Nous curated catalog IDs x models.dev (OpenRouter) metadata.

Membership comes from Hermes' official Nous catalog. Capabilities, context limits,
effort levels and list prices come from models.dev, which Hermes itself uses for
Nous metadata resolution. Nothing here is guessed: unknown fields stay None and
models without metadata are marked ``catalog_only`` and excluded from auto-routing.
"""
from dataclasses import asdict, dataclass, field
import json
import os
import tempfile
import urllib.request
from typing import Any, Dict, Optional, Tuple

CATALOG_URL = "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json"
MODELS_DEV_URL = "https://models.dev/api.json"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
METADATA_SOURCE = "models.dev:openrouter"
OPENROUTER_SOURCE = "openrouter:/api/v1/models"

# Canonical effort order used only to find the nearest level a model supports.
EFFORT_ORDER: Tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class VerifiedProfile:
    model_id: str
    status: str  # "verified_metadata" | "catalog_only"
    metadata_source: Optional[str] = None
    name: str = ""
    description: str = ""
    family: str = ""
    supports_tools: bool = False
    supports_vision: bool = False
    supports_reasoning: bool = False
    effort_levels: Tuple[str, ...] = ()
    input_modalities: Tuple[str, ...] = ()
    context_window: Optional[int] = None
    max_output: Optional[int] = None
    # List prices from models.dev (USD / 1M tokens). Portal promo prices may be lower.
    list_cost_in: Optional[float] = None
    list_cost_out: Optional[float] = None
    list_cost_cache_read: Optional[float] = None
    release_date: str = ""
    knowledge_cutoff: str = ""
    is_silent_default: bool = False
    default_effort: Optional[str] = None
    reasoning_mandatory: bool = False
    # Public third-party benchmark data (Artificial Analysis via OpenRouter). None = not published.
    intelligence_index: Optional[float] = None
    coding_index: Optional[float] = None
    agentic_index: Optional[float] = None
    fetched_at: str = field(default="", compare=False)

    @property
    def routable(self) -> bool:
        """Auto-routing requires verified metadata and native tool calling (Hermes is agentic)."""
        return self.status == "verified_metadata" and self.supports_tools


def _catalog_entries(catalog: Dict[str, Any]):
    if not isinstance(catalog, dict) or catalog.get("version") != 1:
        raise ValueError("Unsupported Hermes model catalog schema")
    models = catalog.get("providers", {}).get("nous", {}).get("models")
    if not isinstance(models, list) or any(
        not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m["id"].strip()
        for m in models
    ):
        raise ValueError("Nous catalog must be a list of {id: str} objects")
    return models


def _metadata_index(models_dev: Dict[str, Any]) -> Dict[str, Any]:
    block = models_dev.get("openrouter") if isinstance(models_dev, dict) else None
    models = block.get("models") if isinstance(block, dict) else None
    if not isinstance(models, dict):
        raise ValueError("models.dev payload lacks openrouter.models mapping")
    return models


def _effort_levels(meta: Dict[str, Any]) -> Tuple[str, ...]:
    for option in meta.get("reasoning_options") or []:
        if isinstance(option, dict) and option.get("type") == "effort":
            values = option.get("values") or []
            return tuple(v for v in values if isinstance(v, str))
    return ()


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _int(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def build_profiles(catalog: Dict[str, Any], models_dev: Dict[str, Any], fetched_at: str) -> Dict[str, VerifiedProfile]:
    entries = _catalog_entries(catalog)
    index = _metadata_index(models_dev)
    profiles: Dict[str, VerifiedProfile] = {}
    for entry in entries:
        mid = entry["id"].strip()
        silent_default = bool(entry.get("default"))
        meta = index.get(mid)
        if not isinstance(meta, dict):
            profiles[mid] = VerifiedProfile(
                model_id=mid, status="catalog_only",
                is_silent_default=silent_default, fetched_at=fetched_at,
            )
            continue
        modalities = meta.get("modalities") or {}
        inputs = tuple(m for m in modalities.get("input") or [] if isinstance(m, str))
        limit = meta.get("limit") or {}
        cost = meta.get("cost") or {}
        profiles[mid] = VerifiedProfile(
            model_id=mid,
            status="verified_metadata",
            metadata_source=METADATA_SOURCE,
            name=str(meta.get("name") or ""),
            description=str(meta.get("description") or ""),
            family=str(meta.get("family") or ""),
            supports_tools=meta.get("tool_call") is True,
            supports_vision="image" in inputs,
            supports_reasoning=meta.get("reasoning") is True,
            effort_levels=_effort_levels(meta),
            input_modalities=inputs,
            context_window=_int(limit.get("context")),
            max_output=_int(limit.get("output")),
            list_cost_in=_num(cost.get("input")),
            list_cost_out=_num(cost.get("output")),
            list_cost_cache_read=_num(cost.get("cache_read")),
            release_date=str(meta.get("release_date") or ""),
            knowledge_cutoff=str(meta.get("knowledge") or ""),
            is_silent_default=silent_default,
            fetched_at=fetched_at,
        )
    return profiles


def _per_million(value: Any) -> Optional[float]:
    """OpenRouter prices are USD-per-token strings; negative means variable (router models)."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return None if price < 0 else round(price * 1_000_000, 6)


def _canonical_efforts(values: Any) -> Tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    known = [lvl for lvl in EFFORT_ORDER if lvl in values]
    extras = [v for v in values if isinstance(v, str) and v not in EFFORT_ORDER]
    return tuple(known + extras)


def build_profiles_from_openrouter(catalog: Dict[str, Any], openrouter: Dict[str, Any], fetched_at: str) -> Dict[str, VerifiedProfile]:
    entries = _catalog_entries(catalog)
    data = openrouter.get("data") if isinstance(openrouter, dict) else None
    if not isinstance(data, list):
        raise ValueError("OpenRouter payload lacks data list")
    index = {m["id"]: m for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)}
    profiles: Dict[str, VerifiedProfile] = {}
    for entry in entries:
        mid = entry["id"].strip()
        silent_default = bool(entry.get("default"))
        meta = index.get(mid)
        if meta is None:
            profiles[mid] = VerifiedProfile(model_id=mid, status="catalog_only",
                                            is_silent_default=silent_default, fetched_at=fetched_at)
            continue
        arch = meta.get("architecture") or {}
        inputs = tuple(m for m in arch.get("input_modalities") or [] if isinstance(m, str))
        top = meta.get("top_provider") or {}
        contexts = [c for c in (_int(meta.get("context_length")), _int(top.get("context_length"))) if c]
        params = meta.get("supported_parameters") or []
        reasoning = meta.get("reasoning") if isinstance(meta.get("reasoning"), dict) else {}
        pricing = meta.get("pricing") or {}
        aa = (meta.get("benchmarks") or {}).get("artificial_analysis") or {}
        profiles[mid] = VerifiedProfile(
            model_id=mid,
            status="verified_metadata",
            metadata_source=OPENROUTER_SOURCE,
            name=str(meta.get("name") or ""),
            description=str(meta.get("description") or ""),
            family=str(meta.get("canonical_slug") or ""),
            supports_tools="tools" in params,
            supports_vision="image" in inputs,
            supports_reasoning=bool(reasoning) or "reasoning" in params,
            effort_levels=_canonical_efforts(reasoning.get("supported_efforts")),
            input_modalities=inputs,
            context_window=min(contexts) if contexts else None,
            max_output=_int(top.get("max_completion_tokens")),
            list_cost_in=_per_million(pricing.get("prompt")),
            list_cost_out=_per_million(pricing.get("completion")),
            list_cost_cache_read=_per_million(pricing.get("input_cache_read")),
            knowledge_cutoff=str(meta.get("knowledge_cutoff") or ""),
            is_silent_default=silent_default,
            default_effort=reasoning.get("default_effort") if isinstance(reasoning.get("default_effort"), str) else None,
            reasoning_mandatory=reasoning.get("mandatory") is True,
            intelligence_index=_num(aa.get("intelligence_index")),
            coding_index=_num(aa.get("coding_index")),
            agentic_index=_num(aa.get("agentic_index")),
            fetched_at=fetched_at,
        )
    return profiles


def clamp_effort(profile: VerifiedProfile, desired: Optional[str]) -> Optional[str]:
    """Map a requested effort onto a level the model accepts; None means omit the field."""
    levels = profile.effort_levels
    if not levels or not desired:
        return None
    wanted = "max" if desired == "ultra" else desired
    if wanted in levels:
        return wanted
    ranked = [lvl for lvl in EFFORT_ORDER if lvl in levels]
    if not ranked or wanted not in EFFORT_ORDER:
        return ranked[-1] if ranked else None
    position = EFFORT_ORDER.index(wanted)
    for lvl in ranked:
        if EFFORT_ORDER.index(lvl) >= position:
            return lvl
    return ranked[-1]


def save_snapshot(path: str, profiles: Dict[str, VerifiedProfile], fetched_at: str) -> None:
    payload = {
        "fetched_at": fetched_at,
        "sources": {"catalog": CATALOG_URL, "metadata": MODELS_DEV_URL},
        "profiles": {mid: asdict(p) for mid, p in sorted(profiles.items())},
    }
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)  # atomic: readers never see a half-written registry


def load_snapshot(path: str) -> Tuple[Dict[str, VerifiedProfile], str]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    profiles = {}
    for mid, data in payload["profiles"].items():
        for key in ("effort_levels", "input_modalities"):
            data[key] = tuple(data.get(key) or ())
        profiles[mid] = VerifiedProfile(**data)
    return profiles, payload["fetched_at"]


def _get_json(url: str, timeout: int) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-browser-farm-registry/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_profiles(fetched_at: str, catalog_url: str = CATALOG_URL,
                   openrouter_url: str = OPENROUTER_MODELS_URL,
                   models_dev_url: str = MODELS_DEV_URL) -> Dict[str, VerifiedProfile]:
    """Public, key-less sources only. No model inference is performed."""
    catalog = _get_json(catalog_url, 15)
    try:
        return build_profiles_from_openrouter(catalog, _get_json(openrouter_url, 30), fetched_at)
    except (OSError, ValueError):
        return build_profiles(catalog, _get_json(models_dev_url, 30), fetched_at)
