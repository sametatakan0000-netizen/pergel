"""SSRF enforcement is WIRING, not shelfware: guards and relays must actually be
connected on the real serving paths.

Audit 2026-10-29 (morning briefing) found two dead seams:

1. ``cdp_bridge`` accepted an ``ssrf_guard`` but ``AdblockBrowserSession`` /
   ``make_adblock_driver`` never passed one — so the server.py docstring's claim
   ("redirect-to-private IS closed at the enforcement layer") was FALSE on the
   default CDP serving path: a redirect-to-private during a link-preview fetch
   would render an intranet/private page and leak its HTML into the result.
2. Sub-process engines (lightpanda, pooled chromium) only routed through the
   validating EgressRelay under ORACLE_EGRESS_ENFORCE=1; without it they resolve
   DNS themselves and follow redirects internally — the engine-level pre-flight
   covers the entry URL only (redirect-to-private + rebinding windows).

RED tests first; then the wiring lands.
"""
import asyncio
import os
import sys
import types
import unittest
from unittest import mock

from src.browser_engine.egress_proxy import EgressPolicy


def _public_policy(allow_literal: bool = False) -> EgressPolicy:
    """Hermetic resolver stub: every host resolves to a public address."""
    return EgressPolicy(resolver=lambda host: ["93.184.216.34"],
                        allow_literal=allow_literal)


def _fake_bundle():
    from src.browser_engine.rule_engine import compile_rules
    return types.SimpleNamespace(network=compile_rules([]))


class MakeSsrfGuardTests(unittest.TestCase):
    """policy_ssrf_guard: the CDP request gate, one decision with the pre-flight.

    The contract (matches test_cdp_ssrf_guard's _private_guard): True marks an
    SSRF-risk target (private/loopback, fail-closed on unresolvable). Non-network
    schemes (data:, blob:, chrome-extension:, about:) are not SSRF-able hops and
    must pass, or extension/startup resources break.
    """

    def _guard(self, policy):
        from src.browser_engine.cdp_adblock_driver import make_ssrf_guard
        return make_ssrf_guard(lambda: policy)

    def test_private_literal_targets_are_flagged(self):
        guard = self._guard(_public_policy())
        for url in ("http://127.0.0.1/x", "http://10.0.0.5/",
                    "http://169.254.169.254/latest/meta-data/",
                    "http://[::1]/admin", "http://192.168.1.1/"):
            self.assertTrue(guard(url), url)

    def test_public_targets_pass(self):
        guard = self._guard(_public_policy())
        self.assertFalse(guard("http://93.184.216.34/"))
        self.assertFalse(guard("https://example.com/page"))

    def test_hostname_resolving_to_private_is_flagged(self):
        pol = EgressPolicy(resolver=lambda host: ["10.0.0.5"])
        self.assertTrue(self._guard(pol)("http://intranet.test/"))

    def test_unresolvable_host_is_flagged_fail_closed(self):
        pol = EgressPolicy(resolver=lambda host: [])
        self.assertTrue(self._guard(pol)("http://no-such-host.test/"))

    def test_non_network_schemes_pass(self):
        guard = self._guard(_public_policy())
        for url in ("data:text/html,<b>x</b>", "chrome-extension://abc/x.js",
                    "about:blank", "blob:https://site/1", "file:///etc/passwd"):
            self.assertFalse(guard(url), url)

    def test_private_ok_when_request_allows_private(self):
        pol = _public_policy(allow_literal=True)
        self.assertFalse(self._guard(pol)("http://10.0.0.5/"))

    def test_default_guard_honours_private_targets_context(self):
        # The shipped default must read the REQUEST's policy (contextvar), so a
        # dev/login fetch with private_targets_allowed() is not blocked.
        from src.browser_engine.cdp_adblock_driver import make_ssrf_guard
        from src.browser_engine.worker import private_targets_allowed
        guard = make_ssrf_guard()
        self.assertTrue(guard("http://10.0.0.5/"))
        with private_targets_allowed():
            self.assertFalse(guard("http://10.0.0.5/"))


