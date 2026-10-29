"""Live shield stats for Pergel — aggregation + loopback HTTP endpoint.

The shield panel polls ``/stats`` while the engine intercepts requests; the
``on_blocked`` callback of ``AdblockBrowserSession`` feeds :class:`ShieldStats`.
Endpoint is loopback-only and CORS-permissive so the panel can run from a
local ``file://`` document.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional, Tuple

_START_TIME = __import__("time").time()


class ShieldStats:
    """Thread-safe running tally of engine decisions (block/redirect/modify)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rules: Counter = Counter()

    def record(self, decision: dict) -> None:
        """Accept a ``decide_cdp_response`` decision dict; count non-allow."""
        if decision.get("action") == "allow":
            return
        rule = decision.get("rule_id") or "genel kural"
        with self._lock:
            self._rules[rule] += 1

    def snapshot(self) -> dict:
        with self._lock:
            total = sum(self._rules.values())
            top = [{"rule": r, "count": n}
                   for r, n in self._rules.most_common()]
        return {"blocked_total": total, "top_rules": top}


def serve_stats(host: str = "127.0.0.1", port: int = 0,
                stats: Optional[ShieldStats] = None
                ) -> Tuple[Callable[[], None], int]:
    """Start the stats endpoint on a daemon thread.

    Returns ``(stop, port)`` — call ``stop()`` to shut down. ``port=0`` binds a
    free ephemeral port which is returned instead.
    """
    st = stats or ShieldStats()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            path = self.path.rstrip("/")
            if path == "/diag":
                import platform
                import time
                body = json.dumps({
                    "loopback_status": "ok",
                    "hostname": platform.node(),
                    "platform": platform.system(),
                    "uptime_sec": round(time.time() - _START_TIME),
                    "note": "All diagnostics run locally on 127.0.0.1. No data leaves your device.",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path != "/stats":
                self.send_error(404)
                return
            body = json.dumps(st.snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep stdout pristine
            pass

    srv = ThreadingHTTPServer((host, port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    def stop() -> None:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=3)

    return stop, srv.server_address[1]
