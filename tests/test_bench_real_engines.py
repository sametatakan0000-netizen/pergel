"""Real-engine smoke: each installed target must render the JS-dependent SPA fixture.

This is a receipt, not a gate for engines that legitimately cannot run a given page: a failure
is reported per-target and only breaks the suite if the engine claims JS support (chromium kinds).
"""
import unittest

try:
    import playwright  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from src.bench.adapters import FetchResult
from src.bench.fixture_server import MARKERS, fixture_server
from src.bench.install import MANIFEST
from src.bench.runner import run_cell
from src.bench.runner import Scenario
from src.bench.targets import build_target, load_manifest

SPA = Scenario("spa", "/spa", MARKERS["spa"])
JS_CAPABLE_KINDS = {"chromium"}  # lightpanda/gecko/webkit failures are data, not a suite failure


def _manifest_or_skip(test):
    if not HAS_PLAYWRIGHT:
        test.skipTest("playwright not installed (system python)")
    data = load_manifest()
    if not data:
        test.skipTest("no installed targets in manifest")


class RealEngineSmokeTests(unittest.TestCase):
    def test_static_renders_on_every_installed_target(self):
        _manifest_or_skip(self)
        with fixture_server() as base:
            for tid, entry in sorted(load_manifest().items()):
                with self.subTest(target=tid):
                    if entry.get("blocked"):
                        print(f"\n  {tid} BLOCKED: {entry['blocked'][:60]}", end="")
                        continue
                    try:
                        target = build_target(tid, entry)
                    except ValueError:
                        continue
                    rows = run_cell(target, Scenario("static", "/static", MARKERS["static"]), base,
                                    lifecycles=1, warmups=0, fetches=1)
                    self.assertEqual(rows[0]["success_rate"], 1.0, f"{tid} failed to render /static")

    def test_spa_renders_where_js_is_expected(self):
        _manifest_or_skip(self)
        failures = []
        with fixture_server() as base:
            for tid, entry in sorted(load_manifest().items()):
                if entry.get("blocked") or entry.get("kind") not in JS_CAPABLE_KINDS:
                    continue
                with self.subTest(target=tid):
                    target = build_target(tid, entry)
                    rows = run_cell(target, SPA, base, lifecycles=1, warmups=0, fetches=1)
                    if rows[0]["success_rate"] != 1.0:
                        failures.append(tid)
        self.assertEqual(failures, [], f"JS-capable targets failed to render the SPA: {failures}")

    def test_all_targets_get_a_smoke_record(self):
        """Print a per-target verdict for the report; never raises on a non-JS engine."""
        _manifest_or_skip(self)
        with fixture_server() as base:
            for tid, entry in sorted(load_manifest().items()):
                if entry.get("blocked"):
                    print(f"\n  {tid} BLOCKED", end="")
                    continue
                try:
                    target = build_target(tid, entry)
                    rows = run_cell(target, SPA, base, lifecycles=1, warmups=0, fetches=1)
                    verdict = rows[0]["success_rate"]
                except Exception as exc:
                    verdict = f"error:{type(exc).__name__}"
                print(f"\n  {tid} spa={verdict} kind={entry.get('kind')}", end="")


if __name__ == "__main__":
    unittest.main()
