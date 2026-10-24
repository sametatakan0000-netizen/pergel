"""MCP tool surface (Slice 4): in-process FastMCP client against a stubbed HTTP layer."""
import unittest
from typing import Any, Dict, List, Tuple

from src.mcp_server import build_mcp

try:
    from fastmcp import Client
    from fastmcp.exceptions import ToolError
except ImportError:  # shortcut: fastmcp is optional; CI without it skips MCP tests
    Client = None
    ToolError = Exception


JOB_OK = {
    "job_id": "j-1", "status": "completed", "engine": "lightpanda",
    "extracted_markdown": "# Sayfa\n\nicerik", "oracle_passed": True,
    "discovered_apis": ["https://example.com/api/data.json"],
    "attempted_engines": ["lightpanda"], "blocked": False,
}
FANOUT_OK = {
    "original_query": "q", "subqueries": ["a", "b"],
    "sources": [{"title": "T", "url": "https://e.com", "snippet": "s"}],
    "grounded_context": "[1] T (https://e.com) — s",
}


class _StubHttp:
    def __init__(self, routes: Dict[Tuple[str, str], Tuple[int, Dict[str, Any]]]):
        self.routes = routes
        self.calls: List[Tuple[str, str, Any]] = []

    def __call__(self, method: str, path: str, payload: Any = None) -> Tuple[int, Dict[str, Any]]:
        self.calls.append((method, path, payload))
        return self.routes[(method, path)]


@unittest.skipUnless(Client is not None, "fastmcp not installed")
class McpToolSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_inventory(self):
        mcp = build_mcp(http_fn=_StubHttp({}))
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
        self.assertEqual(names, {"browse_url", "search_fanout", "list_models", "router_health"})

    async def test_browse_url_posts_job_and_returns_structured_result(self):
        stub = _StubHttp({("POST", "/v1/jobs/browse"): (200, JOB_OK)})
        mcp = build_mcp(http_fn=stub)
        async with Client(mcp) as client:
            res = await client.call_tool("browse_url", {"url": "https://example.com/"})
        self.assertEqual(res.data["job_id"], "j-1")
        self.assertIn("icerik", res.data["markdown"])
        self.assertEqual(stub.calls[0][0], "POST")
        self.assertEqual(stub.calls[0][2]["url"], "https://example.com/")

    async def test_browse_url_surfaces_api_error_as_tool_error(self):
        mcp = build_mcp(http_fn=_StubHttp({("POST", "/v1/jobs/browse"): (400, {"error": "bad url"})}))
        async with Client(mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("browse_url", {"url": "not-a-url"})

    async def test_search_fanout_returns_grounded_context(self):
        stub = _StubHttp({("POST", "/v1/search/fanout"): (200, FANOUT_OK)})
        mcp = build_mcp(http_fn=stub)
        async with Client(mcp) as client:
            res = await client.call_tool("search_fanout", {"query": "q"})
        self.assertEqual(res.data["sources"][0]["url"], "https://e.com")
        self.assertIn("[1]", res.data["grounded_context"])

    async def test_list_models_and_health_are_get_calls(self):
        stub = _StubHttp({("GET", "/v1/models"): (200, {"data": [{"id": "oracle/auto"}]}),
                          ("GET", "/v1/health"): (200, {"status": "ok"})})
        mcp = build_mcp(http_fn=stub)
        async with Client(mcp) as client:
            models = await client.call_tool("list_models", {})
            health = await client.call_tool("router_health", {})
        self.assertEqual(models.data["data"][0]["id"], "oracle/auto")
        self.assertEqual(health.data["status"], "ok")


if __name__ == "__main__":
    unittest.main()


class BrowseKeyLoadingTests(unittest.TestCase):
    def test_env_var_wins_over_key_file(self):
        import os
        import src.mcp_server as m
        os.environ["BROWSE_API_KEY"] = "from-env"
        try:
            self.assertEqual(m._load_browse_key(), "from-env")
        finally:
            del os.environ["BROWSE_API_KEY"]

    def test_falls_back_to_key_file(self):
        import os, tempfile
        import src.mcp_server as m
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
            fh.write("BROWSE_API_KEY=from-file\n")
            path = fh.name
        os.environ.pop("BROWSE_API_KEY", None)
        orig = m._KEY_FILE
        m._KEY_FILE = path
        try:
            self.assertEqual(m._load_browse_key(), "from-file")
        finally:
            m._KEY_FILE = orig
            os.unlink(path)

    def test_missing_everywhere_is_empty(self):
        import os
        import src.mcp_server as m
        os.environ.pop("BROWSE_API_KEY", None)
        orig = m._KEY_FILE
        m._KEY_FILE = "/nonexistent/.env"
        try:
            self.assertEqual(m._load_browse_key(), "")
        finally:
            m._KEY_FILE = orig
