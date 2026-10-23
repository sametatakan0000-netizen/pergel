import json
import os
import tempfile
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from src.api.server import BrowserFarmSaaSServer
from src.router.model_registry import build_profiles_from_openrouter


def _or_model(mid, cost_in, vision=False, efforts=("low", "medium", "high"), ctx=200000, aa=None):
    return {
        "id": mid, "name": mid, "context_length": ctx,
        "architecture": {"input_modalities": ["text", "image"] if vision else ["text"]},
        "supported_parameters": ["tools", "tool_choice", "reasoning_effort"],
        "reasoning": {"supported_efforts": list(efforts)} if efforts else None,
        "pricing": {"prompt": str(cost_in / 1e6), "completion": str(cost_in * 4 / 1e6)},
        "benchmarks": {"artificial_analysis": {"intelligence_index": aa}},
    }


def fixture_profiles():
    """Small, deterministic registry built through the real OpenRouter-format parser."""
    catalog = {"version": 1, "providers": {"nous": {"models": [
        {"id": "test/cheap"}, {"id": "test/mid"}, {"id": "google/gemini-4-argon"}, {"id": "test/catalog-only"},
    ]}}}
    openrouter = {"data": [
        _or_model("test/cheap", 0.05, efforts=("none", "high"), ctx=131072, aa=30.0),
        _or_model("test/mid", 0.8, ctx=262144, aa=40.0),
        _or_model("google/gemini-4-argon", 2.0, vision=True, ctx=1048576, aa=52.6),
    ]}
    return build_profiles_from_openrouter(catalog, openrouter, fetched_at="fixture")



