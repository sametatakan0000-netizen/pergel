"""Egress policy for the browser engine (SSRF enforcement at the connection point).

Principle: resolve the host ONCE, reject if ANY answer is non-public, and
connect to the validated address. Redirects are validated per hop by calling
``check_url`` again. Pure logic, DNS is injected so tests stay hermetic.
"""


import http.client
import ipaddress
import socket
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})


class EgressDenied(Exception):
    """Raised when a target violates the egress policy."""


class EgressAddressError(EgressDenied):
    """Raised when a host cannot be resolved to a usable address.

    Policy-wise a denial (subclass of EgressDenied), but callers that must tell
    "cannot resolve" (soft failure) from "non-public target" (hard SSRF block)
    catch this specifically."""


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
        raise EgressAddressError(f"host does not resolve: {host}") from exc
    if not answers:
        raise EgressAddressError(f"host does not resolve: {host}")
    validated = None
    for raw in answers:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise EgressAddressError(f"invalid address from resolver: {raw!r}") from exc
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

    @property
    def allows_private(self) -> bool:
        """True when private/loopback targets are an explicit opt-in for this
        request (``private_targets_allowed()`` sets it). Enforcement layers use
        this to skip strict plumbing (relay pinning, pre-flight) for dev fetches."""
        return self._allow_literal

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


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that DIALS a pre-validated IP instead of resolving the
    Host header (closes the DNS-rebinding TOCTOU window: the address that passed
    the egress check is exactly the address connected to)."""

    def __init__(self, host: str, pinned_ip: str, **kw):
        self._pinned_ip = pinned_ip
        super().__init__(host, **kw)

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS variant: TLS still authenticates the certificate against the hostname."""

    def __init__(self, host: str, pinned_ip: str, **kw):
        self._pinned_ip = pinned_ip
        super().__init__(host, **kw)

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pinned_ip: str):
        super().__init__()
        self._pinned_ip = pinned_ip

    def http_open(self, req):
        ip = self._pinned_ip
        return self.do_open(
            lambda host, **kw: _PinnedHTTPConnection(host, pinned_ip=ip, **kw), req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: str):
        super().__init__()
        self._pinned_ip = pinned_ip

    def https_open(self, req):
        ip = self._pinned_ip
        return self.do_open(
            lambda host, **kw: _PinnedHTTPSConnection(host, pinned_ip=ip, **kw), req)


def pinned_opener(pinned_ip: str) -> urllib.request.OpenerDirector:
    """Opener that connects to ``pinned_ip`` regardless of the URL's hostname.

    Deliberately NO redirect handler: HTTPError(3xx) surfaces to the caller,
    which must re-validate the next hop through the egress policy before
    following it (redirect-to-private stays a closed path).
    """
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_PinnedHTTPHandler(pinned_ip))
    opener.add_handler(_PinnedHTTPSHandler(pinned_ip))
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    opener.add_handler(urllib.request.UnknownHandler())
    return opener
