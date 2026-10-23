"""Execution helpers for Amiral + subagent (MoA) turns.

Shape of one MoA turn:
  1. Subagents (members) run in parallel, non-streaming, with the same messages and tools.
  2. Their drafts are appended to the request as one system message.
  3. The Amiral (plan[0]) answers from that enriched request, streamed as usual.

Members never stream and never reach the client; a failed or unusable member is dropped
silently. If none survive, the caller falls back to the plain single-model path.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_DRAFT_CHARS = 4000  # per member; keeps the aggregator prompt bounded
DRAFT_HEADER = ("Independent drafts from subagent models for the same request. Use them as "
                "evidence, resolve disagreements yourself, and answer the user directly. "
                "Do not mention the drafts.")


def draft_text(body: Dict[str, Any]) -> Optional[str]:
    """Readable draft from a chat completion; tool calls become a one-line description."""
    choices = body.get("choices") if isinstance(body, dict) else None
    if not choices:
        return None
    message = choices[0].get("message") or {}
    parts: List[str] = []
    if isinstance(message.get("content"), str) and message["content"].strip():
        parts.append(message["content"].strip())
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        parts.append(f"[proposed tool call: {fn.get('name', '?')}({fn.get('arguments', '')})]")
    text = "\n".join(parts).strip()
    if not text:
        return None
    return text[:MAX_DRAFT_CHARS]


def run_members(call_fn: Callable[[str, Dict[str, Any]], Tuple[int, Dict[str, Any]]],
                members: List[str], payload: Dict[str, Any],
                max_workers: int = 3) -> List[Tuple[str, str]]:
    """Call every member in parallel. Returns ``[(model_id, draft)]`` in member order,
    keeping only members that answered 200 with usable content."""
    if not members:
        return []

    def one(model_id: str) -> Optional[str]:
        member_payload = dict(payload)
        member_payload["stream"] = False
        member_payload.pop("stream_options", None)
        try:
            status, body = call_fn(model_id, member_payload)
        except Exception:  # a failing subagent must never break the turn
            return None
        if status != 200:
            return None
        return draft_text(body)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(members))) as pool:
        results = list(pool.map(one, members))
    return [(m, d) for m, d in zip(members, results) if d]


def build_aggregator_payload(payload: Dict[str, Any],
                             drafts: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Copy of the request with the subagent drafts inserted as a system message just
    before the latest user turn. Tools and every other field are left untouched."""
    out = dict(payload)
    messages = list(payload.get("messages") or [])
    if not drafts:
        out["messages"] = messages
        return out
    blocks = [f"--- draft {i + 1} ({model}) ---\n{text}" for i, (model, text) in enumerate(drafts)]
    note = {"role": "system", "content": DRAFT_HEADER + "\n\n" + "\n\n".join(blocks)}
    insert_at = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            insert_at = index
            break
    out["messages"] = messages[:insert_at] + [note] + messages[insert_at:]
    return out


def member_usage_summary(drafts: List[Tuple[str, str]], attempted: List[str]) -> Dict[str, Any]:
    return {"attempted": attempted, "used": [m for m, _ in drafts],
            "dropped": [m for m in attempted if m not in {d[0] for d in drafts}]}


def json_size(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload))
