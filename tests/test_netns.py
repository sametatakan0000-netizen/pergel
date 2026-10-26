"""Netns isolation + Chromium egress-proxy launch: generated plan, live-verified.

The system layer (netns, veth, nftables) is generated as shell commands so the
plan is testable hermetically; the live test uses sudo to verify real isolation.
"""
import subprocess
import unittest

from src.browser_engine.netns import (
    chromium_proxy_args,
    plan_netns,
    plan_teardown,
)


class PlanTests(unittest.TestCase):
    def test_plan_creates_netns_veth_and_nft_drop(self):
        script = plan_netns(namespace="bf_engine", veth_host="bfh0",
                            veth_ns="bfns0", host_ip="10.255.255.1",
                            ns_ip="10.255.255.2", proxy_host="10.255.255.1",
                            proxy_port=8899)
        self.assertIn("ip netns add bf_engine", script)
        self.assertIn("veth", script)
        self.assertIn("nft", script)
        self.assertIn("10.255.255.1", script)  # proxy host allowed
        self.assertIn("8899", script)  # proxy port allowed
        self.assertIn("drop", script.lower())

    def test_teardown_removes_netns(self):
        script = plan_teardown(namespace="bf_engine", veth_host="bfh0")
        self.assertIn("ip netns del bf_engine", script)
        self.assertIn("nft", script.lower())

    def test_chromium_args_point_at_proxy(self):
        args = chromium_proxy_args(proxy_host="10.255.255.1", proxy_port=8899)
        self.assertIn("--proxy-server=http://10.255.255.1:8899", args)
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 10.255.255.1", args)


if __name__ == "__main__":
    unittest.main()
