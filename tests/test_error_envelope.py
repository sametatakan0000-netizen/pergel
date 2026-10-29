"""Error-envelope + request_id contract.

Every JSON response (success and error) carries a top-level ``request_id`` for
log/response correlation. Every error body has ``error`` as a STRUCTURED object:

    {"error": {"code": "<stable_snake_case>", "message": "<human readable>", "domain": "<optional>"},
     "request_id": "<id>"}

``domain`` is present only where it is meaningful (target host). Callers may send
``X-Request-Id`` to supply their own correlation id; the server echoes it.
"""
import json
import socket as _socket
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

from src.api.server import BrowserFarmSaaSServer
from src.browser_engine.worker import FetchBlocked

PAGE = "<html><body><p>hello</p></body></html>"

_REAL_GETADDRINFO = _socket.getaddrinfo


def _fake_dns(host, *args, **kwargs):
    if isinstance(host, str) and host.endswith("example.com"):
        port = args[0] if args else kwargs.get("port", 0)
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
    return _REAL_GETADDRINFO(host, *args, **kwargs)


def setUpModule():
    _socket.getaddrinfo = _fake_dns
    # Hermetic: the fake DNS maps example.com to a non-routable test IP, so the
    # RSS/sitemap probe would hang on real TCP. Disable that adapter for this module
    # (its behaviour is covered by tests/test_rss_sitemap_adapter.py).
    global _RSS_SAVED
    from src.browser_engine import platform_adapters as _pa
    _RSS_SAVED = _pa.RssSitemapAdapter.fetch
    _pa.RssSitemapAdapter.fetch = lambda self, url, get: None


def tearDownModule():
    _socket.getaddrinfo = _REAL_GETADDRINFO
    from src.browser_engine import platform_adapters as _pa
    _pa.RssSitemapAdapter.fetch = _RSS_SAVED


def call(base, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json"}
    hdr.update(headers or {})
    req = urllib.request.Request(base + path, data=data,
                                 method="POST" if body is not None else "GET", headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


class _Base(unittest.TestCase):
    def setUp(self):
        # _RATE_BUCKETS is module-level and persists across test servers -> clear it
        # so one test's rate-limit exhaustion cannot bleed into the next (skill pitfall).
        from src.api import server as _srv
        _srv._RATE_BUCKETS.clear()

    def tearDown(self):
        from src.api import server as _srv
        _srv._RATE_BUCKETS.clear()

    def start(self, driver=None, search=None, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = BrowserFarmSaaSServer(port=0, db_dir=tmp.name, profiles={},
                                    driver_fn=driver or (lambda e, u, s: PAGE),
                                    search_fn=search, nous_proxy_url="http://127.0.0.1:9/v1", **kw)
        srv.start_background()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.port}"


class TestRequestId(_Base):
    def test_success_response_carries_request_id(self):
        base = self.start()
        st, body, _ = call(base, "/v1/health")
        self.assertEqual(st, 200)
        self.assertIn("request_id", body)
        self.assertTrue(body["request_id"])

    def test_request_id_echoed_from_header(self):
        base = self.start()
        st, body, _ = call(base, "/v1/jobs/browse", {"url": "https://x.example.com"},
                           headers={"X-Request-Id": "corr-123"})
        self.assertEqual(st, 200)
        self.assertEqual(body["request_id"], "corr-123")

    def test_error_response_carries_request_id_header_and_body(self):
        base = self.start()
        st, body, hdr = call(base, "/v1/jobs/browse", {})
        self.assertEqual(st, 400)
        self.assertIn("request_id", body)
        self.assertIn("X-Request-Id", hdr)


class TestErrorEnvelope(_Base):
    def assert_shape(self, body):
        err = body.get("error")
        self.assertIsInstance(err, dict, body)
        self.assertIn("code", err)
        self.assertIn("message", err)
        self.assertIsInstance(err["code"], str)
        self.assertIsInstance(err["message"], str)
        self.assertTrue(err["code"])
        # request_id is correlated both at the top level and inside error
        # (the latter matches tests/test_access_block_codes.py contract).
        self.assertTrue(body.get("request_id"), "top-level request_id required")
        self.assertTrue(err.get("request_id"), "error.request_id required")

    def test_validation_error_is_structured(self):
        base = self.start()
        st, body, _ = call(base, "/v1/jobs/browse", {})
        self.assertEqual(st, 400)
        self.assert_shape(body)

    def test_unknown_endpoint_error_is_structured(self):
        base = self.start()
        st, body, _ = call(base, "/v1/nope")
        self.assertEqual(st, 404)
        self.assert_shape(body)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_rate_limit_error_is_structured(self):
        base = self.start()
        # Exhaust the default RPM bucket (rpm default is low) until the server answers 429.
        got_429 = None
        for _ in range(200):
            st, body, _ = call(base, "/v1/jobs/browse", {"url": "https://x.example.com"})
            if st == 429:
                got_429 = body
                break
        self.assertIsNotNone(got_429, "expected to hit the rate limiter within 200 calls")
        self.assert_shape(got_429)
        self.assertEqual(got_429["error"]["code"], "rate_limited")

    def test_blocked_job_error_keeps_code_and_domain(self):
        def drv(e, u, s):
            raise FetchBlocked("robots", code="robots_disallowed")
        base = self.start(driver=drv)
        st, body, _ = call(base, "/v1/jobs/browse", {"url": "https://x.example.com"})
        self.assertEqual(st, 403)
        self.assert_shape(body)
        self.assertEqual(body["error"]["code"], "robots_disallowed")
        self.assertEqual(body["error"]["domain"], "x.example.com")
        self.assertIn("message", body["error"])

    def test_unresolvable_host_message_still_readable(self):
        import socket as _socket
        from unittest import mock
        real = _socket.getaddrinfo

        def deny(host, *args, **kwargs):
            if isinstance(host, str) and host.endswith(".invalid"):
                raise _socket.gaierror("nxdomain")
            return real(host, *args, **kwargs)
        base = self.start()
        with mock.patch("socket.getaddrinfo", deny):
            st, body, _ = call(base, "/v1/jobs/browse", {"url": "http://no-such-host.invalid/x"})
        self.assertEqual(st, 400)
        self.assert_shape(body)
        self.assertIn("resolve", body["error"]["message"])


if __name__ == "__main__":
    unittest.main()
