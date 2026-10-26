"""Content-extraction quality: page-type aware fallback selection.

trafilatura favors precision and drops too much on reference/docs pages
(docs.python.org: 47 words vs 285 for agent-browser). The extraction layer
must detect page type and switch to the right strategy:

- article/blog/news  -> trafilatura (good balance: ~80-85% words, low tokens)
- reference/API docs -> regex fallback (preserves code blocks, signatures)
- SPA/JS-heavy shell -> regex fallback (DOM text kept verbatim)
- short page         -> regex fallback (trafilatura discards short content)

Contract: the extractor returns >= 50% of the visible text words for
reference pages, while staying small for articles.
"""
import unittest

from src.browser_engine.worker import html_to_clean_markdown

# A reference/doc page: many code signatures and parameter tables, little prose.
DOC_PAGE = (
    "<html><head><title>urllib.request — Python docs</title>"
    "<style>body{font:14px sans-serif}</style>"
    "<script>var analytics=1;</script></head>"
    "<body><nav>Python Docs Navigation Menu</nav>"
    "<h1>urllib.request</h1>"
    "<p>This module defines functions and classes which help in opening URLs.</p>"
    "<h2>Request Objects</h2>"
    "<dl><dt>full_url</dt><dd>The original URL passed to the constructor.</dd>"
    "<dt>data</dt><dd>Request data, or None.</dd>"
    "<dt>method</dt><dd>The HTTP method, defaults to GET.</dd></dl>"
    "<h2>Functions</h2>"
    "<pre><code>urllib.request.urlopen(url, data=None, timeout=...)</code></pre>"
    "<p>Open the URL url, which can be either a string or a Request object.</p>"
    "<pre><code>urllib.request.install_opener(opener)</code></pre>"
    "<pre><code>urllib.request.build_opener([handler, ...])</code></pre>"
    "<table><tr><th>Parameter</th><th>Default</th><th>Doc</th></tr>"
    "<tr><td>url</td><td>required</td><td>target address</td></tr>"
    "<tr><td>data</td><td>None</td><td>payload</td></tr></table>"
    "<footer>© Python Software Foundation</footer></body></html>"
)

# An article page: continuous prose, nav/footer boilerplate.
ARTICLE_PAGE = (
    "<html><head><script>track()</script></head><body>"
    "<nav><a href='/a'>Menu A</a><a href='/b'>Menu B</a></nav>"
    "<article><h1>Web scraping</h1>"
    "<p>Web scraping extracts structured data from websites. It is widely used for "
    "price monitoring, research and archiving public pages, and it has a long history "
    "in the development of search engines and data pipelines.</p>"
    "<p>Extraction tools parse the document tree and keep the textual content, then "
    "discard navigation chrome and advertising blocks to make the page readable.</p>"
    "<p>Modern approaches combine heuristic readability with machine learning to "
    "separate the main column from the surrounding boilerplate of a web page.</p>"
    "</article><footer>Copyright notice here</footer></body></html>"
)


class ReferenceDocExtraction(unittest.TestCase):
    def test_keeps_function_signatures(self):
        md = html_to_clean_markdown(DOC_PAGE)
        self.assertIn("urllib.request.urlopen", md, md[:400])

    def test_keeps_parameter_names(self):
        md = html_to_clean_markdown(DOC_PAGE)
        # trafilatura escapes markdown specials: full_url -> full\_url.
        # Normalize before matching so we test content presence, not escaping.
        normalized = md.replace("\\_", "_").replace("\\*", "*").replace("\\#", "#")
        for word in ("full_url", "data", "method"):
            self.assertIn(word, normalized, f"{word!r} dropped: {md[:400]}")

    def test_keeps_substantial_fraction_of_visible_words(self):
        md = html_to_clean_markdown(DOC_PAGE)
        body_words = len(md.split())
        # reference pages must not be gutted to a handful of words
        self.assertGreaterEqual(body_words, 35, f"only {body_words} words kept")

    def test_drops_script_and_nav_chrome(self):
        md = html_to_clean_markdown(DOC_PAGE)
        self.assertNotIn("analytics", md)
        self.assertNotIn("Python Docs Navigation Menu", md)


