import json
import unittest
import urllib.error
import urllib.request

from src.bench.fixture_server import MARKERS, fixture_server


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode()


class FixtureTests(unittest.TestCase):
    def test_static_has_marker_in_raw_html(self):
        with fixture_server() as base:
            self.assertIn(MARKERS["static"], get(base + "/static")[1])

    def test_spa_marker_is_absent_from_raw_html_and_needs_js(self):
        with fixture_server() as base:
            self.assertNotIn(MARKERS["spa"], get(base + "/spa")[1])
            self.assertEqual(json.loads(get(base + "/api/reviews")[1])["items"][0], "good")

    def test_heavy_node_count_is_parameterized_and_capped(self):
        with fixture_server() as base:
            self.assertEqual(get(base + "/heavy?n=10")[1].count("row "), 10)
            self.assertLessEqual(get(base + "/heavy?n=999999")[1].count("row "), 50000)

    def test_unknown_path_404(self):
        with fixture_server() as base:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                get(base + "/nope")
            self.assertEqual(ctx.exception.code, 404)
