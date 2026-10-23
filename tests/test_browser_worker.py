import unittest
from src.browser_engine import worker as worker_mod
from src.browser_engine.worker import (
    BrowserWorker,
    discover_har_api_endpoints,
    html_to_clean_markdown,
)


class TestBrowserWorker(unittest.TestCase):
    def test_html_to_clean_markdown_and_har_api_discovery(self):
        raw_html = """
        <html><head><title>Test Page</title><script>fetch('/api/v2/pricing.json')</script></head>
        <body>
          <h1>Main Title</h1>
          <p>Read the <a href="https://example.com/docs">documentation</a>.</p>
        </body></html>
        """
        md = html_to_clean_markdown(raw_html)
        self.assertIn("# Main Title", md)
        self.assertIn("[documentation](https://example.com/docs)", md)

        endpoints = discover_har_api_endpoints(raw_html, base_url="https://example.com")
        self.assertIn("https://example.com/api/v2/pricing.json", endpoints)

    def test_worker_escalates_engine_when_lightpanda_returns_empty(self):
        called_engines = []

        def fake_driver(engine: str, url: str, session_name: str) -> str:
            called_engines.append(engine)
            if engine == "lightpanda":
                return ""
            return "<html><body><h1>Rendered Product Data</h1><p>Price: $49</p></body></html>"

        worker = BrowserWorker(driver_fn=fake_driver)
        result = worker.execute_task(
            job_id="job_99",
            url="https://spa.example.com",
            needs_vision=False,
            js_complexity="low",
        )
        self.assertTrue(result["oracle_passed"])
        self.assertEqual(result["final_engine"], "chromium-browser-use")
        self.assertEqual(called_engines, ["lightpanda", "chromium-browser-use"])
        self.assertIn("# Rendered Product Data", result["markdown"])

        # Second call to the same domain must adaptively skip lightpanda via self-evolution
        called_engines.clear()
        result2 = worker.execute_task(
            job_id="job_100",
            url="https://spa.example.com/checkout",
            needs_vision=False,
            js_complexity="low",
        )
        self.assertTrue(result2["oracle_passed"])
        self.assertEqual(called_engines, ["chromium-browser-use"])
        self.assertGreaterEqual(len(worker.orchestrator.evolution_ledger), 1)
        self.assertEqual(worker.orchestrator.evolution_ledger[0]["mode"], "FIX")


if __name__ == "__main__":
    unittest.main()


ARTICLE_HTML = """<html><head><title>Pricing</title></head><body>
<nav><ul><li><a href="/">Home</a></li><li><a href="/login">LOGIN-NAV-JUNK</a></li></ul></nav>
<article><h1>Pricing Guide</h1>
<p>The starter plan costs 49 dollars per month and includes ten thousand page fetches,
cited search results and automatic engine escalation for hard websites.</p>
<p>The team plan costs 199 dollars per month and adds priority queues, webhook delivery
with signed payloads, and discovered API endpoint exports for every crawled domain.</p>
<pre><code>curl -X POST /v1/jobs -d '{"url": "https://example.com"}'</code></pre>
<table><tr><th>Plan</th><th>Price</th></tr><tr><td>Starter</td><td>49</td></tr></table>
</article>
<footer>COOKIE-FOOTER-JUNK All rights reserved</footer></body></html>"""


class TestMainContentExtraction(unittest.TestCase):
    @unittest.skipIf(worker_mod.trafilatura is None, "trafilatura not installed (use .venv)")
    def test_boilerplate_removed_and_content_kept(self):
        md = html_to_clean_markdown(ARTICLE_HTML)
        self.assertIn("Pricing Guide", md)
        self.assertIn("199 dollars", md)
        self.assertIn("curl -X POST /v1/jobs", md)
        self.assertNotIn("LOGIN-NAV-JUNK", md)
        self.assertNotIn("COOKIE-FOOTER-JUNK", md)

    def test_short_fragment_falls_back_to_regex(self):
        self.assertIn("# Hi", html_to_clean_markdown("<h1>Hi</h1><p>x</p>"))


class TestPolicyBlockDoesNotEscalate(unittest.TestCase):
    def test_fetch_blocked_stops_ladder(self):
        from src.browser_engine.worker import FetchBlocked
        calls = []

        def drv(engine, url, session):
            calls.append(engine)
            raise FetchBlocked("robots")

        r = BrowserWorker(driver_fn=drv).execute_task("j1", "https://blocked.example.com")
        self.assertFalse(r["oracle_passed"])
        self.assertTrue(r["blocked"])
        self.assertEqual(calls, ["lightpanda"])
