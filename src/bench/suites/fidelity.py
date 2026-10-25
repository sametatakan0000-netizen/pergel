"""No-LLM task-fidelity micro-suite (Task 3.4): scripted tasks on the deterministic
fixtures with exact expected outputs. Pure pass/fail, zero model calls, zero network
beyond localhost — safe for CI-style unit runs.

Cases (each returns None on pass, a short reason string on fail):
1. api_discovery_recall: /spa page source must yield /api/product and /api/reviews (2/2).
2. boilerplate_removal: /static extraction keeps the article marker, drops nav `menu` and footer.
3. robots_block_never_escalates: robots.txt Disallow makes the worker report blocked=True
   on the FIRST engine — the ladder must never escalate past a policy block.
4. body_cap_2mb: a >2MB page fetch returns exactly MAX_BODY_BYTES bytes (HTTP-driver cap).
"""
import http.server
import threading
import urllib.request
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from src.browser_engine.worker import (
    MAX_BODY_BYTES,
    BrowserWorker,
    _default_url_driver,
)
from src.bench.fixture_server import MARKERS


def _fetch_html(base: str, path: str) -> str:
    with urllib.request.urlopen(base + path, timeout=15) as resp:
        return resp.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")


def api_discovery_recall(base: str) -> Optional[str]:
    result = BrowserWorker().execute_task("fidelity-spa", base + "/spa")
    found = {urlsplit(u).path for u in result["discovered_apis"]}
    expected = {"/api/product", "/api/reviews"}
    missing = expected - found
    return None if not missing else f"recall {len(expected - missing)}/2, missing {sorted(missing)}"


def boilerplate_removal(base: str) -> Optional[str]:
    result = BrowserWorker().execute_task("fidelity-static", base + "/static")
    md = result["markdown"]
    problems = []
    if MARKERS["static"] not in md:
        problems.append("article marker missing")
    if "menu" in md.lower():
        problems.append("nav 'menu' kept")
    if any(line.strip() == "f" for line in md.splitlines()):
        problems.append("footer text kept")
    return "; ".join(problems) or None


class _DisallowedHandler(http.server.BaseHTTPRequestHandler):
    """Fixture origin whose robots.txt forbids everything."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = (b"User-agent: *\nDisallow: /\n" if self.path == "/robots.txt"
                else b"<html><body><p>must never be fetched</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain" if self.path == "/robots.txt" else "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def robots_block_never_escalates(base: str) -> Optional[str]:
    del base  # self-contained disallowing origin; the standard fixtures allow robots
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _DisallowedHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/page"
        result = BrowserWorker().execute_task("fidelity-robots", url)
    finally:
        srv.shutdown()
        srv.server_close()
    if not result.get("blocked"):
        return f"expected blocked=True, got oracle_passed={result.get('oracle_passed')}"
    if result["attempted_engines"] != ["lightpanda"]:
        return f"policy block escalated: attempted {result['attempted_engines']}"
    return None


def body_cap_2mb(base: str) -> Optional[str]:
    raw = _default_url_driver("chromium-browser-use", base + "/heavy?n=50000", "fidelity")
    size = len(raw.encode("utf-8"))
    if size == MAX_BODY_BYTES:
        return None
    return f"expected exactly {MAX_BODY_BYTES} bytes (cap hit), got {size}"


CASES: List[Callable[[str], Optional[str]]] = [
    api_discovery_recall,
    boilerplate_removal,
    robots_block_never_escalates,
    body_cap_2mb,
]


def run_fidelity(base_url: str) -> Dict[str, Any]:
    """Run every case against a fixture-server base URL; never raises."""
    passed: List[str] = []
    failed: Dict[str, str] = {}
    for case in CASES:
        try:
            reason = case(base_url)
        except Exception as exc:  # a crash is a failed case, not a harness error
            reason = f"{type(exc).__name__}: {exc}"
        if reason is None:
            passed.append(case.__name__)
        else:
            failed[case.__name__] = reason
    return {"passed": passed, "failed": failed}
