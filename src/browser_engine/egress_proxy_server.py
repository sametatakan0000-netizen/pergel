"""Policy layer for the egress HTTP proxy (decision-making, no sockets).

The network plumbing (accept, connect to the validated IP, splice bytes)
sits above these pure decisions so the SSRF policy is testable hermetically.

Terminology:
  forward  -> absolute-form HTTP request (plaintext); the proxy rewrites and
              sends it to the validated IP, re-checking redirects per hop.
  tunnel   -> CONNECT; validated at setup. Note: inside the TLS tunnel the
              proxy cannot see subsequent hops — the netns isolation is the
              backstop for that (a tunnel can only reach public addresses).
  deny     -> policy refusal (EgressDenied or malformed input).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .egress_proxy import Egress, EgressDenied, EgressPolicy


@dataclass(frozen=True)
class ProxyEndpoint:
    host: str
    port: int


@dataclass(frozen=True)
class Decision:
    action: str  # "forward" | "tunnel" | "deny"
    host: str = ""
    port: int = 0
    ip: str = ""
    path: str = ""
    reason: Optional[EgressDenied] = None


def decide(policy: EgressPolicy, *, method: str, target: str, version: str = "HTTP/1.1") -> Decision:
    """Validate a proxy request line. target is absolute-form, or host:port for CONNECT."""
    method = (method or "").upper()
    if not target or " " in target or not version.startswith("HTTP/"):
        return Decision(action="deny",
                        reason=EgressDenied("malformed request line"))
    try:
        if method == "CONNECT":
            host, _, port_text = target.rpartition(":")
            if not host or not port_text.isdigit():
                raise EgressDenied("malformed CONNECT target")
            port = int(port_text)
            url = f"https://{host}:{port}/"
        else:
            from urllib.parse import urlsplit
            parts = urlsplit(target)
            if not parts.scheme or not parts.hostname:
                raise EgressDenied("malformed absolute URL")
            host = parts.hostname
            port = parts.port or (443 if parts.scheme == "https" else 80)
            url = target

        eg: Egress = policy.check_url(url)
    except EgressDenied as exc:
        return Decision(action="deny", reason=exc)

    action = "tunnel" if method == "CONNECT" else "forward"
    return Decision(action=action, host=eg.host, port=port, ip=eg.ip,
                    path="/" if method == "CONNECT" else "")


def decide_redirect(policy: EgressPolicy, *, location: str) -> Egress:
    """Validate a redirect hop. Raises EgressDenied for private/scheme-violating targets."""
    return policy.check_url(location)
