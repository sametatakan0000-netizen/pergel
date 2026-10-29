"""Tests for session record/replay and WebMCP modules."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.session_replay import SessionRecorder, SessionReplay
from src.api.webmcp import WebMCPHandler, TOOLS


class TestSessionRecorder(unittest.TestCase):
    def test_record_and_save(self):
        with tempfile.TemporaryDirectory() as td:
            r = SessionRecorder("test1", sessions_dir=td)
            r.record("GET", "https://example.com", status=200,
                    resp_body=b"<html>hello</html>")
            path = r.save()
            assert os.path.exists(path)
            data = json.loads(open(path).read())
            assert data["session_id"] == "test1"
            assert data["entry_count"] == 1
            assert data["entries"][0]["url"] == "https://example.com"

    def test_summary(self):
        with tempfile.TemporaryDirectory() as td:
            r = SessionRecorder("s2", sessions_dir=td)
            r.record("GET", "https://a.com", status=200)
            r.record("GET", "https://b.com", status=404)
            s = r.summary
            assert s["entries"] == 2
            assert s["unique_urls"] == 2
            assert s["errors"] == 1


class TestSessionReplay(unittest.TestCase):
    def test_record_then_replay(self):
        with tempfile.TemporaryDirectory() as td:
            r = SessionRecorder("replay_test", sessions_dir=td)
            r.record("GET", "https://example.com/page", status=200,
                    resp_body=b"content here")
            path = r.save()

            replay = SessionReplay.load(path)
            result = replay.fetch("https://example.com/page")
            assert result is not None
            assert result["status"] == 200
            assert result["body_b64"] is not None

    def test_replay_miss(self):
        with tempfile.TemporaryDirectory() as td:
            r = SessionRecorder("miss_test", sessions_dir=td)
            r.record("GET", "https://a.com", status=200)
            path = r.save()
            replay = SessionReplay.load(path)
            assert replay.fetch("https://not-recorded.com") is None

    def test_replay_urls(self):
        with tempfile.TemporaryDirectory() as td:
            r = SessionRecorder("urls_test", sessions_dir=td)
            r.record("GET", "https://x.com", status=200)
            r.record("GET", "https://y.com", status=200)
            path = r.save()
            replay = SessionReplay.load(path)
            assert len(replay.urls) == 2


class TestWebMCP(unittest.TestCase):
    def test_list_tools(self):
        h = WebMCPHandler()
        result = h.list_tools()
        assert "tools" in result
        assert len(result["tools"]) == 4
        names = [t["name"] for t in result["tools"]]
        assert "browse_url" in names
        assert "extract_data" in names
        assert "crawl_sitemap" in names
        assert "search_fanout" in names

    def test_capabilities(self):
        h = WebMCPHandler()
        caps = h.capabilities()
        assert caps["protocol"] == "webmcp"
        assert caps["features"]["ssrf_protection"] is True
        assert caps["features"]["telemetry"] is False

    def test_call_unknown_tool(self):
        h = WebMCPHandler()
        result = h.call_tool("nonexistent", {})
        assert "error" in result
        assert result["isError"] is True

    def test_call_tool_not_wired(self):
        h = WebMCPHandler()
        result = h.call_tool("browse_url", {"url": "https://example.com"})
        assert "error" in result
        assert result["error"]["code"] == "not_wired"

    def test_call_tool_with_handler(self):
        def fake_browse(url, mode):
            return {"url": url, "status": 200, "content": "test"}
        h = WebMCPHandler(browse_fn=fake_browse)
        result = h.call_tool("browse_url", {"url": "https://example.com"})
        assert result["isError"] is False
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert data["url"] == "https://example.com"

    def test_tool_schemas_valid(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"


if __name__ == "__main__":
    unittest.main()
