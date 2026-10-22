"""HMAC-SHA256 İmzalı ve Otomatik Yeniden Denemeli Webhook Dağıtıcısı."""
import hashlib
import hmac
import json
import urllib.request
from typing import Any, Callable, Dict, Optional


def compute_hmac_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _default_http_sender(url: str, body: bytes, headers: Dict[str, str]) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return int(resp.status)


class WebhookDispatcher:
    """Görev tamamlandığında müşteri URL'sine HMAC-SHA256 imzalı HTTP POST gönderir."""

    def __init__(
        self,
        secret: str = "hermes-browser-farm-secret",
        sender_fn: Optional[Callable[[str, bytes, Dict[str, str]], int]] = None,
        max_retries: int = 3,
    ) -> None:
        self.secret = secret
        self.sender_fn = sender_fn or _default_http_sender
        self.max_retries = max(1, max_retries)

    def dispatch(self, webhook_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        sig = compute_hmac_signature(self.secret, body)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-BrowserFarm-Signature": f"sha256={sig}",
        }

        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                status_code = self.sender_fn(webhook_url, body, headers)
                if 200 <= status_code < 300:
                    return {
                        "delivered": True,
                        "status_code": status_code,
                        "attempts": attempt,
                        "signature": f"sha256={sig}",
                    }
                last_error = f"HTTP {status_code}"
            except Exception as exc:
                last_error = str(exc)

        return {
            "delivered": False,
            "status_code": 0,
            "attempts": self.max_retries,
            "error": last_error,
        }
