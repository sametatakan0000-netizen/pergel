"""Production wiring: the adblock driver factory must accept an extension host
and pass it to every AdblockBrowserSession it creates.

RED before this change: make_adblock_driver(bundle) had no way to receive an
ExtensionHost, so the production driver never enforced extension rules.
"""
import unittest
from unittest import mock

from src.browser_engine.adblock_session import AdblockBundle, compile_adblock
from src.browser_engine import cdp_adblock_driver as drv
from src.browser_engine.extension_host import Extension, ExtensionHost


class DriverFactoryExtensionTests(unittest.TestCase):
    def test_factory_forwards_extension_host_to_session(self):
        host = ExtensionHost()
        seen = {}

        class Spy:
            def __init__(self, bundle, browser_path=None, extensions=None, **kw):
                seen["extensions"] = extensions
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False
            async def fetch(self, url, host=None, timeout=30.0):
                return {"html": ["<p>ok</p>"]}

        with mock.patch.object(drv, "AdblockBrowserSession", Spy), \
                mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard",
                           return_value=mock.MagicMock()):
            driver = drv.make_adblock_driver(AdblockBundle(), extensions=host)
            out = driver("engine", "https://example.com", "s")
        self.assertIs(seen["extensions"], host)
        self.assertEqual(out, "<p>ok</p>")

    def test_factory_without_extensions_is_unchanged(self):
        self.assertIsNotNone(drv.make_adblock_driver(compile_adblock([])))


if __name__ == "__main__":
    unittest.main()
