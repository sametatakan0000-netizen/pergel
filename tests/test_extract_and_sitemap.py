"""Structured extraction (/v1/extract logic) + sitemap URL discovery (/v1/map logic).

Both are pure functions over strings — no network. These back the product's
deterministic data-access endpoints: named-field extraction from a page, and
listing a site's URLs from its sitemap.
"""
import unittest

from src.api.extract import extract_fields
from src.browser_engine.platform_adapters import sitemap_urls

HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Pergel Pro","price":"49",
 "priceCurrency":"USD","description":"AI-native browsing"}
</script>
</head><body>
  <h1 data-hook="title">Pergel Pro</h1>
  <span id="price">$49</span>
  <div class="stock-status">In stock</div>
  <p class="about">The starter plan costs 49 dollars monthly.</p>
</body></html>
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/pricing</loc></url>
  <url><loc>https://example.com/docs</loc></url>
</urlset>
"""

GRAPH_JSONLD = """
<script type="application/ld+json">
{"@graph":[{"@type":"Organization","name":"Pergel"},{"@type":"WebSite","name":"Pergel Site"}]}
</script>
"""


class TestExtractFields(unittest.TestCase):
    def test_jsonld_strategy(self):
        out = extract_fields(HTML, [
            {"name": "product_name", "jsonld": "name"},
            {"name": "price", "jsonld": "price"},
            {"name": "currency", "jsonld": "priceCurrency"},
        ])
        self.assertEqual(out["product_name"], "Pergel Pro")
        self.assertEqual(out["price"], "49")
        self.assertEqual(out["currency"], "USD")

    def test_css_strategy(self):
        out = extract_fields(HTML, [
            {"name": "title", "css": "title"},
            {"name": "stock", "css": "stock-status"},
            {"name": "price_id", "css": "price"},
        ])
        self.assertEqual(out["title"], "Pergel Pro")
        self.assertEqual(out["stock"], "In stock")
        self.assertEqual(out["price_id"], "$49")

    def test_regex_strategy(self):
        out = extract_fields(HTML, [
            {"name": "monthly_cost", "regex": r"costs (\d+) dollars"},
        ])
        self.assertEqual(out["monthly_cost"], "49")

    def test_strategy_fallback_order(self):
        # jsonld wins when present; regex only used when jsonld misses.
        out = extract_fields(HTML, [
            {"name": "name", "jsonld": "name", "regex": r"data-hook=\"title\">([^<]+)<"},
            {"name": "missing", "jsonld": "nope", "css": "nope", "regex": r"zzz (\\w+)"},
        ])
        self.assertEqual(out["name"], "Pergel Pro")
        self.assertIsNone(out["missing"])

    def test_graph_jsonld_and_list_blocks(self):
        out = extract_fields(GRAPH_JSONLD, [{"name": "org", "jsonld": "name"}])
        self.assertEqual(out["org"], "Pergel")  # first matching key in @graph

    def test_no_spec_returns_empty(self):
        self.assertEqual(extract_fields(HTML, []), {})
        self.assertEqual(extract_fields(HTML, [{"noname": "x"}]), {})


class TestSitemapUrls(unittest.TestCase):
    def test_extracts_all_locs(self):
        self.assertEqual(
            sitemap_urls(SITEMAP),
            ["https://example.com/", "https://example.com/pricing", "https://example.com/docs"])

    def test_ignores_non_sitemap_xml(self):
        self.assertEqual(sitemap_urls("<html><body>hi</body></html>"), [])
        self.assertEqual(sitemap_urls("not xml at all"), [])

    def test_caps_and_trims(self):
        big = "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(
            f"<url><loc>https://e.com/{i}</loc></url>" for i in range(5)) + "</urlset>"
        self.assertEqual(len(sitemap_urls(big, limit=3)), 3)


if __name__ == "__main__":
    unittest.main()
