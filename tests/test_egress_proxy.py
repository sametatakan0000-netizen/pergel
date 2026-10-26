"""Egress proxy policy: resolve once, validate the IP, connect to THAT IP.

Hermetic: DNS is injected, no network. RED first.
"""
import unittest

from src.browser_engine.egress_proxy import (
    EgressDenied,
    EgressPolicy,
    pick_validated_address,
)


def _dns(table):
    def resolve(host):
        if host not in table:
            raise OSError("nxdomain")
        return table[host]
    return resolve


class PickValidatedAddressTests(unittest.TestCase):
    def test_public_address_is_returned(self):
        ip = pick_validated_address("example.com", _dns({"example.com": ["93.184.216.34"]}))
        self.assertEqual(ip, "93.184.216.34")

    def test_private_address_is_denied(self):
        with self.assertRaises(EgressDenied):
            pick_validated_address("evil.test", _dns({"evil.test": ["10.0.0.5"]}))

    def test_loopback_and_link_local_denied(self):
        for ip in ("127.0.0.1", "169.254.169.254", "::1", "fe80::1"):
            with self.subTest(ip=ip), self.assertRaises(EgressDenied):
                pick_validated_address("h.test", _dns({"h.test": [ip]}))

    def test_mixed_answer_denies_if_any_private(self):
        # Rebinding-style answer: one public + one private -> refuse the whole host.
        with self.assertRaises(EgressDenied):
            pick_validated_address("mix.test", _dns({"mix.test": ["93.184.216.34", "192.168.1.1"]}))

    def test_unresolvable_denied(self):
        with self.assertRaises(EgressDenied):
            pick_validated_address("nope.test", _dns({}))


class EgressPolicyTests(unittest.TestCase):
    def test_allows_public_http_and_https_only(self):
        policy = EgressPolicy(resolver=_dns({"example.com": ["93.184.216.34"]}))
        self.assertEqual(policy.check_url("https://example.com/a").ip, "93.184.216.34")
        with self.assertRaises(EgressDenied):
            policy.check_url("file:///etc/passwd")
        with self.assertRaises(EgressDenied):
            policy.check_url("gopher://example.com/")

    def test_redirect_hop_to_private_is_denied(self):
        policy = EgressPolicy(resolver=_dns({
            "a.example": ["93.184.216.34"],
            "meta.internal": ["169.254.169.254"],
        }))
        policy.check_url("https://a.example/")  # first hop ok
        with self.assertRaises(EgressDenied):
            policy.check_url("http://meta.internal/latest/meta-data")  # hop 2 denied

    def test_ip_literal_private_denied_without_dns(self):
        policy = EgressPolicy(resolver=_dns({}))
        with self.assertRaises(EgressDenied):
            policy.check_url("http://127.0.0.1:8080/")


if __name__ == "__main__":
    unittest.main()
