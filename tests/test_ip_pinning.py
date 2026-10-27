"""DNS rebinding / IP pinning: the plain-HTTP fetch must CONNECT to the address
that passed egress validation, never re-resolve the hostname (TOCTOU).

Threat (found 2026-10-26, cf. tests/test_product_api rebinding cases):
`urlopen(url)` resolves the hostname AGAIN at connect time, so a name that
validated as public can flip to 169.254.169.254 / 127.0.0.1 between the
check and the connect. Fix shape (decided):
- resolve ONCE per fetch hop (`pick_validated_address`), dial that IP
  (`pinned_opener`), keep Host header + TLS SNI on the original hostname;
- every redirect hop is re-validated against the policy before connecting;
- policy denial at fetch time -> FetchBlocked(code="target_private_address").
"""
import http.server
import threading
import unittest
import urllib.parse

from src.browser_engine import worker as w
from src.browser_engine.egress_proxy import (
    Egress,
    EgressDenied,
    EgressPolicy,
    pinned_opener,
)

FAKE_OK = EgressPolicy(resolver=lambda host: ["127.0.0.1"], allow_literal=True)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/hop":
            self.send_response(302)
            self.send_header("Location", "http://second.test/private")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>pinned-ok</body></html>")

    def log_message(self, *args):
        pass


def _serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class TestPinnedOpener(unittest.TestCase):
    def test_opener_dials_ip_and_never_resolves_hostname(self):
        # The hostname must not need to resolve at all: the opener dials the
        # pinned IP literally (that IS the pinning guarantee).
        srv = _serve()
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        opener = pinned_opener("127.0.0.1")
        with opener.open(f"http://no-such-host.test:{port}/x", timeout=5) as resp:
            body = resp.read().decode()
        self.assertIn("pinned-ok", body)


class TestFetchPinning(unittest.TestCase):
    def setUp(self):
        w._ROBOTS_CACHE.clear()

    def test_fetch_pins_to_validated_ip_single_resolution(self):
        # The hostname must be resolved exactly ONCE (the validation resolve);
        # robots.txt fetch and the page fetch both ride the same pin.
        srv = _serve()
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        calls = []

        def resolver(host):
            calls.append(host)
            return ["127.0.0.1"]

        policy = EgressPolicy(resolver=resolver, allow_literal=True)
        text = w._default_url_raw(
            "lightpanda", f"http://pinned.test:{port}/page", "s", policy=policy
        )
        self.assertIn("pinned-ok", text)
        self.assertEqual(calls, ["pinned.test"])

    def test_strict_policy_denies_private_target_before_connect(self):
        with self.assertRaises(w.FetchBlocked) as cm:
            w._default_url_raw("lightpanda", "http://127.0.0.1:9/x", "s")
        self.assertEqual(cm.exception.code, "target_private_address")

    def test_non_http_schemes_are_blocked(self):
        # Measured 2026-10-27: ftp/data/file/javascript all reject with
        # "scheme not allowed" before any resolution happens.
        for url in ("ftp://203.0.113.5/x", "data:text/html,<p>hi</p>",
                    "file:///etc/passwd", "javascript:alert(1)"):
            with self.assertRaises(w.FetchBlocked) as cm:
                w._default_url_raw("lightpanda", url, "s")
            self.assertEqual(cm.exception.code, "target_private_address")


class _ScriptedPolicy:
    """Hop 1 (pinned.test) passes pinned to 127.0.0.1; any other host is denied."""

    def __init__(self):
        self.seen = []

    def check_url(self, url):
        host = urllib.parse.urlsplit(url).hostname
        self.seen.append(host)
        if host == "pinned.test":
            return Egress(url=url, host=host, ip="127.0.0.1")
        raise EgressDenied(f"non-public address for {host}")


class TestRedirectRevalidation(unittest.TestCase):
    def test_redirect_to_denied_host_is_blocked_and_not_fetched(self):
        srv = _serve()
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        policy = _ScriptedPolicy()
        with self.assertRaises(w.FetchBlocked) as cm:
            w._pinned_fetch(f"http://pinned.test:{port}/hop", policy, timeout=5)
        self.assertEqual(cm.exception.code, "target_private_address")
        self.assertEqual(policy.seen, ["pinned.test", "second.test"])


if __name__ == "__main__":
    unittest.main()
