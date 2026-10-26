"""SPA content preservation: JS-injected DOM must survive extraction.

Failure mode (2026-10-26 corpus run): SPA pages (Amazon 21 words, YouTube 26,
GitLab 38, Swagger 2) return only the server-rendered shell because
1. Lightpanda does not execute JS (`fetch --dump html` = static HTML), and
2. Chromium grabs page.content() at `load`, before React/Vue commit.

Contract:
- `rendered_body` extraction path must see the JS-injected DOM (test drives a
  driver_fn that returns post-JS HTML, so this tests the extraction contract).
- The Chromium fetcher must wait for content stabilization, not just `load`.
- A shell page whose injected text is missing must NOT be accepted as success
  if the engine can escalate to a JS-capable engine (engine ladder).
"""
import unittest
from unittest import mock

from src.browser_engine import worker as w


CHROME = (
    "<nav>'<a href=/a>Home</a><a href=/b>Shop</a><a href=/c>Deals</a></nav>"
    "<footer>Copyright 2026. Terms Privacy Sitemap Contact Help.</footer>"
)
# Realistic SPA shell: framework marker (React root), plus chrome that makes the
# static-extracted markdown pass a naive length>=10 check.
SHELL_ONLY = (
    "<html><head><title>Shop</title></head>"
    '<body><div id="root" data-reactroot></div>' + CHROME
    + "<script>fetch('/api/data').then(r=>r.json()).then(d=>{"
    "document.getElementById('root').innerHTML='<h1>Product Title</h1>'"
    "+'<p>Product description here.</p>'</script></body></html>"
)
RENDERED = (
    "<html><head><title>Shop</title></head>"
    '<body><div id="root"><h1>Product Title</h1>'
    "<p>Product description here.</p></div>" + CHROME + "</body></html>"
)
RENDERED = (
    "<html><head><title>App</title></head>"
    '<body><div id="root"><h1>Product Title</h1>'
    "<p>Product description here.</p></div></body></html>"
)


class SpaExtractionTests(unittest.TestCase):
    def test_rendered_dom_text_survives_extraction(self):
        """Post-JS HTML (what a JS engine returns) must yield the injected text."""
        md = w.html_to_clean_markdown(RENDERED)
        self.assertIn("Product Title", md, md[:300])
        self.assertIn("Product description", md, md[:300])

    def test_shell_without_injected_text_is_not_content(self):
        """A shell page with no injected text must not masquerade as content."""
        md = w.html_to_clean_markdown(SHELL_ONLY)
        self.assertNotIn("Product Title", md)

    def test_worker_prefers_engine_returning_rendered_dom(self):
        """Given a driver that returns the rendered DOM for a JS engine and a
        shell for a static engine, execute_task must surface the rendered text."""
        def driver(engine, url, session):
            # static engines cannot run JS -> shell only
            if engine == "lightpanda":
                return SHELL_ONLY
            return RENDERED

        bw = w.BrowserWorker(driver_fn=driver)
        res = bw.execute_task("job-spa", "http://spa.test/page", js_complexity="high")
        self.assertIn("Product Title", res["markdown"], res.get("markdown", "")[:300])

    def test_thin_js_app_shell_must_escalate(self):
        """A JS-app shell (framework marker) whose static extraction is thin but
        passes a naive len>=10 check must still escalate to a JS-capable engine.

        This is the real-world failure: Amazon/YouTube/GitLab shells carry nav +
        footer chrome, so the extracted markdown clears a length threshold and
        the worker wrongly accepts the shell as a finished page.
        """
        # Trafilatura drops <nav>/<footer> entirely (0 chars); it keeps <p>/<li>.
        # Real SPA shells (Amazon/YouTube/GitLab) embed paragraphs and list items
        # (cookie banners, promo copy, category lists) that survive extraction and
        # clear a len>=10 check, while the actual product/video content is JS-only.
        # The shell's HTML payload is large (inline JS bundles) but the extractable
        # text is a tiny fraction of it -- the real-world signature (GitLab 433KB
        # -> 38 words; YouTube 42KB -> 26 words).
        chrome = (
            "<p>Browse thousands of products across every category you love and "
            "find the best deals today on our store.</p>"
            "<p>Sign in to your account to see personalized recommendations and "
            "track your orders easily.</p>"
            "<ul><li>Home and Kitchen</li><li>Electronics and Gadgets</li>"
            "<li>Deals of the Day</li><li>Customer Service</li></ul>"
        )
        js_bundle = "<script>/*" + ("x" * 25000) + "*/" + (
            "fetch('/api/data').then(r=>r.json()).then(d=>{"
            "document.getElementById('root').innerHTML='<h1>Real Product Name</h1>'"
            "+'<p>Real product description body.</p>'})"
        ) + "</script>"
        thin_shell = (
            "<html><head><title>Shop</title></head>"
            '<body><div id="root" data-reactroot></div>' + chrome +
            js_bundle + "</body></html>"
        )
        rendered_page = (
            "<html><head><title>Shop</title></head>"
            '<body><div id="root"><h1>Real Product Name</h1>'
            "<p>Real product description body.</p></div>" + chrome + "</body></html>"
        )

        calls = []

        def driver(engine, url, session):
            calls.append(engine)
            return thin_shell if engine == "lightpanda" else rendered_page

        bw = w.BrowserWorker(driver_fn=driver)
        res = bw.execute_task("job-thin", "http://spa.test/page", js_complexity="low")
        # chrome alone already clears len>=10, so the naive path would NOT escalate
        static_md = w.html_to_clean_markdown(thin_shell)
        self.assertGreaterEqual(len(static_md.strip()), 10,
                                "fixture must reproduce the real bug (static md >= 10)")
        # The JS engine's injected content is the proof of escalation; it exists
        # only after client render, never in the static shell.
        self.assertNotIn("Real product description body", static_md,
                         "shell fixture must NOT contain the JS-injected content")
        self.assertIn("Real product description body", res.get("markdown", ""),
                      f"did not escalate to JS engine; calls={calls} md={res.get('markdown','')[:200]}")

    def test_shell_only_engine_does_not_truncate_escalation(self):
        """If the static engine returns only a shell (tiny markdown), the worker
        must escalate to the next engine rather than accept the shell as done."""
        calls = []

        def driver(engine, url, session):
            calls.append(engine)
            return SHELL_ONLY if engine == "lightpanda" else RENDERED

        bw = w.BrowserWorker(driver_fn=driver)
        res = bw.execute_task("job-spa2", "http://spa.test/page", js_complexity="low")
        self.assertIn("Product Title", res.get("markdown", ""), res.get("markdown", "")[:300])
        self.assertGreater(len(calls), 1, "no escalation happened, shell accepted as done")


if __name__ == "__main__":
    unittest.main()
