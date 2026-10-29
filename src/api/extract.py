"""Structured extraction from page HTML (/v1/extract backing logic).

Pure functions over HTML — no network, no server. Given raw page HTML and a
field spec, returns extracted values. Strategies, in order per field:
  1. jsonld   — schema.org JSON-LD (<script type="application/ld+json">) by key
  2. css      — element text via a data-attribute/selector-ish match
  3. regex    — a user-supplied regex with one capture group

This is the deterministic extraction half of the product: a caller asks for
named fields and gets JSON back, no LLM guesswork in the hot path.
"""
import json
import re
from typing import Any, Dict, List, Optional


def _parse_jsonld(html: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # A block may be a single object, a list, or an @graph wrapper.
        if isinstance(data, list):
            blocks.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                blocks.extend(x for x in graph if isinstance(x, dict))
            else:
                blocks.append(data)
    return blocks


def _jsonld_lookup(blocks: List[Dict[str, Any]], key: str) -> Optional[Any]:
    key_l = key.lower()
    for block in blocks:
        for k, v in block.items():
            if k.lower() == key_l:
                return v
    return None


def _first_text(html: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return (m.group(1) if m.groups() else m.group(0)).strip()


def _css_text(html: str, selector: str) -> Optional[str]:
    """Minimal data-hook extraction: element text by hook/id/class.

    Not a real CSS engine — covers the deterministic hooks the product needs
    (``data-hook="price">49<``, ``data-price="49"``, ``<span id="price">49</span>``)
    without a browser. Patterns, in order:
      1. any ``data-*="<selector>"`` attribute -> that element's text
      2. ``data-<selector>="<value>"`` attribute -> the value itself
      3. ``id="<selector>"`` or ``class~=...<selector>...`` -> element text
    """
    # 1. data-hook="selector" (or any data-*="selector") -> element inner text
    m = re.search(
        r'data-[a-z-]+=["\']%s["\'][^>]*>(.*?)</' % re.escape(selector),
        html, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    # 2. data-<selector>="value" -> the attribute value
    m = re.search(r'data-%s=["\']([^"\']+)["\']' % re.escape(selector), html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 3. id="selector" ...>text</tag>
    m = re.search(
        r'id=["\']%s["\'][^>]*>(.*?)</' % re.escape(selector), html, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    # 4. class containing selector
    m = re.search(
        r'class=["\'][^"\']*%s[^"\']*["\'][^>]*>(.*?)</' % re.escape(selector),
        html, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return None


def extract_fields(html: str, fields: List[Dict[str, str]]) -> Dict[str, Any]:
    """Extract named fields from HTML.

    Each field spec: {"name": <output key>, "jsonld": <key>, "css": <selector>,
    "regex": <pattern with one capture group>} — at least one strategy. Strategies
    are tried per spec in the order jsonld -> css -> regex; first hit wins.
    """
    blocks = _parse_jsonld(html)
    out: Dict[str, Any] = {}
    for spec in fields or []:
        name = spec.get("name")
        if not name:
            continue
        value = None
        if spec.get("jsonld"):
            value = _jsonld_lookup(blocks, spec["jsonld"])
        if value is None and spec.get("css"):
            value = _css_text(html, spec["css"])
        if value is None and spec.get("regex"):
            value = _first_text(html, spec["regex"])
        out[name] = value
    return out
