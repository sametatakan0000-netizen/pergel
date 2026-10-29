"""WebMCP (Web Model Context Protocol) adapter for Pergel.

Exposes Pergel's browse/extract/crawl capabilities as MCP tools over HTTP,
compatible with the emerging WebMCP spec (Chromium 146+).

This module provides the SERVER-SIDE protocol handler. The actual tool calls
go through Pergel's existing SSRF-guarded API, so security guarantees are preserved.

Tools exposed:
  - browse_url     — fetch a URL with SSRF protection
  - extract_data   — schema-based extraction (JSON-LD, CSS, regex)
  - crawl_sitemap  — discover URLs from sitemap
  - search_fanout  — multi-engine search with dedupe

Endpoints (under /v1/mcp/):
  GET  /v1/mcp/tools          — list available tools (JSON schema)
  POST /v1/mcp/call           — invoke a tool
  GET  /v1/mcp/capabilities   — server capabilities
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional

MCP_VERSION = "0.1.0"

# Tool definitions (JSON Schema per MCP spec)
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "browse_url",
        "description": "Fetch a URL with SSRF protection. Returns HTML/text content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "mode": {"type": "string", "enum": ["fetch", "engine"], "description": "fetch=HTTP, engine=headless browser"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "extract_data",
        "description": "Extract structured data from a URL using CSS selectors, JSON-LD, or regex.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to extract from"},
                "schema": {"type": "object", "description": "Extraction schema: {field: selector} or {field: {selector, attr}}"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "crawl_sitemap",
        "description": "Discover URLs from a site's sitemap.xml.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Base URL to discover sitemap"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "search_fanout",
        "description": "Search multiple engines with query fan-out and dedupe results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "engines": {"type": "array", "items": {"type": "string"}, "description": "Engines to search (default: all)"},
            },
            "required": ["query"],
        },
    },
]


class WebMCPHandler:
    """Handles WebMCP protocol requests."""

    def __init__(self, browse_fn=None, extract_fn=None, crawl_fn=None, search_fn=None):
        self._browse = browse_fn
        self._extract = extract_fn
        self._crawl = crawl_fn
        self._search = search_fn

    def list_tools(self) -> Dict[str, Any]:
        """Return available tools in MCP format."""
        return {"tools": TOOLS}

    def capabilities(self) -> Dict[str, Any]:
        """Return server capabilities."""
        return {
            "protocol": "webmcp",
            "version": MCP_VERSION,
            "tools": [t["name"] for t in TOOLS],
            "features": {
                "ssrf_protection": True,
                "egress_control": True,
                "rate_limiting": True,
                "telemetry": False,
            },
        }

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a tool and return MCP-format result."""
        start = time.time()
        tool_names = [t["name"] for t in TOOLS]
        if name not in tool_names:
            return {"error": {"code": "unknown_tool", "message": f"Unknown tool: {name}. Available: {tool_names}"}, "isError": True}

        try:
            if name == "browse_url" and self._browse:
                result = self._browse(arguments["url"], arguments.get("mode", "fetch"))
            elif name == "extract_data" and self._extract:
                result = self._extract(arguments["url"], arguments.get("schema", {}))
            elif name == "crawl_sitemap" and self._crawl:
                result = self._crawl(arguments["url"])
            elif name == "search_fanout" and self._search:
                result = self._search(arguments["query"], arguments.get("engines"))
            else:
                return {"error": {"code": "not_wired", "message": f"Tool {name} has no handler wired"}}

            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "isError": False,
                "duration_ms": round((time.time() - start) * 1000, 1),
            }
        except Exception as e:
            return {
                "error": {"code": "tool_error", "message": str(e)},
                "isError": True,
                "duration_ms": round((time.time() - start) * 1000, 1),
            }
