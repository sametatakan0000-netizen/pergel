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


class ProcessGroupCleanupTests(unittest.TestCase):
    """Chromium-family browsers are multi-process: stop() must reap the WHOLE tree, not just the leader."""

    def test_stop_kills_grandchildren(self):
        import os, subprocess, sys, time
        from src.bench.adapters import kill_process_tree
        script = "import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\ntime.sleep(60)"
        p = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
        time.sleep(0.6)
        from src.bench.procmem import tree_pids
        pids = tree_pids(p.pid)
        self.assertGreaterEqual(len(pids), 2)
        kill_process_tree(p)
        time.sleep(0.3)
        alive = [x for x in pids if os.path.exists(f"/proc/{x}") and open(f"/proc/{x}/stat").read().split(")")[-1].split()[0] != "Z"]
        self.assertEqual(alive, [])

    def test_kill_process_tree_is_safe_on_already_dead_process(self):
        import subprocess, sys
        from src.bench.adapters import kill_process_tree
        p = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        p.wait()
        kill_process_tree(p)  # must not raise
