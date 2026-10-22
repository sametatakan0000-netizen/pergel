"""Canlı İndeks Sorgu Yayılımı (Query Fan-Out) ve Gerçek Zamanlı Tabanlama (Grounding) Motoru."""
import asyncio
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Awaitable, Callable, Dict, List, Optional


def decompose_query(query: str, max_subqueries: int = 4) -> List[str]:
    """Karmaşık bir istemi anlamsal alt sorgulara (Query Fan-Out) ayrıştırır."""
    cleaned = query.strip()
    if not cleaned:
        return []
    parts = re.split(
        r"\s+(?:ve|ile|ayrıca|veya|karşılaştırması|nelerdir\??|nedir\??|,|;)\s+",
        cleaned,
        flags=re.IGNORECASE,
    )
    subqueries: List[str] = []
    for part in parts:
        p = part.strip(" ?.,;:")
        if len(p) >= 4 and p not in subqueries:
            subqueries.append(p)
    if len(subqueries) < 2 and len(cleaned.split()) >= 4:
        words = cleaned.strip(" ?.").split()
        mid = len(words) // 2
        subqueries = [" ".join(words[:mid]), " ".join(words[mid:])]
    return subqueries[:max_subqueries]


async def default_searxng_search(
    subquery: str, searxng_url: str = "http://localhost:8888"
) -> List[Dict[str, str]]:
    """Yerel SearXNG JSON API üzerinden arama yürütür."""
    encoded = urllib.parse.urlencode({"q": subquery, "format": "json"})
    url = f"{searxng_url.rstrip('/')}/search?{encoded}"

    def _fetch() -> List[Dict[str, str]]:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        results = []
        for item in payload.get("results", [])[:5]:
            results.append(
                {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("content", ""),
                }
            )
        return results

    return await asyncio.to_thread(_fetch)


async def execute_fanout_and_ground(
    query: str,
    search_fn: Optional[Callable[[str], Awaitable[List[Dict[str, str]]]]] = None,
    max_subqueries: int = 4,
) -> Dict[str, Any]:
    """Alt sorguları paralel yürütür, kaynakları tekilleştirir ve satır içi [N] tabanlama üretir."""
    active_search = search_fn or default_searxng_search
    subqueries = decompose_query(query, max_subqueries=max_subqueries)
    raw_batches = await asyncio.gather(*(active_search(sq) for sq in subqueries))

    deduped_sources: List[Dict[str, str]] = []
    seen_urls = set()
    lines: List[str] = []

    for sq, batch in zip(subqueries, raw_batches):
        for item in batch:
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            deduped_sources.append(item)
            idx = len(deduped_sources)
            title = item.get("title", "Kaynak")
            snippet = item.get("snippet", "")
            lines.append(f"[{idx}] {title} ({url}) — {snippet} (Alt Sorgu: '{sq}')")

    return {
        "original_query": query,
        "subqueries": subqueries,
        "sources": deduped_sources,
        "grounded_context": "\n".join(lines),
    }
