"""Netns isolation + Chromium egress-proxy launch parameters.

Generates shell commands (so the plan is hermetic and testable) and the
Chromium launch args that pin egress to the proxy. The live sudo test in
tests/test_netns.py verifies the real isolation.

Design: the engine runs inside a network namespace whose only route is a
veth pair to the host, where the egress proxy listens. nftables inside the
namespace drops everything except traffic to the proxy host:port, so the
engine can only reach the proxy — which resolves/validates and connects to
the validated IP. DNS cannot leak (nothing else is routable).
"""



def plan_netns(*, namespace: str, veth_host: str, veth_ns: str,
               host_ip: str, ns_ip: str, proxy_host: str, proxy_port: int) -> str:
    """Shell script: create the namespace, veth pair, addresses, and nft drop-all-but-proxy."""
    return f"""#!/bin/sh
set -e
ip netns add {namespace}
ip link add {veth_host} type veth peer name {veth_ns}
ip link set {veth_ns} netns {namespace}
ip addr add {host_ip}/30 dev {veth_host}
ip link set {veth_host} up
ip netns exec {namespace} ip addr add {ns_ip}/30 dev {veth_ns}
ip netns exec {namespace} ip link set {veth_ns} up
ip netns exec {namespace} ip link set lo up
ip netns exec {namespace} ip route add default via {host_ip}
# nft: allow ONLY the proxy, drop everything else (no DNS/other egress possible).
ip netns exec {namespace} nft -f - <<'NFT'
table inet bf_egress {{
  chain output {{
    type filter hook output priority 0; policy drop;
    ip daddr {proxy_host} tcp dport {proxy_port} accept
    ct state established,related accept
  }}
}}
NFT
"""


def plan_teardown(*, namespace: str, veth_host: str) -> str:
    """Shell script: remove the namespace and its nft ruleset."""
    return f"""#!/bin/sh
ip netns exec {namespace} nft flush ruleset 2>/dev/null || true
ip netns del {namespace} 2>/dev/null || true
ip link del {veth_host} 2>/dev/null || true
"""


def chromium_proxy_args(*, proxy_host: str, proxy_port: int) -> list[str]:
    """Chromium launch args: route egress through the proxy and block raw DNS.

    MAP * ~NOTFOUND makes Chrome fail any direct resolve, EXCLUDE lets it reach
    the proxy host itself. Combined with the netns drop-all, no DNS leak is
    possible.
    """
    return [
        f"--proxy-server=http://{proxy_host}:{proxy_port}",
        f"--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE {proxy_host}",
    ]
