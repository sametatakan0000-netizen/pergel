import json
import os
import tempfile
import unittest
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest import mock

from src.api import server as server_mod
from src.api.server import BrowserFarmSaaSServer
from src.router.model_registry import build_profiles_from_openrouter

CATALOG = {"version": 1, "providers": {"nous": {"models": [
    {"id": "amiral/top"}, {"id": "sub/a"}, {"id": "sub/b"}]}}}


def _or(mid, price, aa, ctx=200000):
    return {"id": mid, "pricing": {"prompt": str(price / 1_000_000), "completion": str(price * 5 / 1_000_000)},
            "context_length": ctx, "architecture": {"input_modalities": ["text"]},
            "supported_parameters": ["tools"], "name": mid,
            "benchmarks": {"artificial_analysis": {"intelligence_index": aa}}}


OPENROUTER = {"data": [_or("amiral/top", 2.0, 57.0), _or("sub/a", 0.10, 54.0),
                       _or("sub/b", 0.08, 53.0)]}


class TestMoaEndToEnd(unittest.TestCase):
    def test_hard_turn_fans_out_to_members_then_amiral_gets_drafts(self):
        received = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(body)
                answer = f"answer-from-{body['model']}"
                response = json.dumps({"id": "x", "object": "chat.completion", "model": body["model"],
                                       "choices": [{"index": 0, "finish_reason": "stop",
                                                    "message": {"role": "assistant", "content": answer}}],
                                       "usage": {"prompt_tokens": 1000, "completion_tokens": 10}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        Thread(target=upstream.serve_forever, daemon=True).start()
        profiles = build_profiles_from_openrouter(CATALOG, OPENROUTER, fetched_at="t")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server_mod, "MOA_ENABLED", True):
            srv = BrowserFarmSaaSServer(port=0, db_dir=tmp, profiles=profiles,
                                        nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1")
            srv.moa_policy.choose = lambda bucket: "moa"  # pin the arm: this test is about the fan-out
            srv.start_background()
            try:
                # Make the hard turn force a band with subagents (tier 3 Amiral).
                big = "mimari refactor planı " + "detay " * 20000
                data = json.dumps({"model": "oracle/auto", "stream": True,
                                   "messages": [{"role": "user", "content": big}],
                                   "tools": [{"type": "function", "function": {"name": "terminal", "parameters": {"type": "object", "properties": {}}}}]}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/v1/chat/completions", data=data,
                                             method="POST", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    r.read()
                    selected = r.headers.get("X-Oracle-Selected-Model")
            finally:
                srv.shutdown()
                upstream.shutdown()
        members = [b for b in received if b.get("stream") is False]
        amiral_calls = [b for b in received if b.get("stream") is True]
        self.assertGreaterEqual(len(members), 1)            # subagents ran, non-streaming
        self.assertEqual(len(amiral_calls), 1)              # exactly one streamed Amiral answer
        drafts = [m for m in amiral_calls[0]["messages"] if m["role"] == "system"
                  and "draft" in m["content"]]
        self.assertEqual(len(drafts), 1)
        self.assertIn(members[0]["model"], drafts[0]["content"].replace("(", " ").replace(")", " ")
                      or drafts[0]["content"])
        self.assertEqual(selected, amiral_calls[0]["model"])
        self.assertEqual(amiral_calls[0]["tools"][0]["function"]["name"], "terminal")


class TestMoaArmSelection(unittest.TestCase):
    def test_single_arm_sends_only_amiral_and_records_nothing_for_members(self):
        received = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(body)
                response = json.dumps({"id": "x", "object": "chat.completion", "model": body["model"],
                                       "choices": [{"index": 0, "finish_reason": "stop",
                                                    "message": {"role": "assistant", "content": "ok"}}],
                                       "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        Thread(target=upstream.serve_forever, daemon=True).start()
        profiles = build_profiles_from_openrouter(CATALOG, OPENROUTER, fetched_at="t")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server_mod, "MOA_ENABLED", True):
            srv = BrowserFarmSaaSServer(port=0, db_dir=tmp, profiles=profiles,
                                        nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1")
            srv.moa_policy.choose = lambda bucket: "single"
            srv.start_background()
            try:
                big = "mimari refactor planı " + "detay " * 20000
                data = json.dumps({"model": "oracle/auto", "stream": True,
                                   "messages": [{"role": "user", "content": big}]}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/v1/chat/completions", data=data,
                                             method="POST", headers={"Content-Type": "application/json",
                                                                     "x-hermes-session-id": "arm-s"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    r.read()
            finally:
                srv.shutdown()
                upstream.shutdown()
        self.assertEqual(len(received), 1)                  # only the Amiral was called
        self.assertNotIn("draft", json.dumps(received[0]["messages"]))
