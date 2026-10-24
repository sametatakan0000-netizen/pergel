"""Slice 4: MCP tool surface over the loopback REST API (SOTA decision 2026-10-23:
MCP is the expected surface for agent tools; this wraps the job/search/router API).

Transport: stdio by default (`python -m src.mcp_server`). The REST base URL and the
`/v1/jobs` bearer key come from ORACLE_API_BASE / BROWSE_API_KEY; router paths need no key.
"""
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

try:
    from fastmcp import FastMCP
except ImportError:  # shortcut: optional dep like trafilatura/playwright
    FastMCP = None

DEFAULT_BASE = "http://127.0.0.1:8090"
_KEY_FILE = os.path.expanduser("~/.config/oracle-router/browse_api.env")


def _load_browse_key() -> str:
    """/v1/jobs bearer key: BROWSE_API_KEY env wins, else the 0600 deploy env file."""
    env = os.environ.get("BROWSE_API_KEY")
    if env:
        return env
    try:
        with open(_KEY_FILE, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("BROWSE_API_KEY="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return ""

HttpFn = Callable[[str, str, Optional[Dict[str, Any]]], Tuple[int, Dict[str, Any]]]


def _default_http(method: str, path: str, payload: Optional[Dict[str, Any]] = None,
                  base_url: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    base = (base_url or os.environ.get("ORACLE_API_BASE") or DEFAULT_BASE).rstrip("/")
    headers = {"Content-Type": "application/json"}
    key = _load_browse_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except ValueError:
            body = {"error": f"HTTP {exc.code}"}
        return exc.code, body


def build_mcp(http_fn: Optional[HttpFn] = None, base_url: Optional[str] = None) -> "FastMCP":
    if FastMCP is None:
        raise RuntimeError("fastmcp is not installed (.venv/bin/pip install fastmcp)")
    http = http_fn or (lambda method, path, payload=None: _default_http(method, path, payload, base_url))
    mcp = FastMCP(name="browser-farm")

    @mcp.tool
    def browse_url(url: str, goal: str = "", needs_vision: bool = False,
                   js_complexity: str = "low") -> Dict[str, Any]:
        """Fetch a URL through the cascading engine ladder (lightpanda -> chromium) and
        return clean markdown plus discovered HAR/XHR API endpoints. Honors robots.txt."""
        status, body = http("POST", "/v1/jobs/browse", {
            "url": url, "goal": goal, "needs_vision": needs_vision,
            "js_complexity": js_complexity,
        })
        if status != 200:
            raise RuntimeError(body.get("error", f"browse failed: HTTP {status}"))
        return {"job_id": body.get("job_id"), "final_engine": body.get("engine"),
                "markdown": body.get("extracted_markdown", ""),
                "discovered_apis": body.get("discovered_apis", []),
                "blocked": body.get("blocked", False)}

    @mcp.tool
    def search_fanout(query: str) -> Dict[str, Any]:
        """Fan a query out into subqueries, run live-index search and return deduped
        sources with inline [N] grounding."""
        status, body = http("POST", "/v1/search/fanout", {"query": query})
        if status != 200:
            raise RuntimeError(body.get("error", f"fanout failed: HTTP {status}"))
        return body

    @mcp.tool
    def list_models() -> Dict[str, Any]:
        """List models served by the oracle router."""
        status, body = http("GET", "/v1/models")
        if status != 200:
            raise RuntimeError(f"models failed: HTTP {status}")
        return body

    @mcp.tool
    def router_health() -> Dict[str, Any]:
        """Health report of the router: watchdog services and upstream readiness."""
        status, body = http("GET", "/v1/health")
        if status != 200:
            raise RuntimeError(f"health failed: HTTP {status}")
        return body

    return mcp


if __name__ == "__main__":
    build_mcp().run()  # stdio