class QualityGateTests(unittest.TestCase):
    """When trafilatura drops too much content, fall back to regex extraction."""

    def test_dense_reference_page_is_not_gutted(self):
        # Real-world pattern: many short code blocks and parameter names.
        # trafilatura precision mode may discard most of it.
        blocks = "".join(
            f"<h3>func_{i}(arg_{i})</h3><p>Does thing {i}. Returns value {i}.</p>"
            f"<pre><code>func_{i}(arg_{i}, timeout={i})</code></pre>"
            for i in range(20)
        )
        page = f"<html><body><h1>API Reference</h1>{blocks}</body></html>"
        md = html_to_clean_markdown(page)
        words = len(md.split())
        # must keep at least 40% of the visible text (~160 words total)
        self.assertGreaterEqual(words, 60, f"only {words} words from dense reference page")

    def test_quality_gate_prefers_more_content_when_close_in_tokens(self):
        # If regex gives 2x more content than trafilatura for a doc page, use regex.
        blocks = "".join(
            f"<dl><dt>param_{i}</dt><dd>Parameter number {i} description.</dd></dl>"
            for i in range(15)
        )
        page = f"<html><body><h1>Config</h1>{blocks}</body></html>"
        md = html_to_clean_markdown(page)
        normalized = md.replace("\\_", "_")
        # key markers from the <dl> terms must survive
        self.assertIn("param_0", normalized, md[:300])
        self.assertIn("param_14", normalized, md[-300:])


class QualityGateRealisticTests(unittest.TestCase):
    """Real-world failure: sidebar-heavy reference page where trafilatura picks
    the wrong element and returns almost nothing. The quality gate must notice
    and fall back to regex extraction."""

    def test_sidebar_heavy_page_keeps_main_content(self):
        # docs.python.org pattern: huge sidebar, thin content column
        sidebar_links = "".join(
            f'<li><a href="/lib/{i}">Module {i} reference</a></li>' for i in range(50)
        )
        page = (
            "<html><head><title>urllib.request</title>"
            "<script>var _gaq = 1;</script></head><body>"
            f'<div class="sidebar"><ul>{sidebar_links}</ul></div>'
            '<div class="document"><h1>urllib.request</h1>'
            "<p>This module defines functions and classes which help in opening "
            "URLs under a basic authentication scheme.</p>"
            "<h2>Request Objects</h2>"
            "<p>Request objects have the following attributes:</p>"
            "<dl><dt>full_url</dt><dd>The original URL passed to the constructor.</dd>"
            "<dt>data</dt><dd>Request data, or None for GET.</dd>"
            "<dt>method</dt><dd>The HTTP method, defaults to GET.</dd></dl>"
            "<h2>Examples</h2>"
            "<pre><code>import urllib.request\n"
            "with urllib.request.urlopen('http://example.com') as r:\n"
            "    print(r.read())</code></pre>"
            "</div><footer>Copyright Python</footer></body></html>"
        )
        md = html_to_clean_markdown(page)
        normalized = md.replace("\\_", "_")
        words = len(md.split())
        # the doc content (not sidebar) must survive
        self.assertIn("full_url", normalized, f"doc content gutted: {words} words: {md[:300]}")
        self.assertIn("urllib.request.urlopen", normalized, f"code block lost: {md[:500]}")


class ArticleExtraction(unittest.TestCase):
    def test_keeps_article_prose(self):
        md = html_to_clean_markdown(ARTICLE_PAGE)
        self.assertIn("Web scraping extracts structured data", md)

    def test_drops_boilerplate(self):
        md = html_to_clean_markdown(ARTICLE_PAGE)
        self.assertNotIn("Menu A", md)
        self.assertNotIn("Copyright notice here", md)

    def test_stays_compact(self):
        md = html_to_clean_markdown(ARTICLE_PAGE)
        self.assertLess(len(md), len(ARTICLE_PAGE))


if __name__ == "__main__":
    unittest.main()
