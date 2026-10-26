"""Egress policy for the browser engine (SSRF enforcement at the connection point).

Principle: resolve the host ONCE, reject if ANY answer is non-public, and
connect to the validated address. Redirects are validated per hop by calling
``check_url`` again. Pure logic, DNS is injected so tests stay hermetic.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})


class EgressDenied(Exception):
    """Raised when a target violates the egress policy."""


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


def pick_validated_address(host: str,
                           resolver: Callable[[str], Iterable[str]] = _system_resolver,
                           allow_private: bool = False) -> str:
    """Resolve ``host`` and return one validated address.

    Denies the host if resolution fails or if ANY returned address is non-public
    (a mixed public/private answer is the classic rebinding pattern).
    ``allow_private`` is a test-only escape hatch (see EgressPolicy.allow_literal).
    """
    try:
        answers = list(resolver(host))
    except OSError as exc:
        raise EgressDenied(f"host does not resolve: {host}") from exc
    if not answers:
        raise EgressDenied(f"host does not resolve: {host}")
    validated = None
    for raw in answers:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise EgressDenied(f"invalid address from resolver: {raw!r}") from exc
        if not _is_public(ip) and not allow_private:
            raise EgressDenied(f"non-public address for {host}: {raw}")
        validated = validated or str(ip)
    return validated  # type: ignore[return-value]


@dataclass(frozen=True)
class Egress:
    url: str
    host: str
    ip: str


class EgressPolicy:
    """Per-request policy. Call ``check_url`` for the first URL and every redirect hop."""

    def __init__(self, resolver: Callable[[str], Iterable[str]] = _system_resolver,
                 allow_literal: bool = False):
        self._resolver = resolver
        self._allow_literal = allow_literal

    def check_url(self, url: str) -> Egress:
        parts = urlsplit(url)
        if parts.scheme not in ALLOWED_SCHEMES:
            raise EgressDenied(f"scheme not allowed: {parts.scheme!r}")
        host = parts.hostname or ""
        if not host:
            raise EgressDenied("missing host")
        # IP literals are validated directly, without DNS.
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            ip = pick_validated_address(host, self._resolver,
                                        allow_private=self._allow_literal)
        else:
            if not _is_public(literal) and not self._allow_literal:
                raise EgressDenied(f"non-public literal: {host}")
            ip = str(literal)
        return Egress(url=url, host=host, ip=ip)
