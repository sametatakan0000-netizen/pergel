"""EgressGuard: live proxy must bind before returning and deny private targets."""
import asyncio
import unittest

from src.browser_engine.egress_guard import EgressGuard
from src.browser_engine.egress_proxy import EgressPolicy


class EgressGuardTests(unittest.TestCase):
    def test_start_returns_real_bound_port(self):
        guard = EgressGuard(EgressPolicy(), listen_port=0)
        port = guard.start()
        try:
            self.assertGreater(port, 0)
        finally:
            guard.stop()

    def test_default_policy_denies_loopback_with_403(self):
        guard = EgressGuard(EgressPolicy(), listen_port=0)
        port = guard.start()
        try:
            async def probe():
                r, w = await asyncio.open_connection("127.0.0.1", port)
                w.write(b"GET http://127.0.0.1:1/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                await w.drain()
                data = await asyncio.wait_for(r.read(300), 5)
                w.close()
                return data
            data = asyncio.run(probe())
            self.assertIn(b"403", data.split(b"\r\n")[0])
        finally:
            guard.stop()


if __name__ == "__main__":
    unittest.main()
