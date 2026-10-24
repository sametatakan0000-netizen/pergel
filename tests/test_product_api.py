import asyncio
import json
import tempfile
import unittest
import urllib.error
import urllib.request

from src.api.server import BrowserFarmSaaSServer
from src.browser_engine.worker import FetchBlocked

PAGE = ("<html><body><article><h1>Plans</h1><p>" + "The starter plan costs 49 dollars monthly. " * 6 +
        "</p><script>fetch('/api/v2/pricing.json')</script></article></body></html>")


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class _Base(unittest.TestCase):
    def start(self, driver=None, search=None, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = BrowserFarmSaaSServer(port=0, db_dir=tmp.name, profiles={}, driver_fn=driver or (lambda e, u, s: PAGE),
                                    search_fn=search, nous_proxy_url="http://127.0.0.1:9/v1", **kw)
        srv.start_background()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.port}"


class TestBrowseJob(_Base):
    def test_result_exposes_engine_trail_and_apis(self):
        base = self.start()
        st, job = call(base, "/v1/jobs/browse", {"url": "https://shop.example.com/p"})
        self.assertEqual(st, 200)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["attempted_engines"], ["lightpanda"])
        self.assertIn("https://shop.example.com/api/v2/pricing.json", job["discovered_apis"])

    def test_blocked_job_is_failed_and_flagged(self):
        def drv(e, u, s):
            raise FetchBlocked("robots")
        base = self.start(driver=drv)
        st, job = call(base, "/v1/jobs/browse", {"url": "https://x.example.com"})
        self.assertEqual(st, 200)
        self.assertEqual(job["status"], "failed")
        self.assertTrue(job["blocked"])

    def test_rejects_bad_scheme_and_missing_url(self):
        base = self.start()
        for body in ({}, {"url": "file:///etc/passwd"}, {"url": "ftp://a.example.com"}):
            self.assertEqual(call(base, "/v1/jobs/browse", body)[0], 400, body)

    def test_rejects_private_targets_by_default(self):
        base = self.start()
        for u in ("http://127.0.0.1:8645/v1/models", "http://localhost/x", "http://169.254.169.254/latest",
                  "http://10.0.0.5/"):
            self.assertEqual(call(base, "/v1/jobs/browse", {"url": u})[0], 400, u)

    def test_private_targets_allowed_when_opted_in(self):
        base = self.start(allow_private_targets=True)
        self.assertEqual(call(base, "/v1/jobs/browse", {"url": "http://127.0.0.1:1/x"})[0], 200)


class TestFanout(_Base):
    def test_uses_injected_search_and_cites_sources(self):
        async def search(sq):
            return [{"url": f"https://src.example.com/{abs(hash(sq)) % 1000}", "title": sq, "snippet": "s"}]
        base = self.start(search=search)
        st, res = call(base, "/v1/search/fanout", {"query": "lightpanda ve camoufox karşılaştırması"})
        self.assertEqual(st, 200)
        self.assertTrue(res["sources"])
        self.assertTrue(all("indexed.local" not in s["url"] for s in res["sources"]))
        self.assertIn("[1]", res["grounded_context"])

    def test_search_backend_down_returns_502_not_fake_results(self):
        async def search(sq):
            raise OSError("searxng down")
        base = self.start(search=search)
        st, res = call(base, "/v1/search/fanout", {"query": "a long enough query here"})
        self.assertEqual(st, 502)
        self.assertNotIn("sources", res)

    def test_empty_query_400(self):
        self.assertEqual(call(self.start(), "/v1/search/fanout", {"query": " "})[0], 400)


