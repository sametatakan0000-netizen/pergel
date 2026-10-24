import json
import os
import tempfile
import unittest
from unittest import mock

from src.bench import run as bench_run
from src.bench.adapters import FetchResult


class _Fake:
    def __init__(self):
        self.id = "fake"

    def start(self): pass
    def stop(self): pass
    def root_pids(self): return []

    def fetch(self, url, marker, timeout_s=30.0):
        return FetchResult(True, 5.0, 100)


class RunCliTests(unittest.TestCase):
    def setUp(self):
        bench_run.TARGET_REGISTRY["fake"] = lambda: _Fake()
        self.addCleanup(bench_run.TARGET_REGISTRY.pop, "fake", None)

    def test_writes_raw_env_and_report(self):
        with tempfile.TemporaryDirectory() as out:
            code = bench_run.main(["--targets", "fake", "--scenarios", "static", "--baseline", "fake",
                                   "--lifecycles", "2", "--warmups", "0", "--fetches", "2", "--out", out,
                                   "--force"])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(out, "raw.jsonl")))
            env = json.load(open(os.path.join(out, "env.json")))
            self.assertIn("forced", env)
            self.assertIn("# Benchmark report", open(os.path.join(out, "REPORT.md")).read())
            with open(os.path.join(out, "raw.jsonl")) as fh:
                self.assertEqual(len(fh.readlines()), 2)

    def test_refuses_when_machine_is_busy(self):
        with tempfile.TemporaryDirectory() as out, mock.patch("os.getloadavg", return_value=(5.0, 1.0, 1.0)):
            code = bench_run.main(["--targets", "fake", "--scenarios", "static", "--baseline", "fake",
                                   "--out", out])
            self.assertEqual(code, 2)
            self.assertFalse(os.path.exists(os.path.join(out, "REPORT.md")))

    def test_unknown_target_is_an_error_not_a_skip(self):
        with tempfile.TemporaryDirectory() as out:
            code = bench_run.main(["--targets", "nope", "--scenarios", "static", "--baseline", "nope",
                                   "--out", out, "--force"])
            self.assertEqual(code, 3)

    def test_forced_flag_true_only_when_guard_was_overridden(self):
        with tempfile.TemporaryDirectory() as out, mock.patch("os.getloadavg", return_value=(5.0, 1.0, 1.0)):
            bench_run.main(["--targets", "fake", "--scenarios", "static", "--baseline", "fake", "--lifecycles", "2",
                            "--warmups", "0", "--fetches", "1", "--out", out, "--force"])
            self.assertTrue(json.load(open(os.path.join(out, "env.json")))["forced"])
        with tempfile.TemporaryDirectory() as out, mock.patch("os.getloadavg", return_value=(0.1, 0.1, 0.1)):
            bench_run.main(["--targets", "fake", "--scenarios", "static", "--baseline", "fake", "--lifecycles", "2",
                            "--warmups", "0", "--fetches", "1", "--out", out, "--force"])
            self.assertFalse(json.load(open(os.path.join(out, "env.json")))["forced"])
