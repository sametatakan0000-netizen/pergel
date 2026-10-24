import unittest

from src.bench.adapters import FetchResult, chromium_argv, free_port, lightpanda_argv


class AdapterHelperTests(unittest.TestCase):
    def test_free_port_is_bindable_int(self):
        self.assertGreater(free_port(), 1024)

    def test_chromium_argv_has_identical_flag_set_for_every_vendor(self):
        a = chromium_argv("/opt/chrome/chrome", 9333, "/tmp/p1")
        b = chromium_argv("/opt/brave/brave", 9444, "/tmp/p2")
        strip = lambda argv: [x for x in argv[1:] if not x.startswith(("--remote-debugging-port", "--user-data-dir"))]
        self.assertEqual(strip(a), strip(b))
        self.assertIn("--remote-debugging-port=9333", a)
        self.assertIn("--no-sandbox", a)

    def test_lightpanda_argv(self):
        self.assertEqual(lightpanda_argv("/x/lightpanda", 9222),
                         ["/x/lightpanda", "serve", "--host", "127.0.0.1", "--port", "9222"])

    def test_fetch_result_defaults(self):
        r = FetchResult(ok=True, ms=1.5, html_len=10)
        self.assertEqual(r.error, "")