class CdpSessionGuardWiringTests(unittest.TestCase):
    """The session must hand its guard to the bridge AND decide with it."""

    def test_session_bridge_receives_ssrf_guard(self):
        from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
        guard = lambda url: True
        sess = AdblockBrowserSession(_fake_bundle(), ssrf_guard=guard)
        self.assertIs(sess._bridge._ssrf_guard, guard)

    def test_observer_decision_runs_the_same_ssrf_check(self):
        # _notify_decision is what the live block counter reports from; if it
        # skips the guard the stats claim "allowed" for blocked hops.
        from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
        seen = []
        sess = AdblockBrowserSession(_fake_bundle(),
                                     ssrf_guard=lambda url: True,
                                     on_blocked=seen.append)
        params = {"requestId": "r1",
                  "request": {"url": "http://10.0.0.5/secret", "headers": {}},
                  "resourceType": "Document"}
        sess._notify_decision(params)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["action"], "block")

    def test_make_adblock_driver_passes_explicit_guard(self):
        from src.browser_engine.cdp_adblock_driver import make_adblock_driver
        captured = {}
        guard = lambda url: False

        class FakeSession:
            def __init__(self, bundle, browser_path=None, **kw):
                captured.update(kw)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def fetch(self, url, host=None, timeout=30.0):
                return {"html": ["<html></html>"], "text": [""], "title": ""}

        with mock.patch("src.browser_engine.cdp_adblock_driver.AdblockBrowserSession",
                        FakeSession), \
                mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard",
                           return_value=mock.MagicMock()):
            out = make_adblock_driver(_fake_bundle(), ssrf_guard=guard)(
                "lightpanda", "https://example.com/", "s")
        self.assertEqual(out, "<html></html>")
        self.assertIs(captured.get("ssrf_guard"), guard)

    def test_make_adblock_driver_defaults_to_policy_guard(self):
        from src.browser_engine.cdp_adblock_driver import make_adblock_driver
        captured = {}

        class FakeSession:
            def __init__(self, bundle, browser_path=None, **kw):
                captured.update(kw)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def fetch(self, url, host=None, timeout=30.0):
                return {"html": ["<html></html>"], "text": [""], "title": ""}

        with mock.patch("src.browser_engine.cdp_adblock_driver.AdblockBrowserSession",
                        FakeSession), \
                mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard",
                           return_value=mock.MagicMock()):
            make_adblock_driver(_fake_bundle())("lightpanda", "https://example.com/", "s")
        guard = captured.get("ssrf_guard")
        self.assertTrue(callable(guard))
        self.assertTrue(guard("http://127.0.0.1/"))  # a real policy guard


class RelayRequiredTests(unittest.TestCase):
    """_relay_required: strict requests must route engine traffic through the
    validating relay; private-allowed (dev) requests stay direct."""

    def test_strict_policy_requires_relay(self):
        from src.browser_engine.engine_drivers import _relay_required
        self.assertTrue(_relay_required(_public_policy()))
        self.assertTrue(_relay_required(None))  # live policy: strict by default

    def test_private_opt_in_stays_direct(self):
        from src.browser_engine.engine_drivers import _relay_required
        self.assertFalse(_relay_required(_public_policy(allow_literal=True)))


class LightpandaRelayWiringTests(unittest.TestCase):
    """Lightpanda has no CDP interception: strict requests must be pinned to the
    relay (--http-proxy), which validates every hop (incl. redirects) and dials
    the validated IP."""

    def _proxy_args(self, policy, enforce: str = "0"):
        import src.browser_engine.engine_drivers as ed
        guard = mock.MagicMock()
        guard.listen_host = "127.0.0.1"
        guard.port = 8899
        with mock.patch.dict(os.environ, {"ORACLE_EGRESS_ENFORCE": enforce,
                                          "ORACLE_EGRESS_NETNS": "0"}, clear=False), \
                mock.patch.object(ed, "_ensure_egress_guard", return_value=guard):
            return ed._lightpanda_proxy_args(policy)

    def test_strict_policy_forces_relay_even_without_enforcement(self):
        args = self._proxy_args(_public_policy())
        self.assertEqual(args, ["--http-proxy", "http://127.0.0.1:8899"])

    def test_private_opt_in_stays_direct_without_enforcement(self):
        import src.browser_engine.engine_drivers as ed
        with mock.patch.object(ed, "_ensure_egress_guard") as guard:
            with mock.patch.dict(os.environ, {"ORACLE_EGRESS_ENFORCE": "0"}, clear=False):
                args = ed._lightpanda_proxy_args(_public_policy(allow_literal=True))
        self.assertEqual(args, [])
        guard.assert_not_called()

    def test_enforcement_env_still_forces_relay(self):
        args = self._proxy_args(_public_policy(allow_literal=True), enforce="1")
        self.assertEqual(args, ["--http-proxy", "http://127.0.0.1:8899"])


