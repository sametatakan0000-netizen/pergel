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
