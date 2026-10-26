"""Egress proxy server: policy-validated requests + per-hop redirect checks.

RED first. Hermetic: no sockets; we test the request-decision layer and the
redirect-hop validation loop. The network plumbing that connects to the
validated IP is exercised separately by the netns live test.
"""
import unittest

from src.browser_engine.egress_proxy import EgressDenied, EgressPolicy
from src.browser_engine.egress_proxy_server import (
    Decision,
    ProxyEndpoint,
    decide,
    decide_redirect,
)


def _dns(table):
    def resolve(host):
        if host not in table:
            raise OSError("nxdomain")
        return table[host]
    return resolve


class DecideTests(unittest.TestCase):
    def setUp(self):
        self.policy = EgressPolicy(resolver=_dns({"example.com": ["93.184.216.34"]}))
        self.endpoint = ProxyEndpoint(host="example.com", port=80)

    def test_absolute_http_request_is_parsed(self):
        d = decide(self.policy,
                   method="GET", target="http://example.com/index.html", version="HTTP/1.1")
        self.assertEqual(d.action, "forward")
        self.assertEqual(d.host, "example.com")
        self.assertEqual(d.port, 80)
        self.assertEqual(d.ip, "93.184.216.34")

    def test_connect_tunnel_is_parsed(self):
        d = decide(self.policy, method="CONNECT", target="example.com:443", version="HTTP/1.1")
        self.assertEqual(d.action, "tunnel")
        self.assertEqual(d.host, "example.com")
        self.assertEqual(d.port, 443)
        self.assertEqual(d.ip, "93.184.216.34")

    def test_private_host_denied(self):
        d = decide(self.policy, method="GET",
                   target="http://127.0.0.1:8080/x", version="HTTP/1.1")
        self.assertEqual(d.action, "deny")
        self.assertIsInstance(d.reason, EgressDenied)

    def test_malformed_request_denied(self):
        d = decide(self.policy, method="GET", target="not a url", version="HTTP/1.1")
        self.assertEqual(d.action, "deny")

    def test_endpoint_includes_validated_ip(self):
        self.assertEqual(self.endpoint, ProxyEndpoint(host="example.com", port=80))


class RedirectHopTests(unittest.TestCase):
    def setUp(self):
        self.policy = EgressPolicy(resolver=_dns({
            "a.example": ["93.184.216.34"],
            "internal.corp": ["10.1.2.3"],
        }))

    def test_redirect_to_private_hop_is_denied(self):
        self.policy.check_url("https://a.example/")  # hop 1 fine
        with self.assertRaises(EgressDenied):
            decide_redirect(self.policy, location="http://internal.corp/secret")

    def test_redirect_to_public_hop_allowed(self):
        loc = decide_redirect(self.policy, location="https://a.example/next")
        self.assertEqual(loc.host, "a.example")


if __name__ == "__main__":
    unittest.main()
