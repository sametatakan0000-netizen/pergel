"""Cheap, deterministic features of an OpenAI chat request (no model calls)."""
import json
from typing import Any, Dict, List

IMAGE_TOKEN_ESTIMATE = 1500   # per image part; base64 bytes are not text tokens
OUTPUT_RESERVE_TOKENS = 4096  # when the caller does not set max_tokens

TIER3_KEYWORDS = ("mimari", "architecture", "tasarım", "design", "refactor", "analiz", "analysis",
                  "güvenlik", "security", "planla", "migration", "optimiz")
TIER2_KEYWORDS = ("kod", "code", "python", "test", "hata", "bug", "fix", "script", "fonksiyon",
                  "function", "deploy", "docker", "sql", "regex", "api")


def message_text(message: Dict[str, Any]) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text") or "" for p in content if isinstance(p, dict))
    return ""


def has_image(messages: List[Dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(p, dict) and p.get("type") in ("image_url", "input_image") for p in content
        ):
            return True
    return False


def last_user_message(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    return next((m for m in reversed(messages) if m.get("role") == "user"), {})


def keyword_tier(messages: List[Dict[str, Any]]) -> int:
    """Crude starting guess from the latest user message; OutcomeLearner corrects it over time."""
    text = message_text(last_user_message(messages)).lower()
    if any(k in text for k in TIER3_KEYWORDS):
        return 3
    if any(k in text for k in TIER2_KEYWORDS):
        return 2
    return 1


def estimate_prompt_tokens(payload: Dict[str, Any]) -> int:
    """Conservative (over-)estimate of INPUT tokens only (no output reserve). ~3 chars/token."""
    chars, images = 0, 0
    for message in payload.get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in ("image_url", "input_image"):
                    images += 1
                else:
                    chars += len(part.get("text") or "")
        for call in message.get("tool_calls") or []:
            chars += len(json.dumps(call, ensure_ascii=False))
    if payload.get("tools"):
        chars += len(json.dumps(payload["tools"], ensure_ascii=False))
    return chars // 3 + images * IMAGE_TOKEN_ESTIMATE


def output_reserve(payload: Dict[str, Any]) -> int:
    return int(payload.get("max_tokens") or payload.get("max_completion_tokens") or OUTPUT_RESERVE_TOKENS)


def estimate_tokens(payload: Dict[str, Any]) -> int:
    """Conservative (over-)estimate of prompt + reserved output tokens."""
    return estimate_prompt_tokens(payload) + output_reserve(payload)
