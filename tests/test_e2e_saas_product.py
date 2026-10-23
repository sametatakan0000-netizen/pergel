import json
import os
import tempfile
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from src.api.server import BrowserFarmSaaSServer



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
                            {"role": "user", "content": "Karmaşık tersine mühendislik mimarisi ve Ghidra decompile planı çıkar"}
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
                self.assertGreaterEqual(prof_res["total_models"], 64)
                self.assertIn("google/gemini-4-argon", prof_res["profiles"])
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
                port=0, db_dir=tmp,
                nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1",
            )
            router.start_background()
            try:
                url = f"http://127.0.0.1:{router.port}/v1/chat/completions"
                for text in ("Merhaba", "Ghidra mimari analizi"):
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
                self.assertEqual(received[1]["messages"][0]["content"], "Ghidra mimari analizi")
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
                    port=0, db_dir=tmp, nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1"
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
                    self.assertEqual(router.router.get_model_score("google/gemini-4-argon"), 0)
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
                    port=0, db_dir=tmp, nous_proxy_url=f"http://127.0.0.1:{upstream.server_port}/v1"
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
                port=0, db_dir=tmp, nous_proxy_url=f"http://127.0.0.1:{unused_port}/v1"
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
                self.assertEqual(router.router.get_model_score("upstage/solar-mini4"), 0)
            finally:
                router.shutdown()


if __name__ == "__main__":
    unittest.main()
