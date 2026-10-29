"""Egress proxy relay: policy-validated connections, byte relaying.

``handle_client`` serves one proxied connection over asyncio streams:
  CONNECT  -> validate, connect to the validated IP, reply 200, splice bytes.
  other    -> forward-form HTTP with per-hop redirect validation.

The caller supplies the streams so tests can drive it with in-memory streams.
"""


import asyncio
from typing import Optional

from .egress_proxy import Egress, EgressDenied, EgressPolicy
from .egress_proxy_server import decide, decide_redirect

_MAX_LINE = 8192


async def _read_request(reader: asyncio.StreamReader):
    """Read a proxy request line + headers. Returns (method, target, version, headers) or None."""
    try:
        line = await reader.readuntil(b"\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        return None
    if not line or line == b"\r\n":
        return None
    parts = line.decode("latin-1", "replace").strip().split(" ", 2)
    if len(parts) != 3:
        return None
    method, target, version = parts
    headers = []
    try:
        while True:
            h = await reader.readuntil(b"\r\n")
            if h == b"\r\n":
                break
            headers.append(h.decode("latin-1", "replace"))
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        return None
    return method, target, version, headers


async def _splice(a_reader, a_writer, b_reader, b_writer):
    """Bidirectional byte relay until both directions see EOF.

    A pump that hits EOF on its source half-closes its writer (``write_eof``)
    so the peer sees end-of-stream, but does NOT tear the connection down —
    the return direction may still be carrying an in-flight response. Writers
    are fully closed only after both pumps finish.
    """
    async def pump(r, w):
        try:
            while True:
                data = await r.read(65536)
                if not data:
                    break
                w.write(data)
                await w.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            # Half-close: signal EOF to the peer without killing the return path.
            try:
                w.write_eof()
            except (AttributeError, OSError):
                pass

    t1 = asyncio.create_task(pump(a_reader, b_writer))
    t2 = asyncio.create_task(pump(b_reader, a_writer))
    await asyncio.gather(t1, t2)
    for w in (a_writer, b_writer):
        try:
            w.close()
        except Exception:
            pass


def _peer(writer) -> Optional[str]:
    try:
        return writer.get_extra_info("peername")
    except Exception:
        return None


async def handle_client(reader: asyncio.StreamReader, writer, policy: EgressPolicy):
    """Serve one proxied connection. Pure over the given streams."""
    parsed = await _read_request(reader)
    if parsed is None:
        writer.close()
        return
    method, target, version, headers = parsed

    d = decide(policy, method=method, target=target, version=version)
    if d.action == "deny":
        reason = str(d.reason) if d.reason else "denied"
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: %d\r\n\r\n%s"
                     % (len(reason), reason.encode()))
        await writer.drain()
        writer.close()
        return

    # Connect to the VALIDATED IP, not the hostname (resolve-once, connect-to-IP).
    try:
        b_reader, b_writer = await asyncio.open_connection(d.ip, d.port)
    except OSError as exc:
        msg = f"upstream connect failed: {exc}".encode()
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: %d\r\n\r\n%s"
                     % (len(msg), msg))
        await writer.drain()
        writer.close()
        return

    if d.action == "tunnel":
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await _splice(reader, writer, b_reader, b_writer)
        return

    # Forward: rewrite the request to origin-form and send it to the IP.
    from urllib.parse import urlsplit
    parts = urlsplit(target)
    origin_form = parts.path or "/"
    if parts.query:
        origin_form += "?" + parts.query
    req = f"{method} {origin_form} {version}\r\n".encode()
    for h in headers:
        low = h.lower()
        if low.startswith("proxy-connection:") or low.startswith("proxy-authorization:"):
            continue
        req += h.encode("latin-1")
    req += b"\r\n"
    b_writer.write(req)
    await b_writer.drain()

    # Relay the response, validating any redirect hop before forwarding it.
    await _forward_response(reader, writer, b_reader, b_writer, policy)


async def _forward_response(client_reader, client_writer, up_reader, up_writer, policy):
    """Relay upstream response bytes to the client; validate redirect hops.

    For a 3xx with a Location header we validate the hop via policy. If the
    target is private we refuse (403) instead of relaying the redirect.
    """
    try:
        head = await up_reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        client_writer.close()
        up_writer.close()
        return

    status_line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    status = int(status_line.split(" ")[1]) if len(status_line.split(" ")) > 1 else 0

    if 300 <= status < 400:
        for raw in head.split(b"\r\n"):
            if raw.lower().startswith(b"location:"):
                loc = raw.split(b":", 1)[1].strip().decode("latin-1", "replace")
                try:
                    decide_redirect(policy, location=loc)
                except EgressDenied as exc:
                    reason = f"redirect denied: {exc}".encode()
                    client_writer.write(
                        b"HTTP/1.1 403 Forbidden\r\nContent-Length: %d\r\n\r\n%s"
                        % (len(reason), reason))
                    await client_writer.drain()
                    client_writer.close()
                    up_writer.close()
                    return

    client_writer.write(head)
    await client_writer.drain()
    await _splice(client_reader, client_writer, up_reader, up_writer)