class TestE2ESaaSProduct(unittest.TestCase):
    def test_full_saas_api_browse_fanout_router_and_health_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            webhooks_received = []

            def mock_driver(engine: str, url: str, session_name: str) -> str:
                return f"<html><body><h1>Scraped {url}</h1><p>Engine: {engine}</p></body></html>"

            def mock_webhook_sender(url: str, body: bytes, headers: dict) -> int:
                webhooks_received.append(
                    (url, json.loads(body.decode("utf-8")), headers)
                )
                return 200

            server = BrowserFarmSaaSServer(
                host="127.0.0.1",
                port=0,
                db_dir=tmp,
                profiles=fixture_profiles(),
                driver_fn=mock_driver,
                webhook_sender_fn=mock_webhook_sender,
            )
            server.start_background()
            try:
                base_url = f"http://127.0.0.1:{server.port}"

                # 1. Health Endpoint
                with urllib.request.urlopen(f"{base_url}/v1/health", timeout=5) as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(health["status"], "degraded")
                self.assertFalse(health["upstream_ready"])

                # 2. Submit Browse Job + Webhook Delivery
                req_data = json.dumps(
                    {
                        "url": "https://target.example.com/pricing",
                        "goal": "Get pricing",
                        "needs_vision": False,
                        "js_complexity": "low",
                        "webhook_url": "https://customer.example.com/callback",
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{base_url}/v1/jobs/browse",
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    job_res = json.loads(resp.read().decode("utf-8"))

                self.assertEqual(job_res["status"], "completed")
                self.assertIn(
                    "# Scraped https://target.example.com/pricing",
                    job_res["extracted_markdown"],
                )
                self.assertEqual(len(webhooks_received), 1)
                self.assertIn("X-BrowserFarm-Signature", webhooks_received[0][2])

                # 3. Fetch Job by ID
                job_id = job_res["job_id"]
                with urllib.request.urlopen(
                    f"{base_url}/v1/jobs/{job_id}", timeout=5
                ) as resp:
                    fetched = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(fetched["job_id"], job_id)
                self.assertEqual(fetched["status"], "completed")

                # 4. OpenAI-Compatible Custom Provider Proxy (/v1/models & /v1/chat/completions)
                with urllib.request.urlopen(f"{base_url}/v1/models", timeout=5) as resp:
                    models_payload = json.loads(resp.read().decode("utf-8"))
                model_ids = {m["id"] for m in models_payload["data"]}
                self.assertIn("oracle/auto", model_ids)
                self.assertIn("oracle/free", model_ids)
                self.assertIn("google/gemini-4-argon", model_ids)

                chat_req_body = json.dumps(
                    {
                        "model": "oracle/auto",
                        "messages": [
                            {"role": "user", "content": "Karmaşık bir mimari tasarım planı çıkar"}
                        ],
                        "tools": [{"type": "function", "function": {"name": "terminal"}}],
                    }
                ).encode("utf-8")
                chat_req = urllib.request.Request(
                    f"{base_url}/v1/chat/completions",
                    data=chat_req_body,
                    headers={
                        "Content-Type": "application/json",
                        "x-hermes-session-id": "sess_test_affinity_01",
                    },
                    method="POST",
                )
                # Without an upstream, never invent a successful model response.
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(chat_req, timeout=5)
                self.assertEqual(ctx.exception.code, 502)

                # 5. Model Profiles Registry Endpoint (/v1/models/profiles)
                with urllib.request.urlopen(
                    f"{base_url}/v1/models/profiles", timeout=5
                ) as resp:
                    prof_res = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(prof_res["total_models"], 4)
                self.assertEqual(prof_res["routable"], 3)
                self.assertEqual(prof_res["profiles"]["test/catalog-only"]["status"], "catalog_only")
                self.assertEqual(prof_res["profiles"]["google/gemini-4-argon"]["intelligence_index"], 52.6)
                virtual = next(m for m in models_payload["data"] if m["id"] == "oracle/auto")
                self.assertEqual(virtual["context_length"], 1048576)  # largest window; plan() filters by fit
            finally:
                server.shutdown()


    def test_router_forwards_real_payload_and_keeps_session_model_sticky(self):
        received = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                received.append(body)
                response = json.dumps({
                    "id": "upstream-real-id", "object": "chat.completion",
                    "model": body["model"],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "upstream-answer"}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 17},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            router = BrowserFarmSaaSServer(
                port=0, db_dir=tmp, profiles=fixture_profiles(),
                nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1",
            )
            router.start_background()
            try:
                url = f"http://127.0.0.1:{router.port}/v1/chat/completions"
                for text in ("mimari tasarım analizi", "Merhaba"):
                    data = json.dumps({
                        "model": "oracle/auto", "messages": [{"role": "user", "content": text}],
                        "tools": [{"type": "function", "function": {"name": "terminal", "parameters": {"type": "object", "properties": {}}}}],
                        "temperature": 0.4,
                    }).encode()
                    req = urllib.request.Request(url, data=data, method="POST", headers={
                        "Content-Type": "application/json", "x-hermes-session-id": "same-session",
                    })
                    with urllib.request.urlopen(req, timeout=5) as response:
                        result = json.load(response)
                    self.assertEqual(result["id"], "upstream-real-id")
                    self.assertEqual(result["choices"][0]["message"]["content"], "upstream-answer")
                    self.assertEqual(result["usage"]["total_tokens"], 17)
                self.assertEqual(received[0]["model"], received[1]["model"])
                self.assertEqual(received[0]["model"], "google/gemini-4-argon")  # escalated, then no downgrade
                self.assertEqual(received[1]["messages"][0]["content"], "Merhaba")
                self.assertEqual(received[1]["temperature"], 0.4)
                self.assertEqual(received[0]["tools"][0]["function"]["name"], "terminal")
            finally:
                router.shutdown()
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=3)

    def test_router_passes_through_streamed_tool_calls_and_upstream_errors(self):
        calls = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append(body)
                if body.get("stream"):
                    chunks = [
                        b'data: {"id":"real-1","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1","type":"function","function":{"name":"terminal","arguments":"{}"}}]}}]}\n\n',
                        b'data: [DONE]\n\n',
                    ]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for chunk in chunks:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    return
                data = b'{"error":{"message":"capacity exceeded"}}'
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                router = BrowserFarmSaaSServer(
                    port=0, db_dir=tmp, profiles=fixture_profiles(),
                    nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1"
                )
                router.start_background()
                try:
                    base = f"http://127.0.0.1:{router.port}/v1/chat/completions"
                    def make_request(stream):
                        return urllib.request.Request(
                            base, data=json.dumps({"model": "google/gemini-4-argon", "stream": stream,
                                                   "messages": [{"role": "user", "content": "call a tool"}]}).encode(),
                            headers={"Content-Type": "application/json"}, method="POST"
                        )
                    with urllib.request.urlopen(make_request(True), timeout=5) as response:
                        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
                        events = response.read()
                    self.assertIn(b'"tool_calls"', events)
                    self.assertIn(b'data: [DONE]', events)
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        urllib.request.urlopen(make_request(False), timeout=5)
                    self.assertEqual(ctx.exception.code, 429)
                    self.assertIn(b'capacity exceeded', ctx.exception.read())
                    self.assertEqual(len(calls), 2)
                    stats = router.live.model_stats("google/gemini-4-argon")
                    self.assertEqual((stats["requests"], stats["errors"]), (2, 1))
                    self.assertIn("google/gemini-4-argon", router.live.cooling_down())
                finally:
                    router.shutdown()
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=3)

    def test_stream_first_event_arrives_before_upstream_finishes(self):
        import threading
        release = threading.Event()

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"id":"first"}\n\n')
                self.wfile.flush()
                release.wait(3)
                self.wfile.write(b'data: [DONE]\n\n')

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                router = BrowserFarmSaaSServer(
                    port=0, db_dir=tmp, profiles=fixture_profiles(),
                    nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1"
                )
                router.start_background()
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{router.port}/v1/chat/completions",
                        data=b'{"model":"google/gemini-4-argon","messages":[{"role":"user","content":"hi"}],"stream":true}',
                        headers={"Content-Type": "application/json"}, method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=1) as response:
                        self.assertIn(b'"first"', response.readline())
                finally:
                    release.set()
                    router.shutdown()
        finally:
            release.set()
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=3)

    def test_legacy_router_complete_does_not_fabricate_model_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = BrowserFarmSaaSServer(port=0, db_dir=tmp)
            router.start_background()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{router.port}/v1/router/complete",
                    data=b'{"prompt":"hello"}',
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(ctx.exception.code, 501)
            finally:
                router.shutdown()

    def test_router_refuses_unsafe_public_bind_without_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                BrowserFarmSaaSServer(host="0.0.0.0", port=0, db_dir=tmp)

    def test_router_fails_closed_without_upstream(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            unused_port = s.getsockname()[1]
        with tempfile.TemporaryDirectory() as tmp:
            router = BrowserFarmSaaSServer(
                port=0, db_dir=tmp, profiles=fixture_profiles(),
                nous_proxy_url=f"http://127.0.0.1:{unused_port}/v1"
            )
            router.start_background()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{router.port}/v1/chat/completions",
                    data=json.dumps({"model": "oracle/auto", "messages": [{"role": "user", "content": "hi"}]}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(ctx.exception.code, 502)
                # A dead proxy is not a model failure: no cooldowns, no per-model error events.
                self.assertEqual(router.live.cooling_down(), set())
                self.assertEqual(router.live.model_stats("test/cheap")["requests"], 0)
            finally:
                router.shutdown()

    def test_without_registry_virtual_profiles_refuse_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = BrowserFarmSaaSServer(port=0, db_dir=tmp)
            router.start_background()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{router.port}/v1/chat/completions",
                    data=json.dumps({"model": "oracle/auto", "messages": [{"role": "user", "content": "hi"}]}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(ctx.exception.code, 422)
            finally:
                router.shutdown()

    def test_rate_limited_candidate_falls_back_and_effort_and_usage_are_handled(self):
        received = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(body)
                if body["model"] == "test/mid":
                    data, status = b'{"error":{"message":"rate limited"}}', 429
                else:
                    data, status = json.dumps({
                        "id": "real", "model": body["model"],
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                        "usage": {"prompt_tokens": 11, "completion_tokens": 3},
                    }).encode(), 200
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                router = BrowserFarmSaaSServer(
                    port=0, db_dir=tmp, profiles=fixture_profiles(),
                    nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1",
                )
                router.start_background()
                try:
                    url = f"http://127.0.0.1:{router.port}/v1/chat/completions"
                    # Tier-2 request ("python kodu") prefers test/mid, which is rate limited.
                    req = urllib.request.Request(url, method="POST", headers={"Content-Type": "application/json"},
                        data=json.dumps({"model": "oracle/auto", "reasoning_effort": "medium",
                                         "messages": [{"role": "user", "content": "python kodu yaz"}]}).encode())
                    with urllib.request.urlopen(req, timeout=5) as response:
                        selected = response.headers["X-Oracle-Selected-Model"]
                        self.assertEqual(json.load(response)["id"], "real")
                    self.assertEqual([b["model"] for b in received], ["test/mid", "google/gemini-4-argon"])
                    self.assertEqual(selected, "google/gemini-4-argon")
                    self.assertIn("test/mid", router.live.cooling_down())
                    self.assertEqual(router.live.model_stats("google/gemini-4-argon")["prompt_tokens"], 11)

                    # Effort is clamped to what the chosen model accepts (test/cheap: none/high).
                    req = urllib.request.Request(url, method="POST", headers={"Content-Type": "application/json"},
                        data=json.dumps({"model": "test/cheap", "reasoning_effort": "medium",
                                         "messages": [{"role": "user", "content": "selam"}]}).encode())
                    with urllib.request.urlopen(req, timeout=5):
                        pass
                    self.assertEqual(received[-1]["reasoning_effort"], "high")

                    # Hermes sends the same session id on auxiliary calls (titles, compression).
                    # An explicit-model auxiliary call must not overwrite the session's sticky model.
                    def send(model, text):
                        r = urllib.request.Request(url, method="POST", headers={
                            "Content-Type": "application/json", "x-hermes-session-id": "conv-1"},
                            data=json.dumps({"model": model, "messages": [{"role": "user", "content": text}]}).encode())
                        with urllib.request.urlopen(r, timeout=5) as resp:
                            return resp.headers["X-Oracle-Selected-Model"]
                    first = send("oracle/auto", "mimari tasarım")
                    send("test/cheap", "bu konuşmaya başlık üret")
                    self.assertEqual(send("oracle/auto", "devam"), first)
                finally:
                    router.shutdown()
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
