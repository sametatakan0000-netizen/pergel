"""Dry-run routing smoke: real public registry, echo upstream (no inference, no cost)."""
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

seen = []


class Echo(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b'{"data":[]}'
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append(req)
        body = json.dumps({"id": "echo", "model": req["model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


up = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
threading.Thread(target=up.serve_forever, daemon=True).start()
tmp = tempfile.mkdtemp()
proc = subprocess.Popen([sys.executable, "-m", "src.cli", "serve", "--port", "18190", "--db-dir", tmp,
                         "--nous-proxy-url", f"http://127.0.0.1:{up.server_port}/v1"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
try:
    print(proc.stdout.readline().strip())
    base = "http://127.0.0.1:18190/v1"
    for _ in range(60):  # wait for first registry refresh
        health = json.load(urllib.request.urlopen(base + "/health", timeout=5))
        if health["registry"]["routable"]:
            break
        time.sleep(1)
    print("health:", health["status"], health["registry"])
    models = json.load(urllib.request.urlopen(base + "/models", timeout=5))["data"]
    print("oracle/auto context_length:", next(m for m in models if m["id"] == "oracle/auto")["context_length"])

    def ask(model, text, effort=None, session=None, image=False):
        content = [{"type": "text", "text": text}]
        if image:
            content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}})
        payload = {"model": model, "messages": [{"role": "user", "content": content}],
                   "tools": [{"type": "function", "function": {"name": "terminal"}}]}
        if effort:
            payload["reasoning_effort"] = effort
        headers = {"Content-Type": "application/json"}
        if session:
            headers["x-hermes-session-id"] = session
        r = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code} {e.read().decode()[:120]}"
        sent = seen[-1]
        return f"{sent['model']}  effort_sent={sent.get('reasoning_effort')}"

    print("auto  'merhaba'               ->", ask("oracle/auto", "merhaba", "medium"))
    print("auto  'python kodu düzelt'    ->", ask("oracle/auto", "python kodu düzelt", "medium"))
    print("auto  'mimari tasarım planı'  ->", ask("oracle/auto", "mimari tasarım planı", "xhigh"))
    print("auto  image 'bu ne?'          ->", ask("oracle/auto", "bu ne?", image=True))
    print("premium 'selam'               ->", ask("oracle/premium", "selam", "max"))
    print("free  'selam'                 ->", ask("oracle/free", "selam"))
    print("session s1: mimari -> devam   ->", ask("oracle/auto", "mimari tasarım", session="s1"), "|", ask("oracle/auto", "devam", session="s1"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:200])
finally:
    proc.terminate(); proc.wait(timeout=5); up.shutdown()
