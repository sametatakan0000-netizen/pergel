"""Access-block codes surfacing on the browse API.

Policy (approved): a block is never silently bypassed and never reported as a
vague failure. Each refusal carries a stable machine-readable code, the target
domain and a human message. Codes:
  robots_disallowed, blocked_by_site, captcha_required,
  paywall_or_login_required, rate_limited_by_site

This suite drives the REST layer: the driver raises FetchBlocked(code=...) and
the API must turn that into the exact structured error contract (no vague
{"error": "<text>"} shape, no silent 200 with empty markdown).
"""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request

os.environ.setdefault("ORACLE_EXPLORE_EPSILON", "0")

from src.api.server import BrowserFarmSaaSServer
from src.browser_engine.worker import FetchBlocked
from tests.test_e2e_saas_product import fixture_profiles

_saved_browse_api_key = None


def setUpModule():
    global _saved_browse_api_key
    _saved_browse_api_key = os.environ.pop("BROWSE_API_KEY", None)


def tearDownModule():
    if _saved_browse_api_key is not None:
        os.environ["BROWSE_API_KEY"] = _saved_browse_api_key


OK_HTML = "<html><body><p>plenty of visible text here for extraction</p></body></html>"


def _server(tmp, driver_fn):
    srv = BrowserFarmSaaSServer(
        host="127.0.0.1",
        port=0,
        db_dir=tmp,
        profiles=fixture_profiles(),
        driver_fn=driver_fn,
        nous_proxy_url="http://127.0.0.1:9/v1",
    )
    srv.start_background()
    return srv


def _browse(base_url, url):
    req = urllib.request.Request(
        f"{base_url}/v1/jobs/browse",
        data=json.dumps({"url": url}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class RobotsDisallowedTests(unittest.TestCase):
    def test_robots_disallowed_returns_structured_403(self):
        def driver(engine, url, session_name):
            raise FetchBlocked(f"robots.txt disallows {url}", code="robots_disallowed")

        with tempfile.TemporaryDirectory() as tmp:
            srv = _server(tmp, driver)
            try:
                status, body = _browse(f"http://127.0.0.1:{srv.port}", "http://example.com/page")
            finally:
                srv.shutdown()

        self.assertEqual(status, 403)
        self.assertIsInstance(body.get("error"), dict, body)
        err = body["error"]
        self.assertEqual(
            {"code": err.get("code"), "domain": err.get("domain")},
            {"code": "robots_disallowed", "domain": "example.com"},
        )
        self.assertTrue(err.get("message"), "human message required")
        self.assertTrue(err.get("request_id"), "request_id required")

    def test_allowed_request_still_returns_200(self):
        def driver(engine, url, session_name):
            return OK_HTML

        with tempfile.TemporaryDirectory() as tmp:
            srv = _server(tmp, driver)
            try:
                status, body = _browse(f"http://127.0.0.1:{srv.port}", "http://example.com/page")
            finally:
                srv.shutdown()

        self.assertEqual(status, 200)
        self.assertNotIn("error", body)
