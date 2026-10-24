"""Deterministic local pages so engine overhead is measured without network noise."""
import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MARKERS = {"static": "ARTICLE-MARKER-7f3a", "spa": "SPA-MARKER-b81c", "heavy": "HEAVY-MARKER-02de"}
MAX_HEAVY_ROWS = 50000

STATIC = ("<!doctype html><html><head><title>Static</title></head><body><nav>menu</nav><article>"
          f"<h1>Static article</h1><p>{MARKERS['static']} " + "Lorem ipsum dolor sit amet. " * 80 +
          "</p></article><footer>f</footer></body></html>")

# The marker is assembled at runtime from two halves, so it appears in the DOM only if JS actually ran
# (a literal marker in the <script> source would make raw HTML and rendered HTML indistinguishable).
_HEAD, _TAIL = MARKERS["spa"][:9], MARKERS["spa"][9:]
SPA = ("<!doctype html><html><head><title>SPA</title></head><body><div id=\"app\">loading</div><script>"
       "(async () => {"
       "const p = await (await fetch('/api/product')).json();"
       "const r = await (await fetch('/api/reviews')).json();"
       f"const m = '{_HEAD}' + '{_TAIL}';"
       "document.getElementById('app').innerHTML = '<h1>' + p.name + '</h1><p>' + m + ' ' + r.items.join(' | ') + '</p>';"
       "})();</script></body></html>")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body: str, ctype: str = "text/html; charset=utf-8", status: int = 200) -> None:
        raw = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        if url.path == "/static":
            return self._send(STATIC)
        if url.path == "/spa":
            return self._send(SPA)
        if url.path == "/api/product":
            return self._send(json.dumps({"name": "Widget"}), "application/json")
        if url.path == "/api/reviews":
            time.sleep(0.05)  # fixed server think-time, identical for every engine
            return self._send(json.dumps({"items": ["good", "fine", "ok"]}), "application/json")
        if url.path == "/heavy":
            n = min(int(q.get("n", ["2000"])[0]), MAX_HEAVY_ROWS)
            rows = "".join(f"<div class='r'><span>row {i}</span></div>" for i in range(n))
            return self._send(f"<!doctype html><html><body>{rows}<p>{MARKERS['heavy']}</p></body></html>")
        if url.path == "/robots.txt":
            return self._send("User-agent: *\nAllow: /\n", "text/plain")
        self._send("not found", status=404)


@contextlib.contextmanager
def fixture_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
