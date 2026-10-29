"""Engine launch path MUST wire egress enforcement when enabled (not a shelf).

Sub-process engine drivers (lightpanda, chromium) fetch outside the plain-HTTP
pinned path and re-resolve DNS themselves — so `engine_driver` must SSRF
pre-flight the target, and under enforcement route the engine's own requests
through the validating EgressRelay.
"""
import os
import unittest
from unittest import mock
from urllib.error import URLError
from src.browser_engine.egress_proxy import EgressPolicy


class LaunchArgsTests(unittest.TestCase):
    def test_chromium_launch_receives_proxy_args_when_enforcement_on(self):
        with mock.patch.dict("os.environ", {"ORACLE_EGRESS_ENFORCE": "1",
                                           "ORACLE_EGRESS_PROXY_HOST": "10.255.255.1",
                                           "ORACLE_EGRESS_PROXY_PORT": "8899"}):
            from src.browser_engine.engine_drivers import _chromium_launch_args
            # Argument generation only: do not bind a real proxy in unit tests.
            with mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard"):
                args = _chromium_launch_args()
        self.assertIn("--proxy-server=http://10.255.255.1:8899", args)
        self.assertTrue(any(a.startswith("--host-resolver-rules=") for a in args))

    def test_chromium_launch_args_empty_when_enforcement_off(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ORACLE_EGRESS_ENFORCE", None)
            from src.browser_engine.engine_drivers import _chromium_launch_args
            args = _chromium_launch_args()
        self.assertEqual(args, [])

    def test_enforcement_defaults_to_off(self):
        os.environ.pop("ORACLE_EGRESS_ENFORCE", None)
        from src.browser_engine.engine_drivers import _egress_enforce
        self.assertFalse(_egress_enforce())


def _public_policy():
    """Hermetic resolver stub: every host resolves to a public address."""
    from src.browser_engine.egress_proxy import EgressPolicy
    return EgressPolicy(resolver=lambda host: ["93.184.216.34"])


class LightpandaLaunchArgsTests(unittest.TestCase):
    """Lightpanda is a subprocess without CDP interception: under enforcement
    its traffic MUST traverse the validating EgressRelay via --http-proxy."""

    def _recorded_argv(self, enforce: bool, allow_literal: bool = False) -> list:
        import src.browser_engine.engine_drivers as ed
        d = os.path.join(os.path.dirname(__file__), "_stubs")
        os.makedirs(d, exist_ok=True)
        argv_path = os.path.join(d, "lp-argv.txt")
        stub = os.path.join(d, "lp-recorder")
        with open(stub, "w") as fh:
            fh.write("#!/bin/sh\nprintf '%s\\n' \"$@\" > " + argv_path + "\n"
                     "echo '<html><body>STUB-HTML</body></html>'\n")
        os.chmod(stub, 0o755)
        env = {"LIGHTPANDA_BIN": stub, "ORACLE_EGRESS_ENFORCE": "1" if enforce else "0"}
        policy = EgressPolicy(resolver=lambda host: ["93.184.216.34"], allow_literal=allow_literal)
        with mock.patch.dict(os.environ, env), \
                mock.patch("src.browser_engine.engine_drivers._ensure_egress_guard") as guard:
            out = ed.engine_driver("lightpanda", "https://example.com/", "s",
                                   user_directed=True, policy=policy)
        self.assertIn("STUB-HTML", out)
        self.assertEqual(guard.called, enforce or not allow_literal)
        with open(argv_path) as fh:
            return fh.read().splitlines()

    def test_lightpanda_argv_includes_http_proxy_when_enforcement_on(self):
        argv = self._recorded_argv(enforce=True, allow_literal=True)
        self.assertIn("--http-proxy", argv)
        self.assertIn("http://10.255.255.1:8899", argv)

    def test_lightpanda_argv_plain_when_enforcement_off(self):
        # Direct mode only when the request opts into private targets; a strict
        # request is relay-pinned even with enforcement off (SSRF redirect safety).
        argv = self._recorded_argv(enforce=False, allow_literal=True)
        self.assertNotIn("--http-proxy", argv)


class EnginePreflightTests(unittest.TestCase):
    """Same SSRF rules as the plain-HTTP fallback (_check_hop): private
    literal or private-resolving host -> FetchBlocked, unresolvable -> URLError.
    All rejected BEFORE any engine subprocess or pool fetch is invoked."""

    @staticmethod
    def _policy(resolved=("93.184.216.34",)):
        from src.browser_engine.egress_proxy import EgressPolicy
        return EgressPolicy(resolver=lambda host: list(resolved))

    def test_lightpanda_rejects_private_literal_before_subprocess(self):
        import src.browser_engine.engine_drivers as ed
        from src.browser_engine.worker import FetchBlocked
        with mock.patch("src.browser_engine.engine_drivers.subprocess.run") as run:
            with self.assertRaises(FetchBlocked) as ctx:
                ed.engine_driver("lightpanda", "http://169.254.169.254/latest/meta-data/", "s",
                                 user_directed=True, policy=self._policy())
        self.assertEqual(ctx.exception.code, "target_private_address")
        run.assert_not_called()

    def test_chromium_rejects_private_literal_before_pool_fetch(self):
        import src.browser_engine.engine_drivers as ed
        from src.browser_engine.worker import FetchBlocked
        with mock.patch.object(ed.chromium_pool, "fetch") as fetch:
            with self.assertRaises(FetchBlocked) as ctx:
                ed.engine_driver("chromium-browser-use", "http://10.0.0.1/", "s",
                                 user_directed=True, policy=self._policy())
        self.assertEqual(ctx.exception.code, "target_private_address")
        fetch.assert_not_called()

    def test_hostname_resolving_to_private_is_rejected(self):
        import src.browser_engine.engine_drivers as ed
        from src.browser_engine.worker import FetchBlocked
        with mock.patch("src.browser_engine.engine_drivers.subprocess.run") as run:
            with self.assertRaises(FetchBlocked) as ctx:
                ed.engine_driver("lightpanda", "http://intranet.test/", "s",
                                 user_directed=True, policy=self._policy(("10.0.0.5",)))
        self.assertEqual(ctx.exception.code, "target_private_address")
        run.assert_not_called()

    def test_unresolvable_host_raises_urlerror_before_subprocess(self):
        import src.browser_engine.engine_drivers as ed
        with mock.patch("src.browser_engine.engine_drivers.subprocess.run") as run:
            with self.assertRaises(URLError):
                ed.engine_driver("lightpanda", "http://no-such-host.test/", "s",
                                 user_directed=True, policy=self._policy(()))
        run.assert_not_called()

    def test_plain_http_fallback_keeps_own_validation_single_resolve(self):
        # camofox/plain-HTTP fallback validates its own hops (and reuses the
        # resolve) — the pre-flight must NOT double-resolve that path.
        import src.browser_engine.engine_drivers as ed
        with mock.patch.object(ed, "_default_url_driver", return_value="") as drv:
            out = ed.engine_driver("camofox", "http://intranet.test/", "s",
                                   user_directed=True, policy=self._policy(("10.0.0.5",)))
        self.assertEqual(out, "")
        drv.assert_called_once()


if __name__ == "__main__":
    unittest.main()
