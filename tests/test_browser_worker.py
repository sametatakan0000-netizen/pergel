import unittest
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


if __name__ == "__main__":
    unittest.main()
