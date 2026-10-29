"""Session record/replay for Pergel browser sessions.

Records every HTTP request/response during a browse session to a JSON log,
then replays them deterministically (no network, no side effects).

Usage:
    recorder = SessionRecorder("my-session")
    recorder.record_request("GET", "https://example.com", headers={...}, body=None)
    recorder.record_response(200, headers={...}, body=b"...", url="https://example.com")
    recorder.save()  # -> sessions/my-session.json

    replay = SessionReplay.load("sessions/my-session.json")
    response = replay.fetch("https://example.com")  # returns recorded response
"""

import hashlib
import json

import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionRecorder:
    """Records HTTP traffic during a session."""

    def __init__(self, session_id: str, sessions_dir: str = "sessions"):
        self.session_id = session_id
        self.sessions_dir = Path(sessions_dir)
        self.entries: List[Dict[str, Any]] = []
        self.started_at = time.time()

    def _key(self, method: str, url: str, body: Optional[bytes] = None) -> str:
        b = body or b""
        raw = f"{method}:{url}:{b}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def record(self, method: str, url: str,
               req_headers: Optional[Dict[str, str]] = None,
               req_body: Optional[bytes] = None,
               status: int = 200,
               resp_headers: Optional[Dict[str, str]] = None,
               resp_body: Optional[bytes] = None,
               duration_ms: float = 0.0) -> None:
        """Record a single request/response pair."""
        entry = {
            "key": self._key(method, url, req_body),
            "method": method,
            "url": url,
            "timestamp": time.time(),
            "duration_ms": duration_ms,
            "request": {
                "headers": req_headers or {},
                "body_size": len(req_body) if req_body else 0,
                "body_sha256": hashlib.sha256(req_body).hexdigest() if req_body else None,
            },
            "response": {
                "status": status,
                "headers": resp_headers or {},
                "body_size": len(resp_body) if resp_body else 0,
                "body_sha256": hashlib.sha256(resp_body).hexdigest() if resp_body else None,
            },
        }
        # Store body inline if small, else as blob reference
        if resp_body and len(resp_body) < 100_000:
            entry["response"]["body_b64"] = __import__("base64").b64encode(resp_body).decode("ascii")
        self.entries.append(entry)

    def save(self) -> str:
        """Save session to JSON file. Returns file path."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self.sessions_dir / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": time.time(),
            "entry_count": len(self.entries),
            "entries": self.entries,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return str(path)

    @property
    def summary(self) -> Dict[str, Any]:
        """Session summary statistics."""
        if not self.entries:
            return {"entries": 0}
        urls = set(e["url"] for e in self.entries)
        errors = [e for e in self.entries if e["response"]["status"] >= 400]
        return {
            "session_id": self.session_id,
            "entries": len(self.entries),
            "unique_urls": len(urls),
            "errors": len(errors),
            "duration_s": round(time.time() - self.started_at, 2),
        }


class SessionReplay:
    """Replays a recorded session without network access."""

    def __init__(self, data: Dict[str, Any]):
        self.session_id = data.get("session_id", "unknown")
        self.entries = data.get("entries", [])
        self._index: Dict[str, Dict[str, Any]] = {}
        for e in self.entries:
            key = e.get("key") or hashlib.sha256(
                f"{e['method']}:{e['url']}".encode()
            ).hexdigest()[:16]
            self._index[key] = e
            # Also index by URL alone (most common lookup)
            self._index[e["url"]] = e

    @classmethod
    def load(cls, path: str) -> "SessionReplay":
        with open(path) as f:
            return cls(json.load(f))

    def fetch(self, url: str, method: str = "GET",
              body: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
        """Return the recorded response for a URL. None if not in recording."""
        key = SessionRecorder("x")._key(method, url, body)
        entry = self._index.get(key) or self._index.get(url)
        if entry is None:
            return None
        resp = entry["response"]
        return {
            "status": resp["status"],
            "headers": resp.get("headers", {}),
            "body_size": resp.get("body_size", 0),
            "body_sha256": resp.get("body_sha256"),
            "body_b64": resp.get("body_b64"),
            "url": entry["url"],
            "recorded_at": entry.get("timestamp"),
        }

    @property
    def urls(self) -> List[str]:
        return list(set(e["url"] for e in self.entries))

    @property
    def summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "entries": len(self.entries),
            "urls": self.urls,
        }