class ChromiumPoolRelayWiringTests(unittest.TestCase):
    """Pooled chromium launches once per generation; relay mode is a launch flag,
    so a mode change must drop the generation and relaunch."""

    def test_chromium_launch_args_force_relay_under_strict_policy(self):
        import src.browser_engine.engine_drivers as ed
        guard = mock.MagicMock()
        guard.listen_host = "127.0.0.1"
        guard.port = 8899
        with mock.patch.dict(os.environ, {"ORACLE_EGRESS_ENFORCE": "0",
                                          "ORACLE_EGRESS_NETNS": "0"}, clear=False), \
                mock.patch.object(ed, "_ensure_egress_guard", return_value=guard):
            args = ed._chromium_launch_args(_public_policy())
        self.assertIn("--proxy-server=http://127.0.0.1:8899", args)
        # loopback literals would otherwise bypass the proxy (Chromium default):
        self.assertIn("--proxy-bypass-list=<-loopback>", args)
        self.assertTrue(any(a.startswith("--host-resolver-rules=") for a in args))

    def test_chromium_launch_args_direct_when_private_ok(self):
        import src.browser_engine.engine_drivers as ed
        with mock.patch.dict(os.environ, {"ORACLE_EGRESS_ENFORCE": "0"}, clear=False):
            self.assertEqual(ed._chromium_launch_args(_public_policy(allow_literal=True)), [])

    def _fake_playwright(self, launches: list):
        class FakePage:
            def goto(self, *a, **kw):
                pass

            def content(self):
                return "<html>ok</html>"

        class FakeBrowser:
            def is_connected(self):
                return True

            def new_page(self, **kw):
                return FakePage()

            def close(self):
                pass

            def kill(self):
                pass

        class FakePw:
            chromium = property(lambda self: self)

            def start(self):
                return self

            def stop(self):
                pass

            def launch(self, **kw):
                launches.append(kw)
                return FakeBrowser()

        api = types.ModuleType("playwright.sync_api")
        api.sync_playwright = lambda: FakePw()
        pkg = types.ModuleType("playwright")
        return mock.patch.dict(sys.modules, {"playwright": pkg,
                                             "playwright.sync_api": api})

    def test_mode_change_relaunches_the_generation(self):
        import src.browser_engine.engine_drivers as ed
        launches = []
        with self._fake_playwright(launches), \
                mock.patch.dict(os.environ, {"ORACLE_EGRESS_ENFORCE": "0",
                                             "ORACLE_EGRESS_NETNS": "0",
                                             "ORACLE_EGRESS_PROXY_HOST": "127.0.0.1",
                                             "ORACLE_EGRESS_PROXY_PORT": "8899"}, clear=False), \
                mock.patch.object(ed, "_ensure_egress_guard"):
            worker = ed._ChromiumWorker()
            # 1st fetch: direct (private-allowed). 2nd: strict -> relaunch.
            worker._fetch_once("https://a.test/", "ua",
                               need_relay=False)
            worker._fetch_once("https://b.test/", "ua",
                               need_relay=True)
        self.assertEqual(len(launches), 2)
        self.assertNotIn("--proxy-server=http://127.0.0.1:8899", launches[0].get("args", []))
        self.assertIn("--proxy-server=http://127.0.0.1:8899", launches[1].get("args", []))

    def test_same_mode_reuses_the_generation(self):
        import src.browser_engine.engine_drivers as ed
        launches = []
        with self._fake_playwright(launches), \
                mock.patch.dict(os.environ, {"ORACLE_EGRESS_ENFORCE": "0",
                                             "ORACLE_EGRESS_NETNS": "0",
                                             "ORACLE_EGRESS_PROXY_HOST": "127.0.0.1",
                                             "ORACLE_EGRESS_PROXY_PORT": "8899"}, clear=False), \
                mock.patch.object(ed, "_ensure_egress_guard"):
            worker = ed._ChromiumWorker()
            worker._fetch_once("https://a.test/", "ua", need_relay=True)
            worker._fetch_once("https://b.test/", "ua", need_relay=True)
        self.assertEqual(len(launches), 1)


if __name__ == "__main__":
    unittest.main()
