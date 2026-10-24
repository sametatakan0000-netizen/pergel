"""Per-turn USD cost. Cache-read tokens bill at the cache-read price when published; with no
cache information the full input price is used, so spend stays an UPPER bound (never an
invented discount)."""
from typing import Any, Dict, Optional


def cached_tokens_from(usage: Optional[Dict[str, Any]]) -> Optional[int]:
    details = (usage or {}).get("prompt_tokens_details")
    value = details.get("cached_tokens") if isinstance(details, dict) else None
    return value if isinstance(value, int) else None


def turn_cost_usd(profile, prompt: int, completion: int, cached: int = 0) -> float:
    pin = profile.billed_cost_in or 0.0
    pout = profile.billed_cost_out or 0.0
    cache_price = profile.list_cost_cache_read if profile.list_cost_cache_read is not None else pin
    cached = max(0, min(cached or 0, prompt or 0))
    return (((prompt or 0) - cached) * pin + cached * cache_price + (completion or 0) * pout) / 1e6