class TestMoaPreview(_Base):
    def test_preview_returns_amiral_and_never_calls_upstream(self):
        from dataclasses import replace
        from src.router.model_registry import build_profiles
        catalog = {"version": 1, "providers": {"nous": {"models": [
            {"id": "m/cheap-a"}, {"id": "m/cheap-b"}, {"id": "m/top"}]}}}
        dev = {"openrouter": {"models": {
            "m/cheap-a": {"tool_call": True, "reasoning": False, "reasoning_options": [],
                          "modalities": {"input": ["text"]}, "limit": {"context": 200000},
                          "cost": {"input": 0.1, "output": 0.5}},
            "m/cheap-b": {"tool_call": True, "reasoning": False, "reasoning_options": [],
                          "modalities": {"input": ["text"]}, "limit": {"context": 200000},
                          "cost": {"input": 0.08, "output": 0.4}},
            "m/top": {"tool_call": True, "reasoning": False, "reasoning_options": [],
                      "modalities": {"input": ["text"]}, "limit": {"context": 200000},
                      "cost": {"input": 2.0, "output": 10.0}},
        }}}
        profiles = build_profiles(catalog, dev, fetched_at="t")
        for mid, q in (("m/cheap-a", 44.0), ("m/cheap-b", 43.5), ("m/top", 57.0)):
            profiles[mid] = replace(profiles[mid], intelligence_index=q)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = BrowserFarmSaaSServer(port=0, db_dir=tmp.name, profiles=profiles,
                                    driver_fn=lambda e, u, s: PAGE,
                                    nous_proxy_url="http://127.0.0.1:9/v1")  # dead upstream
        srv.start_background()
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.port}"
        body = {"model": "oracle/auto", "force": True,
                "messages": [{"role": "user", "content": "merhaba"}]}
        st, decision = call(base, "/v1/router/moa", body)
        self.assertEqual(st, 200)              # dead upstream proves nothing was forwarded
        self.assertEqual(decision["amiral"], "m/cheap-b")
        self.assertIn("cap_usd", decision["moa"])
        st, _ = call(base, "/v1/router/moa", {"messages": []})
        self.assertEqual(st, 400)


class JobsApiAuthTests(_Base):
    """/v1/jobs/* requires a bearer key when BROWSE_API_KEY is set; router paths stay open."""

    def setUp(self):
        import os
        os.environ["BROWSE_API_KEY"] = "test-key-123"
        self.addCleanup(os.environ.pop, "BROWSE_API_KEY", None)

    def test_jobs_post_without_key_is_rejected(self):
        base = self.start()
        status, body = call(base, "/v1/jobs/browse", {"url": "https://example.com/"})
        self.assertEqual(status, 401)

    def test_jobs_get_with_wrong_key_is_rejected(self):
        base = self.start()
        req = urllib.request.Request(base + "/v1/jobs/nope", headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 401)

    def test_jobs_with_correct_key_passes_auth(self):
        base = self.start()
        req = urllib.request.Request(base + "/v1/jobs/browse", method="POST",
                                     data=json.dumps({"url": "https://example.com/"}).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer test-key-123"})
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)

    def test_router_paths_stay_open_without_key(self):
        base = self.start()
        status, _ = call(base, "/v1/router/complete", {"prompt": "hi"})
        self.assertNotEqual(status, 401)


class RateLimitTests(_Base):
    """ORACLE_JOBS_RPM throttles /v1/jobs/* and /v1/search/fanout per client; router paths stay unthrottled."""

    def setUp(self):
        import os
        import src.api.server as srv
        os.environ["ORACLE_JOBS_RPM"] = "2"
        srv._RATE_BUCKETS.clear()
        self.addCleanup(os.environ.pop, "ORACLE_JOBS_RPM", None)
        self.addCleanup(srv._RATE_BUCKETS.clear)

    def test_third_rapid_jobs_call_gets_429_with_retry_after(self):
        base = self.start()
        s1, _ = call(base, "/v1/jobs/unknown-id")
        s2, _ = call(base, "/v1/jobs/unknown-id")
        self.assertEqual((s1, s2), (404, 404))
        req = urllib.request.Request(base + "/v1/jobs/unknown-id")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 429)
        self.assertGreaterEqual(int(ctx.exception.headers.get("Retry-After", "0")), 1)

    def test_router_models_path_is_not_throttled(self):
        base = self.start()
        for _ in range(6):
            status, _ = call(base, "/v1/models")
            self.assertEqual(status, 200)

    def test_zero_rpm_disables_limiting(self):
        import os
        import src.api.server as srv
        os.environ["ORACLE_JOBS_RPM"] = "0"
        srv._RATE_BUCKETS.clear()
        base = self.start()
        for _ in range(5):
            status, _ = call(base, "/v1/jobs/unknown-id")
            self.assertEqual(status, 404)


class FanoutDecomposeWiringTests(_Base):
    def test_decompose_fn_is_none_without_opt_in(self):
        import os
        os.environ.pop("ORACLE_FANOUT_LLM", None)
        srv = self._srv()
        self.assertIsNone(srv._fanout_decompose_fn())

    def test_decompose_fn_is_none_when_no_served_models(self):
        import os
        os.environ["ORACLE_FANOUT_LLM"] = "1"
        self.addCleanup(os.environ.pop, "ORACLE_FANOUT_LLM", None)
        srv = self._srv()
        fn = srv._fanout_decompose_fn()
        self.assertIsNone(fn("cok uzun bir arama sorgusu burada yaziyor"))  # no served model yet

    def _srv(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return BrowserFarmSaaSServer(port=0, db_dir=tmp.name, profiles={}, driver_fn=lambda e, u, s: PAGE)
