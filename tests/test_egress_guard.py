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


class StartEgressGuardBindTests(unittest.TestCase):
    """Proxy must never listen on 0.0.0.0 (LAN-exposed SSRF-policed relay)."""

    def tearDown(self):
        from src.browser_engine import egress_guard as eg
        if eg._current_guard is not None:
            eg._current_guard.stop()
        eg._current_guard = None

    def test_netns_mode_binds_only_veth_host_ip(self):
        from unittest import mock
        from src.browser_engine import egress_guard as eg
        captured = {}
        real_init = eg.EgressGuard.__init__

        def spy_init(self, policy=None, **kw):
            captured.update(kw)
            real_init(self, policy, **kw)

        with mock.patch.object(eg.EgressGuard, "__init__", spy_init), \
                mock.patch.object(eg.EgressGuard, "start", lambda self: 0), \
                mock.patch.object(eg, "_sudo_run"), \
                mock.patch.object(eg.atexit, "register"):
            eg.start_egress_guard(use_netns=True, proxy_port=0)
        self.assertEqual(captured.get("listen_host"), "10.255.255.1")

    def test_no_netns_mode_binds_loopback_only(self):
        from src.browser_engine import egress_guard as eg
        from unittest import mock
        captured = {}
        real_init = eg.EgressGuard.__init__

        def spy_init(self, policy=None, **kw):
            captured.update(kw)
            real_init(self, policy, **kw)

        with mock.patch.object(eg.EgressGuard, "__init__", spy_init), \
                mock.patch.object(eg.EgressGuard, "start", lambda self: 0), \
                mock.patch.object(eg.atexit, "register"):
            eg.start_egress_guard(use_netns=False, proxy_port=0)
        self.assertEqual(captured.get("listen_host"), "127.0.0.1")
