"""Canlı İndeks Sorgu Yayılımı (Query Fan-Out) ve Gerçek Zamanlı Tabanlama (Grounding) Motoru."""
import asyncio
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Awaitable, Callable, Dict, List, Optional


def decompose_query(query: str, max_subqueries: int = 4) -> List[str]:
    """Karmaşık bir istemi anlamsal alt sorgulara (Query Fan-Out) ayrıştırır.

    Yalnızca açık ayırıcılarda (bağlaç/noktalama) böler. Ayırıcı yoksa sorguyu olduğu
    gibi tek parça döndürür; kelime-ortası kesim anlamsız yarım sorgu üretiyordu.
    """
    cleaned = query.strip()
    if not cleaned:
        return []
    # shortcut: lexical conjunction split only; semantic decomposition needs an LLM call (cost policy: none)
    parts = re.split(
        r"\s+(?:ve|ile|ayrıca|veya|,|;)\s+|[,;]\s*",
        cleaned,
        flags=re.IGNORECASE,
    )
    subqueries: List[str] = []
    for part in parts:
        p = re.sub(r"\s+(?:nelerdir|nedir)\??$", "", part.strip(" ?.,;:"), flags=re.IGNORECASE).strip()
        if len(p) >= 4 and p not in subqueries:
            subqueries.append(p)
    if not subqueries:
        return [cleaned]
    return subqueries[:max_subqueries]



_LLM_MIN_QUERY_WORDS = 6  # shorter queries are fine as one search: no model call (cost policy)
_LLM_PROMPT = ("Split the following search request into 2-4 short, self-contained web-search "
               "subqueries in the same language as the request. Answer with ONLY a JSON array "
               "of strings, no prose.\nRequest: {query}")


def llm_decompose_prompt(query: str) -> str:
    """Bounded (~120 token) decomposition prompt; shared by the fan-out and the server wrapper."""
    return _LLM_PROMPT.format(query=query[:500])


def decompose_query_llm(query: str, call_fn: Callable[[str], str],
                        max_subqueries: int = 4) -> Optional[List[str]]:
    """LLM tabanlı ayrıştırma. ``call_fn(prompt)`` ham metin döner; her türlü hata/çöp
    cevap ``None`` döndürür -> çağıran lexical yoluna düşer (asla uydurma yok)."""
    try:
        raw = call_fn(llm_decompose_prompt(query))
        if not isinstance(raw, str):
            return None
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(raw[start:end + 1])
        if not isinstance(parsed, list):
            return None
        subs: List[str] = []
        for item in parsed:
            if not isinstance(item, str):
                return None
            p = item.strip(" ?.,;:")
            if len(p) >= 4 and p not in subs:
                subs.append(p)
        if len(subs) < 2:
            return None
        return subs[:max_subqueries]
    except Exception:  # timeout/JSON/network -> caller falls back to lexical
        return None


async def default_searxng_search(
    subquery: str, searxng_url: Optional[str] = None
) -> List[Dict[str, str]]:
    """Yerel SearXNG JSON API üzerinden arama yürütür (ORACLE_SEARXNG_URL, varsayılan localhost:8888)."""
    searxng_url = searxng_url or os.environ.get("ORACLE_SEARXNG_URL", "http://localhost:8888")
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
    decompose_fn: Optional[Callable[[str], Optional[List[str]]]] = None,
) -> Dict[str, Any]:
    """Alt sorguları paralel yürütür, kaynakları tekilleştirir ve satır içi [N] tabanlama üretir.

    ``decompose_fn`` verilirse yalnızca lexical yol tek parça ürettiğinde VE sorgu yeterince
    uzunken çağrılır (gizli model çağrısı yok; maliyet politikası). Hata/çöp cevapta
    lexical yola düşülür. ``decomposition`` alanı hangi yolun kullanıldığını bildirir.
    """
    active_search = search_fn or default_searxng_search
    subqueries = decompose_query(query, max_subqueries=max_subqueries)
    method = "lexical"
    if (decompose_fn is not None and len(subqueries) == 1
            and len(query.split()) >= _LLM_MIN_QUERY_WORDS):
        llm_subs = await asyncio.to_thread(decompose_fn, query)
        if llm_subs:
            subqueries = llm_subs
            method = "llm"
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
        "decomposition": method,
        "sources": deduped_sources,
        "grounded_context": "\n".join(lines),
    }
