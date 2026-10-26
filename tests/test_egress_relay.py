"""Egress proxy network relay: connect to the validated IP and relay bytes.

Live test over localhost (no external network): the policy resolver is faked
and allow_literal permits the loopback address for this test. The relay is
exercised end-to-end: client -> proxy CONNECT -> validated IP backend -> echo.
RED first (egress_relay not yet written).
"""
import asyncio
import unittest

from src.browser_engine.egress_proxy import EgressPolicy
from src.browser_engine.egress_proxy_server import decide
from src.browser_engine.egress_relay import handle_client


def _dns(table):
    def resolve(host):
        if host not in table:
            raise OSError("nxdomain")
        return table[host]
    return resolve


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_tunnel_relays_bytes(self):
        # Backend echo server on localhost.
        async def echo(reader, writer):
            data = await reader.read(4096)
            writer.write(b"echo:" + data)
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        # Test-only policy: allow the loopback literal (real policy denies it;
        # the netns block is the production backstop for the relay's own path).
        policy = EgressPolicy(resolver=_dns({}), allow_literal=True)

        # Drive handle_client with in-memory streams.
        class FakeWriter:
            def __init__(self):
                self.buf = bytearray()
            def write(self, b):
                self.buf += b
            async def drain(self):
                pass
            def close(self):
                pass
            def write_eof(self):
                pass
            def get_extra_info(self, name):
                return ("127.0.0.1", 0) if name == "peername" else None

        # Provide a reader whose first line is the CONNECT request.
        req = f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n".encode()
        reader = asyncio.StreamReader()
        reader.feed_data(req + b"ping")
        reader.feed_eof()

        fw = FakeWriter()
        await handle_client(reader, fw, policy)

        self.assertIn(b"200", fw.buf)  # tunnel established
        self.assertIn(b"echo:ping", fw.buf)  # backend echoed through the relay

        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
