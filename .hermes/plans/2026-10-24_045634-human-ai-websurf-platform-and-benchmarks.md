# Plan: Human + AI web-surf platform, every-browser benchmark lab, micro-optimization

## Özet (TR)
Üç parça: (1) **Benchmark laboratuvarı** — tüm tarayıcıları/motorları indir, aynı koşullarda ölç, yalnızca istatistiksel olarak savunulabilen sayıları pazarlamada kullan. (2) **Mikro optimizasyon** — yalnızca harness'in kanıtladığı darboğazları düzelt. (3) **İnsan yüzeyi** — Claude/ChatGPT'nin tarayıcıya eklenmesinin tersi: bizim motorumuz, insanın kendi tarayıcısına eklenti (side panel) olarak bağlanır. Sıra: benchmark önce (hem pazarlama verisi hem optimizasyon pusulası), insan yüzeyi sonra. Ücretli LLM koşusu varsayılan KAPALI (bütçe politikası).

## Goal
Build a reproducible benchmark lab covering browser engines, desktop browsers, AI browsers/agents and crawl APIs, use its evidence to optimize the engine at micro level, and ship a human-facing browser extension that exposes the same engine (read page, fan-out search, API discovery) — with every public number backed by raw data, n, CI and a reproduce command.

## Current context / assumptions (read this first; you know nothing about the repo)
- Repo `$REPO=~/.hermes/sandboxes/docker/default/home/ai_browser_farm`. Terminal backend is SSH as user `pc`. Python 3.14 venv: `$REPO/.venv/bin/python`. System `python3` must also stay green (optional deps are skipped there).
- Product (already built, 170 tests green, deployed commit `053f5a2`): REST API `src/api/server.py` on `127.0.0.1:8090` (router + `/v1/jobs/*` + `/v1/search/fanout`), cascading worker `src/browser_engine/worker.py` (lightpanda -> chromium -> camofox ladder), real drivers `src/browser_engine/engine_drivers.py` (lightpanda CLI per fetch, pooled Playwright Chromium), MCP server `src/mcp_server.py`. Read `AGENTS.md` and the skill `ai-browser-farm-dev` (slice loop, deploy pitfalls) before starting.
- Host: Ubuntu 26.04, 12 cores, 30 GB RAM, 404 GB free. Installed: Playwright chromium-headless-shell 156.0.8078.4 (`~/.cache/ms-playwright`), `~/.local/bin/lightpanda` (1.1.0-nightly, moving tag), snap Firefox 158.0.1 and snap Brave 1.98.60. The live router + Hermes gateway run on the same box => **measurement noise**; benchmarks run only when `uptime` load < 1.0 and are recorded with the load average.
- Constraints from the user (do not violate): cost-conscious (no paid model calls for benchmarking without explicit approval + hard cap), prefer public datasets/leaderboards, every claim verified ("Done is a Claim — Show the Receipt"), `# shortcut:` comment on every deliberate simplification, never hand-edit `~/.hermes/config.yaml`, never break `/v1/chat/completions`.
- Verified facts (web research, 2026-10-24) the plan relies on:
  - Chrome for Testing JSON: `https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json` (Stable 156.0.8078.47: `chrome`, `chrome-headless-shell`, `chromedriver` for `linux64`).
  - Lightpanda published methodology: Go+chromedp crawler on 933 pages of `https://demo-browser.lightpanda.io/amiibo/`, m5.large, memory via `smem` (PSS) sampled every 100 ms, peak taken; Chrome = tabs in one browser, Lightpanda = one process per task (their own caveat). Their numbers (25 parallel: 123 MB vs 2.0 GB, 4.81 s vs 46.70 s) are **vendor-reported** => listed separately, never as ours.
  - Standard suites: Speedometer 3.1, JetStream 3.0, MotionMark 1.3.2 at `https://browserbench.org/`. Chrome's own record (blog.google, 2026-06-04): Speedometer 61, JetStream 469 on an M5 MacBook Pro — not comparable to this Linux box; never mix.
  - Agent leaderboards (third-party, `https://leaderboard.steel.dev/`): Online-Mind2Web top = Browser Use Cloud bu-max 97.0%, WebVoyager top = browser-control (Fable 5) 99.19%, WebArena top = WebTactix (DeepSeek v3.2) 74.3%. Browser Use Bench v2.1 (Oct 2026): GPT-6.1 Sol 79.6, Browser Use agent 72.9 at ~11 cents/task.
  - AI-browser landscape (Oct 2026): ChatGPT Atlas retired 2026-08-09; Arc maintenance-only; Edge Copilot Mode folded into Edge (2026-05-13); alive: Perplexity Comet (Win/Mac/iOS/Android — **no Linux**), Dia (macOS/Apple Silicon only), Opera Neon (Win/Mac), Gemini in Chrome (Win/Mac/ChromeOS), Claude in Chrome (extension), Brave Leo (Linux ok, assistant only), Edge (Linux ok). => On this Linux host we can hands-on: Chrome, Chromium, Edge, Brave, Opera, Vivaldi, Firefox, Playwright WebKit, Lightpanda, (optional) Ladybird/Servo. We **cannot** run Comet/Dia/Neon/Safari here (see Open Questions).
  - Extensions: Chrome Side Panel API is stable (Chrome 114+, MV3). Native messaging exists but loopback HTTP + bearer key reuses the existing server with less code.

## Architecture / proposed approach
New package `src/bench/` (stdlib + Playwright only, no new heavy deps): `stats` (bootstrap CI, claim gate) -> `procmem` (PSS/CPU of a process tree from `/proc`) -> `fixture_server` (deterministic local pages, zero network noise) -> `adapters` (one uniform `start/fetch/stop` interface; all Chromium-family + Lightpanda driven through **CDP via Playwright `connect_over_cdp`** so the protocol path is identical) -> `runner` (cold start + warm fetch, N lifecycles) -> `report` (markdown that only prints a ratio when 95% CIs do not overlap; vendor numbers in a separate table). Suites (standard browser suites, extraction quality, our cascade, no-LLM task fidelity) are thin wrappers on the same runner. Optimization and the extension consume the results; nothing ships on a hunch.

Benchmark taxonomy (what "everything AI web-surf can do" maps to):

| Category | Examples | Tier A (free, default) | Tier B (opt-in, paid) |
|---|---|---|---|
| Engines | Lightpanda, Chrome headless-shell, Chrome CfT, Firefox/Gecko, WebKit, (Ladybird, Servo) | local fixtures: cold start, warm latency, PSS, CPU, success | — |
| Desktop browsers | Chrome, Edge, Brave, Opera, Vivaldi, Firefox | same + Speedometer/JetStream headless | — |
| AI browsers/agents | Comet, Dia, Neon, Gemini/Claude in Chrome | feature/architecture cards from public docs (no scores invented) | needs Win/Mac (open question) |
| Extraction | trafilatura, readability, Lightpanda markdown, Crawl4AI, Jina Reader | public dataset F1 + docs/s | — |
| Crawl/browse APIs | Firecrawl, Browserbase, Steel | vendor-reported table with citations | accounts + approval |
| Agent task success | Online-Mind2Web, WebVoyager, WebArena, BU Bench | leaderboard snapshot (cited, dated) | self-run under `BENCH_MAX_USD` cap |
| Our cascade | lightpanda -> chromium vs each alone | success%, p50/p95, PSS on corpus | — |

Phases: 0 inspect & inventory -> 1 harness core (TDD) -> 2 install targets + first real run -> 3 suites -> 4 evidence-driven optimization -> 5 human extension -> 6 agent tiers + publication. Each task ends with a commit. Use: `GC='git -c user.name="Hermes Agent" -c user.email="hermes@localhost"'`.

---

## Phase 1 — Harness core (pure, hermetic, TDD). Do this before downloading anything.

### Task 1.1 — `src/bench/stats.py` (robust statistics + claim gate)
1. Create `src/bench/__init__.py` (empty) and failing test `tests/test_bench_stats.py`:
```python
import unittest
from src.bench.stats import bootstrap_ci, mad, ratio_claim, summarize


class StatsTests(unittest.TestCase):
    def test_mad(self):
        self.assertEqual(mad([1, 2, 3, 4, 100]), 1)

    def test_bootstrap_is_deterministic_and_brackets_median(self):
        xs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        a, b = bootstrap_ci(xs), bootstrap_ci(xs)
        self.assertEqual(a, b)
        self.assertLessEqual(a[0], 14.5)
        self.assertGreaterEqual(a[1], 14.5)

    def test_separated_samples_are_claimable_with_ratio(self):
        base = [100 + i * 0.1 for i in range(12)]
        cand = [10 + i * 0.1 for i in range(12)]
        r = ratio_claim(base, cand)
        self.assertTrue(r["claimable"])
        self.assertGreater(r["ratio"], 9)

    def test_overlapping_samples_not_claimable(self):
        xs = [10 + i * 0.1 for i in range(12)]
        r = ratio_claim(xs, list(xs))
        self.assertFalse(r["claimable"])
        self.assertEqual(r["reason"], "ci overlap")

    def test_too_few_samples_not_claimable(self):
        r = ratio_claim([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        self.assertFalse(r["claimable"])
        self.assertTrue(r["reason"].startswith("n<"))

    def test_summarize_shape(self):
        s = summarize([1, 2, 3, 4, 5, 6])
        self.assertEqual(set(s), {"n", "median", "mad", "ci95", "min", "max"})
```
2. Run `cd $REPO && .venv/bin/python -m unittest tests.test_bench_stats -v` -> expect `ModuleNotFoundError: No module named 'src.bench.stats'` (RED).
3. Implement `src/bench/stats.py`:
```python
"""Robust statistics for benchmark samples (stdlib only)."""
import random
import statistics
from typing import Callable, Dict, Sequence, Tuple

MIN_CLAIM_SAMPLES = 10  # fewer independent lifecycles than this can never back a public claim


def mad(xs: Sequence[float]) -> float:
    m = statistics.median(xs)
    return statistics.median([abs(x - m) for x in xs])


def bootstrap_ci(xs: Sequence[float], stat: Callable = statistics.median, n_boot: int = 2000,
                 alpha: float = 0.05, seed: int = 1337) -> Tuple[float, float]:
    if len(xs) < 2:
        raise ValueError("need at least 2 samples")
    rng = random.Random(seed)
    data = list(xs)
    boots = sorted(stat([rng.choice(data) for _ in data]) for _ in range(n_boot))
    return boots[int(alpha / 2 * n_boot)], boots[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]


def summarize(xs: Sequence[float]) -> Dict:
    lo, hi = bootstrap_ci(xs)
    return {"n": len(xs), "median": statistics.median(xs), "mad": mad(xs),
            "ci95": [lo, hi], "min": min(xs), "max": max(xs)}


def ratio_claim(baseline: Sequence[float], candidate: Sequence[float]) -> Dict:
    """Lower-is-better metric. ratio = baseline/candidate median; claimable only when both
    have n>=MIN_CLAIM_SAMPLES and the two 95% bootstrap CIs do not overlap."""
    if min(len(baseline), len(candidate)) < MIN_CLAIM_SAMPLES:
        return {"claimable": False, "reason": f"n<{MIN_CLAIM_SAMPLES}"}
    b, c = summarize(baseline), summarize(candidate)
    overlap = not (c["ci95"][1] < b["ci95"][0] or b["ci95"][1] < c["ci95"][0])
    ratio = b["median"] / c["median"] if c["median"] else float("inf")
    return {"claimable": not overlap, "ratio": ratio,
            "reason": "ci overlap" if overlap else "ok", "baseline": b, "candidate": c}
```
4. Re-run -> `Ran 6 tests ... OK`. Commit: `$GC add src/bench tests/test_bench_stats.py && $GC commit -q -m "feat(bench): bootstrap stats + claim gate"`.

### Task 1.2 — `src/bench/procmem.py` (PSS + CPU of a process tree, Linux `/proc`)
PSS (not RSS) because Chrome shares pages across processes; same method Lightpanda documents (`smem`).
1. Failing test `tests/test_bench_procmem.py`:
```python
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from src.bench.procmem import TreeSampler, pids_with_exe_prefix, tree_pids

LINUX = os.path.exists("/proc/self/smaps_rollup")


@unittest.skipUnless(LINUX, "linux only")
class ProcmemTests(unittest.TestCase):
    def test_sampler_sees_child_memory(self):
        code = ("import time\nb = bytearray(80*1024*1024)\n"
                "for i in range(0, len(b), 4096): b[i] = 1\ntime.sleep(1.2)")
        p = subprocess.Popen([sys.executable, "-c", code])
        s = TreeSampler(lambda: [p.pid], interval_s=0.05)
        s.start()
        p.wait()
        s.stop()
        self.assertGreater(s.peak_pss_kib, 60 * 1024)

    def test_tree_includes_grandchildren(self):
        p = subprocess.Popen(["sh", "-c", "sleep 1.5 & wait"])
        time.sleep(0.3)
        try:
            self.assertGreaterEqual(len(tree_pids(p.pid)), 2)
        finally:
            p.kill()
            p.wait()

    def test_cpu_seconds_for_busy_child(self):
        code = "import time\nt = time.time()\nwhile time.time() - t < 0.7: pass"
        p = subprocess.Popen([sys.executable, "-c", code])
        s = TreeSampler(lambda: [p.pid], interval_s=0.05)
        s.start()
        p.wait()
        s.stop()
        self.assertGreater(s.cpu_seconds, 0.3)

    def test_pids_with_exe_prefix_finds_top_processes_only(self):
        tmp = tempfile.mkdtemp()
        exe = os.path.join(tmp, "sleep")
        shutil.copy(os.path.realpath(shutil.which("sleep")), exe)
        os.chmod(exe, 0o755)
        p = subprocess.Popen([exe, "2"])
        time.sleep(0.2)
        try:
            self.assertEqual(pids_with_exe_prefix(tmp), [p.pid])
        finally:
            p.kill()
            p.wait()
```
2. Run -> `ModuleNotFoundError` (RED). 3. Implement `src/bench/procmem.py`:
```python
"""Process-tree PSS/CPU sampling from /proc (PSS = shared pages divided among sharers)."""
import os
import threading
from typing import Callable, Dict, List, Optional

CLK_TCK = os.sysconf("SC_CLK_TCK")


def _stat_fields(pid: int) -> Optional[List[str]]:
    """Fields after the ')' of /proc/<pid>/stat: [0]=state(3) [1]=ppid(4) [11]=utime(14) [12]=stime(15)."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
    except OSError:
        return None
    return data[data.rindex(")") + 2:].split()


def _children_map() -> Dict[int, List[int]]:
    kids: Dict[int, List[int]] = {}
    for name in os.listdir("/proc"):
        if name.isdigit():
            f = _stat_fields(int(name))
            if f:
                kids.setdefault(int(f[1]), []).append(int(name))
    return kids


def tree_pids(root: int) -> List[int]:
    kids = _children_map()
    out, stack = [], [root]
    while stack:
        pid = stack.pop()
        out.append(pid)
        stack.extend(kids.get(pid, []))
    return out


def pss_kib(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/smaps_rollup") as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def pids_with_exe_prefix(prefix: str) -> List[int]:
    """Top-level processes whose executable lives under ``prefix`` (parent not also matching)."""
    prefix = os.path.realpath(prefix)
    matched: Dict[int, int] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            exe = os.path.realpath(os.readlink(f"/proc/{name}/exe"))
        except OSError:
            continue
        f = _stat_fields(int(name))
        if f and exe.startswith(prefix):
            matched[int(name)] = int(f[1])
    return sorted(pid for pid, ppid in matched.items() if ppid not in matched)


class TreeSampler:
    """Samples PSS (peak of the summed tree) and CPU ticks (max per pid, so exited pids still count)."""

    def __init__(self, roots_fn: Callable[[], List[int]], interval_s: float = 0.1) -> None:
        self._roots_fn, self._interval = roots_fn, interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self.peak_pss_kib = 0
        self._ticks: Dict[int, int] = {}

    def _tick(self) -> None:
        pids = set()
        for root in self._roots_fn():
            pids.update(tree_pids(root))
        total = 0
        for pid in pids:
            total += pss_kib(pid)
            f = _stat_fields(pid)
            if f:
                self._ticks[pid] = max(self._ticks.get(pid, 0), int(f[11]) + int(f[12]))
        self.peak_pss_kib = max(self.peak_pss_kib, total)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(self._interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._tick()
        self._stop.set()
        self._thread.join(timeout=2)

    @property
    def cpu_seconds(self) -> float:
        return sum(self._ticks.values()) / CLK_TCK
```
4. Run `.venv/bin/python -m unittest tests.test_bench_procmem -v` -> `Ran 4 tests ... OK`. Commit `feat(bench): /proc PSS+CPU tree sampler`.

### Task 1.3 — `src/bench/fixture_server.py` (deterministic pages; no network noise)
Why: Lightpanda's own first benchmark used a local fake e-commerce page to isolate browser overhead; do the same, and add a page that only works if JS ran (SPA) so "success" means "executed JS correctly".
1. Failing test `tests/test_bench_fixtures.py`:
```python
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
```
2. RED (`ModuleNotFoundError`). 3. Implement `src/bench/fixture_server.py`:
```python
"""Deterministic local pages so engine overhead is measured without network noise."""
import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MARKERS = {"static": "ARTICLE-MARKER-7f3a", "spa": "SPA-MARKER-b81c", "heavy": "HEAVY-MARKER-02de"}
MAX_HEAVY_ROWS = 50000

STATIC = ("<!doctype html><html><head><title>Static</title></head><body><nav>menu</nav><article>"
          f"<h1>Static article</h1><p>{MARKERS['static']} " + "Lorem ipsum dolor sit amet. " * 80 +
          "</p></article><footer>f</footer></body></html>")

SPA = ("<!doctype html><html><head><title>SPA</title></head><body><div id=\"app\">loading</div><script>"
       "(async () => {"
       "const p = await (await fetch('/api/product')).json();"
       "const r = await (await fetch('/api/reviews')).json();"
       "document.getElementById('app').innerHTML = '<h1>' + p.name + '</h1><p>" + MARKERS["spa"] +
       " ' + r.items.join(' | ') + '</p>';"
       "})();</script></body></html>")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body: str, ctype: str = "text/html; charset=utf-8", status: int = 200) -> None:
        raw = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        if url.path == "/static":
            return self._send(STATIC)
        if url.path == "/spa":
            return self._send(SPA)
        if url.path == "/api/product":
            return self._send(json.dumps({"name": "Widget"}), "application/json")
        if url.path == "/api/reviews":
            time.sleep(0.05)  # fixed server think-time, identical for every engine
            return self._send(json.dumps({"items": ["good", "fine", "ok"]}), "application/json")
        if url.path == "/heavy":
            n = min(int(q.get("n", ["2000"])[0]), MAX_HEAVY_ROWS)
            rows = "".join(f"<div class='r'><span>row {i}</span></div>" for i in range(n))
            return self._send(f"<!doctype html><html><body>{rows}<p>{MARKERS['heavy']}</p></body></html>")
        if url.path == "/robots.txt":
            return self._send("User-agent: *\nAllow: /\n", "text/plain")
        self._send("not found", status=404)


@contextlib.contextmanager
def fixture_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
```
4. Run `.venv/bin/python -m unittest tests.test_bench_fixtures -v` -> `Ran 4 tests ... OK`. Commit `feat(bench): deterministic fixture server`.

### Task 1.4 — adapters (`src/bench/adapters.py`)
One interface; all CDP engines share one code path so differences are the engine, not the harness.
1. Failing test `tests/test_bench_adapters.py` (hermetic: uses a fake adapter + checks helper functions only; real engines are exercised in Task 2.3):
```python
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
        self.assertIn("--no-sandbox", a)  # applied to ALL chromium-family targets (documented in methodology)

    def test_lightpanda_argv(self):
        self.assertEqual(lightpanda_argv("/x/lightpanda", 9222),
                         ["/x/lightpanda", "serve", "--host", "127.0.0.1", "--port", "9222"])

    def test_fetch_result_defaults(self):
        r = FetchResult(ok=True, ms=1.5, html_len=10)
        self.assertEqual(r.error, "")
```
2. RED. 3. Implement `src/bench/adapters.py`:
```python
"""Uniform engine adapters. Every CDP engine (Chromium family + Lightpanda) is driven the same
way: spawn the binary ourselves (so we own the pid for PSS) and attach Playwright over CDP."""
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.bench.procmem import pids_with_exe_prefix


@dataclass
class FetchResult:
    ok: bool
    ms: float
    html_len: int
    error: str = ""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def chromium_argv(exe: str, port: int, profile: str) -> List[str]:
    # shortcut: --no-sandbox on every Chromium-family target (Ubuntu AppArmor restricts unprivileged userns
    #   for extracted binaries); identical for all vendors so the comparison stays fair. Upgrade: sandboxed run.
    return [exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "--no-sandbox", "--disable-gpu", "about:blank"]


def lightpanda_argv(exe: str, port: int) -> List[str]:
    return [exe, "serve", "--host", "127.0.0.1", "--port", str(port)]


class CdpAdapter:
    POLL_S = 0.02  # marker polling quantum; same for every engine (documented in methodology)

    def __init__(self, target_id: str, argv_fn: Callable[[int, str], List[str]]) -> None:
        self.id, self._argv_fn = target_id, argv_fn
        self._proc: Optional[subprocess.Popen] = None
        self._pw = self._browser = None
        self._profile = ""

    def start(self) -> None:
        port, self._profile = free_port(), tempfile.mkdtemp(prefix="bench-prof-")
        self._proc = subprocess.Popen(self._argv_fn(port, self._profile),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5).read()
                break
            except Exception:
                time.sleep(0.02)
        else:
            raise RuntimeError(f"{self.id}: CDP endpoint did not come up")
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

    def root_pids(self) -> List[int]:
        return [self._proc.pid] if self._proc else []

    def fetch(self, url: str, marker: str, timeout_s: float = 30.0) -> FetchResult:
        t0 = time.perf_counter()
        ctx = None
        try:
            ctx = self._browser.new_context()
            page = ctx.new_page()
            page.goto(url, wait_until="load", timeout=timeout_s * 1000)
            deadline = time.monotonic() + timeout_s
            html = page.content()
            while marker not in html and time.monotonic() < deadline:
                time.sleep(self.POLL_S)
                html = page.content()
            return FetchResult(marker in html, (time.perf_counter() - t0) * 1000, len(html))
        except Exception as exc:  # engine crash/unsupported API counts as a failed fetch, not a harness error
            return FetchResult(False, (time.perf_counter() - t0) * 1000, 0, type(exc).__name__)
        finally:
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:
                    pass

    def stop(self) -> None:
        for closer in (lambda: self._browser.close(), lambda: self._pw.stop()):
            try:
                closer()
            except Exception:
                pass
        if self._proc:
            self._proc.kill()
            self._proc.wait()
        shutil.rmtree(self._profile, ignore_errors=True)


class PlaywrightAdapter:
    """Gecko / WebKit: Playwright launches its own patched builds (disclosed in every report).
    # shortcut: patched Firefox/WebKit, not vendor Firefox/Safari. Upgrade: Firefox via WebDriver BiDi."""

    def __init__(self, target_id: str, browser_name: str, exe_prefix: str) -> None:
        self.id, self._name, self._prefix = target_id, browser_name, exe_prefix
        self._pw = self._browser = None

    def start(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = getattr(self._pw, self._name).launch(headless=True)

    def root_pids(self) -> List[int]:
        return pids_with_exe_prefix(self._prefix)

    fetch = CdpAdapter.fetch  # identical measurement code path
    POLL_S = CdpAdapter.POLL_S

    def stop(self) -> None:
        for closer in (lambda: self._browser.close(), lambda: self._pw.stop()):
            try:
                closer()
            except Exception:
                pass
```
4. Run `.venv/bin/python -m unittest tests.test_bench_adapters -v` -> `Ran 4 tests ... OK`. Commit `feat(bench): uniform CDP/Playwright adapters`.

### Task 1.5 — runner + env capture (`src/bench/runner.py`, `src/bench/env.py`)
Unit of statistics = **one lifecycle** (fresh process): 10 lifecycles x (cold start, 3 warmups, 10 measured fetches) per target x scenario. Per-lifecycle median is the sample, so claims have n=10 independent units, not 100 autocorrelated fetches.
1. Failing test `tests/test_bench_runner.py`:
```python
import unittest

from src.bench.adapters import FetchResult
from src.bench.env import capture_env
from src.bench.runner import Scenario, Target, run_cell


class FakeAdapter:
    def __init__(self, ok=True, ms=5.0):
        self.id, self._ok, self._ms = "fake", ok, ms

    def start(self): pass
    def stop(self): pass
    def root_pids(self): return []
    def fetch(self, url, marker, timeout_s=30.0):
        return FetchResult(self._ok, self._ms, 100 if self._ok else 0, "" if self._ok else "Boom")


class RunnerTests(unittest.TestCase):
    def test_run_cell_produces_one_row_per_lifecycle(self):
        t = Target("fake", lambda: FakeAdapter(True, 5.0))
        rows = run_cell(t, Scenario("static", "/static", "M"), "http://x", lifecycles=4, warmups=1, fetches=3)
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["target"] for r in rows}, {"fake"})
        self.assertEqual(rows[0]["success_rate"], 1.0)
        self.assertEqual(rows[0]["fetch_ms_median"], 5.0)
        self.assertIn("cold_start_ms", rows[0])
        self.assertIn("peak_pss_kib", rows[0])

    def test_failing_engine_records_zero_success_and_no_latency(self):
        t = Target("bad", lambda: FakeAdapter(False))
        rows = run_cell(t, Scenario("spa", "/spa", "M"), "http://x", lifecycles=2, warmups=0, fetches=2)
        self.assertEqual(rows[0]["success_rate"], 0.0)
        self.assertIsNone(rows[0]["fetch_ms_median"])

    def test_env_has_reproducibility_fields(self):
        env = capture_env()
        for key in ("cpu_model", "nproc", "mem_total_kib", "kernel", "loadavg_1m", "python", "git_sha", "timestamp"):
            self.assertIn(key, env)
```
2. RED. 3. Implement `src/bench/runner.py`:
```python
"""Runs target x scenario cells; one row per fresh-process lifecycle."""
import statistics
import time
from dataclasses import dataclass
from typing import Callable, Dict, List

from src.bench.procmem import TreeSampler


@dataclass(frozen=True)
class Scenario:
    id: str
    path: str
    marker: str


@dataclass(frozen=True)
class Target:
    id: str
    make_adapter: Callable[[], object]


def run_cell(target: Target, scenario: Scenario, base_url: str, lifecycles: int = 10,
             warmups: int = 3, fetches: int = 10) -> List[Dict]:
    rows: List[Dict] = []
    url = base_url + scenario.path
    for i in range(lifecycles):
        adapter = target.make_adapter()
        t0 = time.perf_counter()
        adapter.start()
        cold_ms = (time.perf_counter() - t0) * 1000
        try:
            for _ in range(warmups):
                adapter.fetch(url, scenario.marker)
            sampler = TreeSampler(adapter.root_pids, interval_s=0.1)
            sampler.start()
            results = [adapter.fetch(url, scenario.marker) for _ in range(fetches)]
            sampler.stop()
        finally:
            adapter.stop()
        wins = [r.ms for r in results if r.ok]
        rows.append({"target": target.id, "scenario": scenario.id, "lifecycle": i,
                     "cold_start_ms": cold_ms, "success_rate": len(wins) / len(results),
                     "fetch_ms_median": statistics.median(wins) if wins else None,
                     "peak_pss_kib": sampler.peak_pss_kib, "cpu_s": sampler.cpu_seconds})
    return rows
```
and `src/bench/env.py`:
```python
"""Capture everything needed to reproduce / sanity-check a run."""
import datetime
import os
import platform
import subprocess
import sys


def _read(path: str, default: str = "") -> str:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return default


def capture_env() -> dict:
    cpu = next((l.split(":", 1)[1].strip() for l in _read("/proc/cpuinfo").splitlines()
                if l.startswith("model name")), "unknown")
    mem = next((int(l.split()[1]) for l in _read("/proc/meminfo").splitlines()
                if l.startswith("MemTotal:")), 0)
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             timeout=5).stdout.strip()
    except Exception:
        sha = ""
    return {"cpu_model": cpu, "nproc": os.cpu_count(), "mem_total_kib": mem, "kernel": platform.release(),
            "governor": _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").strip(),
            "loadavg_1m": os.getloadavg()[0], "python": sys.version.split()[0], "git_sha": sha,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
```
4. Run -> `Ran 3 tests ... OK`. Commit `feat(bench): runner + env capture`.

### Task 1.6 — report with claim gate (`src/bench/report.py`)
Rule encoded in code, not in anyone's discipline: a "x faster" string can only be emitted when `ratio_claim(...)["claimable"]`.
1. Failing test `tests/test_bench_report.py`:
```python
import unittest

from src.bench.report import aggregate, render_markdown


def rows(target, fetch_ms, n=10, pss=50_000):
    return [{"target": target, "scenario": "static", "lifecycle": i, "cold_start_ms": 100.0,
             "success_rate": 1.0, "fetch_ms_median": fetch_ms, "peak_pss_kib": pss, "cpu_s": 0.5}
            for i in range(n)]


ENV = {"cpu_model": "X", "nproc": 12, "kernel": "k", "loadavg_1m": 0.2, "git_sha": "abc", "timestamp": "t"}


class ReportTests(unittest.TestCase):
    def test_claimable_ratio_is_rendered(self):
        md = render_markdown(rows("chrome", 100.0) + rows("lp", 10.0), ENV, baseline_id="chrome")
        self.assertIn("10.0×", md)

    def test_overlap_prints_no_ratio(self):
        md = render_markdown(rows("chrome", 100.0) + rows("other", 100.0), ENV, baseline_id="chrome")
        self.assertNotIn("×", md)
        self.assertIn("no significant difference", md)

    def test_failed_engine_shows_success_rate_not_latency(self):
        bad = [dict(r, success_rate=0.0, fetch_ms_median=None) for r in rows("lp", 1.0)]
        md = render_markdown(rows("chrome", 100.0) + bad, ENV, baseline_id="chrome")
        self.assertIn("0%", md)
        self.assertIn("n/a", md)

    def test_env_and_methodology_footer_present(self):
        md = render_markdown(rows("chrome", 100.0), ENV, baseline_id="chrome")
        self.assertIn("git abc", md)
        self.assertIn("lifecycles", md)

    def test_aggregate_groups_by_target_and_scenario(self):
        agg = aggregate(rows("a", 1.0) + rows("b", 2.0))
        self.assertEqual(set(agg), {("a", "static"), ("b", "static")})
```
2. RED. 3. Implement `src/bench/report.py`:
```python
"""Markdown report. Ratios only when 95% CIs do not overlap; failures shown, never hidden."""
import statistics
from typing import Dict, List, Tuple

from src.bench.stats import ratio_claim, summarize


def aggregate(rows: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    cells: Dict[Tuple[str, str], List[Dict]] = {}
    for r in rows:
        cells.setdefault((r["target"], r["scenario"]), []).append(r)
    out = {}
    for key, rs in cells.items():
        col = lambda name: [r[name] for r in rs if r[name] is not None]
        out[key] = {"lifecycles": len(rs), "success_rate": statistics.mean(r["success_rate"] for r in rs),
                    "cold_start_ms": col("cold_start_ms"), "fetch_ms": col("fetch_ms_median"),
                    "peak_pss_kib": col("peak_pss_kib"), "cpu_s": col("cpu_s")}
    return out


def _fmt(xs, scale=1.0) -> str:
    if len(xs) < 2:
        return "n/a"
    s = summarize(xs)
    return f"{s['median'] / scale:.1f} [{s['ci95'][0] / scale:.1f}–{s['ci95'][1] / scale:.1f}]"


def _vs(base, cand) -> str:
    if not base or len(cand) < 2 or len(base) < 2:
        return "n/a"
    claim = ratio_claim(base, cand)
    if claim["claimable"]:
        return f"{claim['ratio']:.1f}×"
    return "no significant difference" if claim["reason"] == "ci overlap" else claim["reason"]


def render_markdown(rows: List[Dict], env: Dict, baseline_id: str) -> str:
    agg = aggregate(rows)
    lines = ["# Benchmark report", ""]
    for scenario in sorted({s for _, s in agg}):
        lines += [f"## Scenario `{scenario}`", "",
                  "| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |",
                  "|---|---|---|---|---|---|"]
        base = agg.get((baseline_id, scenario), {}).get("fetch_ms", [])
        for (target, sc), a in sorted(agg.items()):
            if sc != scenario:
                continue
            vs = "baseline" if target == baseline_id else _vs(base, a["fetch_ms"])
            lines.append(f"| {target} | {a['success_rate']:.0%} | {_fmt(a['fetch_ms'])} | "
                         f"{_fmt(a['peak_pss_kib'], 1024)} | {_fmt(a['cold_start_ms'])} | {vs} |")
        lines.append("")
    lines += ["---", f"Run on {env['cpu_model']} ({env['nproc']} cores), kernel {env['kernel']}, "
              f"load {env['loadavg_1m']:.2f}, git {env['git_sha']}, {env['timestamp']}.",
              "Method: each cell = independent lifecycles (fresh process); the sample unit is the per-lifecycle "
              "median of warm fetches; CIs are 95% bootstrap; a ratio is shown only when CIs do not overlap "
              "(n>=10 lifecycles). Latency compares only successful fetches; success rate is reported beside it."]
    return "\n".join(lines)
```
4. Run -> `Ran 5 tests ... OK`. Run the **whole** suite on both interpreters: `.venv/bin/python -m unittest discover -s tests -t .` and `python3 -m unittest discover -s tests -t .` (expect `OK`, count = 170 + new). Commit `feat(bench): report with CI claim gate`.

### Task 1.7 — CLI entry (`src/bench/run.py`)
Thin argparse: `python -m src.bench.run --targets a,b --scenarios static,spa,heavy --baseline a --lifecycles 10 --out bench/results/<run_id>`; writes `raw.jsonl`, `env.json`, `REPORT.md`. Refuses to start when `os.getloadavg()[0] > 1.0` unless `--force` (record `forced: true` in env.json). Test (`tests/test_bench_run.py`): invoke `main([...])` with a registered fake target (`--targets fake`, injected via `TARGET_REGISTRY["fake"]`) in a temp dir; assert the three files exist and `REPORT.md` contains `# Benchmark report`; second test: load-guard returns exit code 2 when `os.getloadavg` is patched to 5.0. Commit.

---

## Phase 2 — Install every target, inspect hands-on, first real numbers

### Task 2.1 — Chrome for Testing resolver (pure function, TDD) + installer
Files: `scripts/bench/install_targets.py`, `tests/test_install_targets.py` (import via `sys.path` insert of repo root or make `scripts/bench/` importable by placing logic in `src/bench/install.py` and keeping the script a 5-line caller — prefer the latter).
1. Test `tests/test_bench_install.py`:
```python
import unittest

from src.bench.install import pick_cft_urls

SAMPLE = {"channels": {"Stable": {"version": "156.0.8078.47", "downloads": {
    "chrome": [{"platform": "linux64", "url": "https://x/chrome-linux64.zip"},
               {"platform": "win64", "url": "https://x/chrome-win64.zip"}],
    "chrome-headless-shell": [{"platform": "linux64", "url": "https://x/hs-linux64.zip"}]}}}}


class InstallTests(unittest.TestCase):
    def test_picks_linux64_assets_for_channel(self):
        version, urls = pick_cft_urls(SAMPLE, "Stable", "linux64")
        self.assertEqual(version, "156.0.8078.47")
        self.assertEqual(urls, {"chrome": "https://x/chrome-linux64.zip",
                                "chrome-headless-shell": "https://x/hs-linux64.zip"})

    def test_missing_channel_raises(self):
        with self.assertRaises(KeyError):
            pick_cft_urls(SAMPLE, "Beta", "linux64")
```
2. RED. 3. `src/bench/install.py` (pure resolver + side-effecting helpers, only the resolver is unit-tested):
```python
"""Download/verify/extract browser binaries into ~/.local/share/bench-browsers (no root)."""
import hashlib
import json
import os
import urllib.request
import zipfile
from typing import Dict, Tuple

ROOT = os.path.expanduser("~/.local/share/bench-browsers")
MANIFEST = os.path.join(ROOT, "manifest.json")
CFT_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"


def pick_cft_urls(data: dict, channel: str, platform: str) -> Tuple[str, Dict[str, str]]:
    ch = data["channels"][channel]
    urls = {}
    for binary in ("chrome", "chrome-headless-shell"):
        for item in ch["downloads"].get(binary, []):
            if item["platform"] == platform:
                urls[binary] = item["url"]
    return ch["version"], urls


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    return sha256_file(dest)


def unzip_keep_modes(path: str, dest: str) -> None:
    with zipfile.ZipFile(path) as z:  # zipfile drops exec bits; restore from external_attr
        for info in z.infolist():
            z.extract(info, dest)
            mode = info.external_attr >> 16
            if mode:
                os.chmod(os.path.join(dest, info.filename), mode)


def record(target_id: str, exe: str, version: str, source: str, sha256: str) -> None:
    os.makedirs(ROOT, exist_ok=True)
    data = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
    data[target_id] = {"exe": exe, "version": version, "source": source, "sha256": sha256}
    json.dump(data, open(MANIFEST, "w"), indent=2)
```
4. Run -> `Ran 2 tests ... OK`. Commit `feat(bench): CfT resolver + installer helpers`.

### Task 2.2 — Install the Linux-capable targets (mutating, network; log everything)
Targets and sources (resolve each URL at run time, store version + sha256 via `record()`; never hardcode a URL you have not just fetched):

| id | family | source |
|---|---|---|
| `chrome-cft` | chromium | CfT Stable `chrome` linux64 |
| `chrome-headless-shell` | chromium | CfT Stable `chrome-headless-shell` linux64 |
| `playwright-chromium` | chromium | already at `~/.cache/ms-playwright/chromium_headless_shell-1248` |
| `lightpanda` | lightpanda | `~/.local/bin/lightpanda` (record `lightpanda version` + sha256; nightly moves => rerun records new version) |
| `firefox-pw` | gecko | `.venv/bin/playwright install firefox` |
| `webkit-pw` | webkit | `.venv/bin/playwright install webkit` (needs `playwright install-deps` => **needs sudo; ask the user**; skip if refused) |
| `brave` | chromium | GitHub releases API `brave/brave-browser` asset `brave-browser-*-linux-amd64.zip` (not the snap: confinement may block CDP/profile dirs) |
| `edge`, `opera`, `vivaldi` | chromium | vendor `.deb` -> extract with `dpkg-deb -x <deb> <dir>` (no install, no root); download pages: packages.microsoft.com (`microsoft-edge-stable`), opera.com, vivaldi.com |
| `ladybird`, `servo` | own engines | OPTIONAL: Servo nightly binary; Ladybird needs a source build (~1 h) — do last, only if CDP/WebDriver is exposed |

Verification per target (copy-paste, expect a version string):
```bash
~/.local/share/bench-browsers/<id>/.../chrome --version      # e.g. "Google Chrome for Testing 156.0.8078.47"
python3 -c "import json;print(json.dumps(json.load(open('/home/pc/.local/share/bench-browsers/manifest.json')),indent=1))"
sysctl kernel.apparmor_restrict_unprivileged_userns          # 1 => --no-sandbox is REQUIRED for extracted binaries (already in chromium_argv)
```
Record anything that fails to launch headless in `docs/research/browsers/<id>.md` under "Known blockers" — a target that cannot run is a finding, not a gap to hide.

### Task 2.3 — Target registry + real smoke test (`src/bench/targets.py`)
1. Implement `src/bench/targets.py`: load `MANIFEST`; build `Target(id, make_adapter)` for each manifest entry — `lightpanda` -> `CdpAdapter(id, lambda port, prof: lightpanda_argv(exe, port))`; chromium-family -> `CdpAdapter(id, lambda port, prof: chromium_argv(exe, port, prof))`; `firefox-pw`/`webkit-pw` -> `PlaywrightAdapter(id, "firefox"/"webkit", exe_prefix=<playwright cache dir>)`. `TARGET_REGISTRY` is a dict filled lazily so tests can inject `"fake"`.
2. Real-engine smoke test `tests/test_bench_real_engines.py` (`skipUnless` the manifest entry exists): for each installed target start adapter, fetch `/static` from `fixture_server()`, assert `ok` and `html_len > 500`; for `/spa` assert `ok` for every target **except** record (not fail) targets that legitimately cannot run JS fully — use `subTest` and print a per-target line. Run: `.venv/bin/python -m unittest tests.test_bench_real_engines -v` -> expect one `ok` per installed target on `/static`; any `/spa` failure is logged as data.
3. Commit `feat(bench): target registry + real-engine smoke`.

### Task 2.4 — Hands-on inspection cards (read-only observation of installed targets)
Write `scripts/bench/inspect_target.py` (reuses `CdpAdapter`, `TreeSampler`, `pss_kib`) that prints JSON per target: version; install size (`du -sk`); **startup ms** (spawn -> `/json/version` 200, 10 runs, median); **idle PSS** with 0, 1 and 3 open `about:blank` tabs; **process count** (`len(tree_pids)`); exposed protocols (`curl /json/version` keys, `/json/protocol` presence, BiDi endpoint if any); listening ports (`ss -ltnp` filtered by the process tree); outbound connections during 30 s idle (`ss -tnp state established` sampled every second — passive observation only, no MITM). Unit test only the pure helpers (JSON shaping). Then write one card per target at `docs/research/browsers/<id>.md` with the fixed template:
```
# <name> <version>
Engine / language / process model:   (from the JSON above)
Automation surface:                  CDP | WebDriver BiDi | Juggler | none
Extension model:                     MV3 side panel | MV3 sidebar_action | none     (public docs link)
AI features & where they run:        cloud | on-device | none                       (public docs link; "unverified" if unknown)
Idle network behaviour (30 s):       <hosts contacted>
Measured: startup / idle PSS / 3-tab PSS / install size
Known blockers:
Sources:                             <urls + retrieval date>
```
Non-Linux AI browsers (Comet, Dia, Neon, Safari, Gemini in Chrome) get **desk-research cards** from vendor docs only, header `Status: desk research — not run on this host`, no scores. Commit `docs(research): browser inspection cards`.

### Task 2.5 — First real benchmark run (the receipt)
```bash
cd $REPO
uptime                                      # load must be < 1.0; if not, wait/stop heavy jobs
RUN=$(date +%Y%m%d_%H%M%S)
.venv/bin/python -m src.bench.run \
  --targets lightpanda,chrome-headless-shell,chrome-cft,playwright-chromium,firefox-pw \
  --scenarios static,spa,heavy --baseline chrome-headless-shell --lifecycles 10 \
  --out bench/results/$RUN
```
Expected: `bench/results/$RUN/{raw.jsonl,env.json,REPORT.md}`; `wc -l raw.jsonl` = targets x scenarios x 10; REPORT.md has one table per scenario. Sanity checks before believing it: (a) `static` success 100% on every engine, (b) rerun the same command and confirm medians agree within the CIs (reproducibility check), (c) `loadavg_1m` in `env.json` < 1.0. Commit `bench/results/$RUN` (small) with `data(bench): first run`.

---

## Phase 3 — Suites ("everything AI web-surf can do")

### Task 3.1 — Standard browser suites (Speedometer 3.1, JetStream 3.0)
File `src/bench/suites/browserbench.py`. **Do not guess automation hooks**: first read the suites' own docs/source (Speedometer README in the WebKit `PerformanceTests` repo; `https://browserbench.org/Speedometer3.1/` page source) to find the start/result mechanism (URL params / result element); write what you find into the module docstring, then implement `run_suite(adapter, url, timeout_s)` returning the numeric score. Test the **parser** (score extraction from a captured HTML snippet saved under `tests/fixtures/`) hermetically; the live run is a manual receipt. Rules: headless Chromium/Firefox/WebKit only; Lightpanda is reported as `n/a (unsupported Web APIs)` — never as 0; scores are machine-specific so **never placed next to** vendor numbers from Apple-silicon MacBooks. MotionMark needs a real compositor/GPU => **defer** (headed desktop session only; note in report).

### Task 3.2 — Extraction quality + throughput (free, public dataset)
Files `src/bench/suites/extraction.py`, `tests/test_bench_extraction.py`. Dataset: the public ScrapingHub article-extraction benchmark (HTML + ground-truth article body) — **verify repo URL and license at execution** and record both in `docs/research/`. Metric = token F1:
```python
from collections import Counter


def token_f1(pred: str, truth: str) -> float:
    p, t = Counter(pred.lower().split()), Counter(truth.lower().split())
    overlap = sum((p & t).values())
    if not overlap:
        return 0.0
    prec, rec = overlap / sum(p.values()), overlap / sum(t.values())
    return 2 * prec * rec / (prec + rec)
```
Tests first: identical -> `1.0`; disjoint -> `0.0`; `token_f1("a b c", "a b d")` -> `0.6667` (assertAlmostEqual places=3). Extractors compared: our `html_to_clean_markdown` (trafilatura), plain trafilatura, our regex fallback, Lightpanda `fetch --dump markdown` (serve the HTML via `fixture_server`-style temp server), `readability-lxml` (pip, venv only). Report mean F1 [CI over pages] and docs/s. Crawl4AI / Jina Reader only if installable/free; otherwise "vendor-reported" table.

### Task 3.3 — Our cascade vs each engine alone (the product claim)
File `src/bench/suites/cascade.py`. Corpus = fixtures (`static`, `spa`, `heavy`) + the Lightpanda demo site (`https://demo-browser.lightpanda.io/amiibo/` and subpages — it exists for benchmarking; respect robots.txt, cap concurrency at 5, identify via UA `HermesBrowserFarm`). Arms: lightpanda only, chromium only, **cascade** (`BrowserWorker.execute_task` with `engine_driver`). Metrics: success %, p50/p95 latency, peak PSS, escalation rate. Hypothesis to **test, not assume**: cascade ≈ chromium success at near-lightpanda median cost. If the data refutes it, the report says so and Phase 4 targets the cause.

### Task 3.4 — No-LLM task-fidelity micro-suite
File `src/bench/suites/fidelity.py`: scripted tasks on fixtures with exact expected outputs: (1) API-discovery recall on `/spa` must find `/api/product` and `/api/reviews` (2/2), (2) boilerplate removal on `/static` (marker present, `menu`/footer absent), (3) robots.txt block never escalates (`FetchBlocked`), (4) 2 MB cap respected. Pure pass/fail, zero cost, runs in CI-style unit tests too.

### Task 3.5 — Reported-numbers table (vendor/third-party, never mixed with ours)
File `bench/reported.json` + loader in `report.py`: each entry `{claim, value, source_url, retrieved, measured_by: "vendor|third-party"}`. Seed with the verified facts above (Lightpanda crawler numbers + methodology, Chrome Speedometer 61 / JetStream 469 on M5 MacBook, steel leaderboard top scores, BU Bench v2.1). Renderer prints them in a separate section titled "Reported by others — not reproduced here". Test: an entry missing `source_url` or `retrieved` is rejected.

---

## Phase 4 — Micro-optimization (evidence-gated)

Rule: **no optimization lands without a before/after harness result with non-overlapping CIs.** Order = by measured share of time, not by guesses.

### Task 4.1 — Stage timers in the worker (test first)
`tests/test_browser_worker.py`: add test asserting `execute_task(...)` result contains `timings_ms` with float keys `driver`, `markdown`, `discover`, all `>= 0`. Implement in `src/browser_engine/worker.py` with `time.perf_counter()` around the three calls inside the ladder loop (keep the last attempt's timings, plus `attempts_ms` list). Expose in the API job response unchanged otherwise. Run full suite; commit.

### Task 4.2 — Profile where time goes (read-only)
Run the Phase 3.3 cascade corpus with timers on; write `docs/research/profile_2026-10.md`: share of time in driver vs trafilatura vs HAR regex, per engine. Candidate backlog (each needs its own before/after):
1. Lightpanda **per-fetch subprocess** vs persistent `lightpanda serve` + CDP (add `lightpanda-fetch-cli` and `lightpanda-serve-cdp` as two bench targets; adopt serve mode into `engine_drivers.py` only if CI-separated win).
2. trafilatura option set (`favor_recall`, `include_formatting`) — speed vs F1 trade, decided by Task 3.2 numbers.
3. Skip HAR regex when the page is static (no `<script>`), compile regex once at module level.
4. `_allowed_by_robots` TTL cache (currently never expires; also a correctness shortcut).
5. Chromium pool: single worker thread serializes all fetches — measure throughput at 1/2/4 concurrent callers; if scaling is poor, add N-browser pool.
Each accepted change: failing perf-assertion test (generous bound, e.g. `assertLess(median_ms, X)` on fixtures) -> implement -> harness before/after table pasted into the commit message -> full suite green on both interpreters.

---

## Phase 5 — Human surface: the engine as a browser extension (reverse of "Claude in Chrome")

Positioning: instead of putting a model inside a browser, put the **AI-native web engine at the side of a human's browser**: one click gives clean markdown of the page as the engine sees it, discovered JSON APIs, cited fan-out search from a selection, export. Chromium-family first (one MV3 build covers Chrome, Edge, Brave, Opera, Vivaldi); Firefox (`sidebar_action`) second.

### Task 5.1 — Server CORS for the extension origin only (TDD)
`tests/test_product_api.py`: add `ExtensionCorsTests(_Base)`: set `ORACLE_EXTENSION_ORIGINS=chrome-extension://abc`; (a) `OPTIONS /v1/jobs/browse` with `Origin: chrome-extension://abc` -> 204 and `Access-Control-Allow-Origin: chrome-extension://abc`, `Access-Control-Allow-Headers` contains `Authorization`; (b) same with `Origin: https://evil.example` -> 204 **without** `Access-Control-Allow-Origin`; (c) env unset -> no CORS headers at all; (d) POST with allowed origin still requires the bearer (401 without). RED, then in `src/api/server.py`:
```python
def _extension_origins() -> set:
    return {o.strip() for o in os.environ.get("ORACLE_EXTENSION_ORIGINS", "").split(",") if o.strip()}
```
and in `RequestHandler`: `_cors()` returning `{"Access-Control-Allow-Origin": origin, "Vary": "Origin", "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}` only when `Origin` is in the allowlist; `do_OPTIONS` sends 204 + those headers + `Content-Length: 0`; `_send_json` merges `_cors()` into its headers. Why allowlist-only + bearer: a random web page must not be able to drive a localhost service (CSRF / DNS rebinding); the preflight fails for any non-listed origin. Full suite both interpreters; commit; deploy per the skill (`bash scripts/host/deploy_default_router.sh`), then add the env var via the 0600 env file `~/.config/oracle-router/browse_api.env` (the deploy template already loads it).

### Task 5.2 — Deterministic extension ID
Add `scripts/ext/ext_id.py` + unit test: given a base64 DER public key, extension ID = first 16 bytes of `sha256(DER)` mapped nibble-wise to `a`–`p`:
```python
import base64, hashlib, sys

def extension_id(pub_b64: str) -> str:
    digest = hashlib.sha256(base64.b64decode(pub_b64)).digest()[:16]
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 15)) for b in digest)

if __name__ == "__main__":
    print(extension_id(sys.argv[1]))
```
Test: output is 32 chars, all in `a`–`p`, deterministic. Generate a key: `openssl genrsa 2048 | openssl rsa -pubout -outform DER | base64 -w0` -> put in `extension/manifest.json` `"key"` (public key only; the private key stays outside the repo). Then `ORACLE_EXTENSION_ORIGINS=chrome-extension://$(python3 scripts/ext/ext_id.py "$KEY")`.

### Task 5.3 — Extension skeleton (`extension/`)
`extension/manifest.json`:
```json
{
  "manifest_version": 3,
  "name": "Browser Farm Companion",
  "version": "0.1.0",
  "description": "Read any page the way an AI-native web engine does: clean markdown, discovered APIs, cited search.",
  "permissions": ["sidePanel", "activeTab", "storage"],
  "host_permissions": ["http://127.0.0.1:8090/*"],
  "background": {"service_worker": "background.js"},
  "side_panel": {"default_path": "sidepanel.html"},
  "action": {"default_title": "Open Companion"},
  "key": "<PUBLIC_KEY_BASE64>"
}
```
`extension/background.js`: `chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });`.
`extension/sidepanel.html`: input for API key (stored in `chrome.storage.local`), buttons **Read page** and **Search selection**, `<pre id="out">`.
`extension/sidepanel.js` core:
```javascript
const BASE = "http://127.0.0.1:8090";
async function api(path, body) {
  const { key } = await chrome.storage.local.get("key");
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key || ""}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}
document.getElementById("read").onclick = async () => {
  const tab = await activeTab();
  const job = await api("/v1/jobs/browse", { url: tab.url });
  document.getElementById("out").textContent =
    `# engine: ${job.engine}\n\n${job.extracted_markdown}\n\n## APIs\n${(job.discovered_apis || []).join("\n")}`;
};
document.getElementById("search").onclick = async () => {
  const tab = await activeTab();
  const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => String(getSelection()) });
  const res = await api("/v1/search/fanout", { query: result });
  document.getElementById("out").textContent = res.grounded_context;
};
```
(Add `"scripting"` to `permissions`.) Privacy note in the panel: the page URL is sent to the **local** engine only; never to a third party.

### Task 5.4 — Extension end-to-end test (real Chromium, local server)
`tests/test_extension_e2e.py` (`skipUnless` playwright): start `BrowserFarmSaaSServer(port=0, db_dir=tmp, driver_fn=stub_returning_PAGE)` with env `ORACLE_EXTENSION_ORIGINS` and `BROWSE_API_KEY=k`; launch Playwright Chromium persistent context with `--disable-extensions-except=extension --load-extension=extension` (headless new supports extensions), open `chrome-extension://<id>/sidepanel.html`, set the key in `chrome.storage.local`, navigate a second tab to a fixture URL, click **Read page**, assert `#out` contains the stub's markdown and `# engine:`. Expected: `Ran N tests ... OK`. Also a negative test: wrong key -> `#out` shows `HTTP 401` (the unhandled rejection must be caught and printed — add try/catch to the click handlers if this fails).

### Task 5.5 — Cross-browser matrix (uses Phase 2 targets)
For each installed Chromium-family target (Chrome, Edge, Brave, Opera, Vivaldi) run the 5.4 test with that binary (`executable_path=`). Record pass/fail per vendor in `docs/research/extension_matrix.md`; vendor-specific breakage (e.g. Opera side-panel differences) is documented, not hidden. Firefox port (`sidebar_action`, `browser_specific_settings.gecko.id`) = separate follow-up task once Chromium passes.

---

## Phase 6 — Agent-level tiers and publication

### Task 6.1 — Leaderboard snapshot (Tier A, free)
`scripts/bench/leaderboard_snapshot.py`: fetch the public steel-dev leaderboard data (GitHub repo `steel-dev/leaderboard` or the site — **verify which is machine-readable**), write `bench/reported.json` entries with `source_url` + `retrieved`. Optional recurring refresh via `hermes cron` (weekly, silent) — cron job creation is mutating; ask first. Never present those scores as ours.

### Task 6.2 — Budget guard for any paid run (Tier B, default OFF)
`src/bench/budget.py` + tests: `BudgetGuard(max_usd, live_router, since)`; `check()` raises `BudgetExceeded` when `live_router.spent_since(since) > max_usd` (this method already exists in `src/router/live_router.py` and prices recorded usage). Test with a fake router returning 0.4 then 2.1 for `max_usd=1.0`. **Hard gate for the implementer:** no benchmark that calls a paid model is run until the user states a USD cap in chat; the run command must pass `--max-usd` and abort on `BudgetExceeded`. Candidate self-run agent evals (only after approval): a 20-task Online-Mind2Web subset, using the cheapest adequate model from the router registry.

### Task 6.3 — Marketing document generator
`scripts/bench/build_marketing.py` -> `docs/marketing/BENCHMARKS.md` from the latest `bench/results/*/REPORT.md` + `reported.json`. Rules enforced by code and a test: (1) only claimable rows get a headline ratio; (2) every figure line carries n, hardware, versions, date and the exact reproduce command; (3) an auto-generated **"Where we lose"** section lists every row where our engine is slower/less successful (credibility = the marketing); (4) vendor/third-party numbers only in the separate cited section; (5) raw data path linked. Test: feed synthetic results with one loss and one win; assert both sections present and no ratio for an overlapping pair.

### Task 6.4 — Status docs + skill update
Update `PRODUCT_STATUS.md` (verified facts only: which targets installed, which suites live, latest run id), refresh `CODEBASE_GRAPH.json` (`PYTHONPATH=. .venv/bin/python -m src.cli graph`), and patch skill `ai-browser-farm-dev` with the benchmark workflow (load check `uptime`, `--no-sandbox` parity, claim gate). Final: both-interpreter full suite, deploy only if `src/api/server.py` changed (Task 5.1).

---

## Tests / validation summary
- Every code task follows RED -> GREEN -> full-suite -> commit, using `.venv/bin/python -m unittest ...` and `python3 -m unittest ...` (system python must stay green; real-engine and extension tests use `skipUnless`).
- Hermetic by design: stats, procmem, fixtures, adapters helpers, runner (fake adapter), report, installer resolver, extraction metric, budget guard, CORS, extension-ID. Real-engine checks are **separate, labeled receipts** (Tasks 2.3, 2.5, 3.x live runs, 5.4).
- Reproducibility gate before any number is published: run the same command twice, medians must agree within CIs; `env.json` load < 1.0.
- Acceptance for the whole plan: `REPORT.md` for >= 5 engines x 3 scenarios with CIs; >= 6 browser cards; extraction F1 table; cascade table; extension e2e green on >= 3 Chromium vendors; `docs/marketing/BENCHMARKS.md` containing a "Where we lose" section.

## Risks, tradeoffs, open questions
- **Risks / honest limits**
  - Noise: shared box (router, Hermes, desktop). Mitigations: load guard, 10 independent lifecycles, bootstrap CI, repeat-run check. Optional hardening (needs sudo, ask): CPU governor `performance`; cgroup limits via `systemd-run --user --scope -p AllowedCPUs=2-3 -p MemoryMax=8G` only if cpuset delegation works for the user — to mimic Lightpanda's m5.large for apples-to-apples.
  - Architecture asymmetry: Chrome = tabs in one browser, Lightpanda = process per task (their own caveat). Report both "1 browser, N contexts" and "N processes" modes before drawing conclusions.
  - `--no-sandbox` on all Chromium-family targets (AppArmor userns restriction) slightly changes performance; applied uniformly and disclosed.
  - Playwright Firefox/WebKit are patched builds, not vendor Firefox/Safari; disclosed in every report.
  - Lightpanda nightly is a moving target; every result stores version + sha256; claims name the version.
  - Lightpanda via Playwright `connect_over_cdp` may hit unimplemented CDP calls (`new_context`, `content`); if so, fall back to Puppeteer/chromedp-style raw CDP in the adapter and document it — do not paper over by dropping the engine.
  - Legal/ethics: benchmark only public pages that allow it (robots.txt), cap concurrency; check each vendor's ToS before publishing comparisons (some cloud APIs restrict benchmarking publication); no scraping of competitor products; trademark-safe wording ("measured on…", never "X is bad").
  - Disk/time: ~2–3 GB of browser downloads; Ladybird source build is long and optional.
  - Agent benchmarks are where money disappears: default OFF, cap-gated, user approval required.
- **Tradeoffs**: PSS over RSS (accurate for multi-process, slower to read); lifecycle-median unit (n=10) over pooled fetches (honest, but slower runs); extension-first over forking a browser (months cheaper, but a fork is the only way to own the whole UX).
- **Open questions for the user (answer before the marked phase)**
  1. *Before Phase 5*: is "human surface" = browser **extension/side panel** (my recommendation) or a standalone browser/fork? And a name for the product.
  2. *Phase 2 scope*: do you have (or accept renting a cloud VM for) a Windows/macOS machine so Comet, Dia, Opera Neon, Safari and Gemini-in-Chrome can be inspected hands-on? On this Linux host they can only get desk-research cards.
  3. *Phase 6*: USD cap for the optional self-run agent benchmarks (default: none, i.e. Tier A only), and may I create a weekly cron to refresh the leaderboard snapshot?
  4. *Sudo*: OK to run `playwright install-deps` (WebKit libs) and optionally set the CPU governor for cleaner numbers?
- **Not in this plan (YAGNI/deferred)**: MotionMark (needs GPU/headed), camofox stealth (legal opt-in), Firefox extension port, web dashboard UI, Ladybird/Servo unless they expose CDP/WebDriver.

---

# ADDENDUM A (2026-10-24) — Product name, multi-OS lab, distro matrix, reverse engineering (REA)

## A0. Decisions from the user (final)
- **Product name: Vane.** Extension display name "Vane — Web Companion"; repo/package rename is a separate, mechanical task (A9). Until then code identifiers stay `ai_browser_farm`.
- Unified product = browser **extension / side panel** (decided earlier). Windows/macOS access: **user said "access exists"** — treat as: user has (or will provide) a Windows and a Mac machine, remote or local. Exact access method is still unknown => first task of the multi-OS phase is a 10-minute access probe (A1.1), not an assumption.
- Sudo: do not ask again. `sudo -n true` fails here (password required) => anything needing root is either done user-space (extract `.deb` with `dpkg-deb -x`, `LD_LIBRARY_PATH`) or is listed as a one-line command for the user. WebKit libs and the orphan-process leak were already fixed user-space (commit `67d88f0`).
- REA is in scope for **inspection** of every browser/AI product (see A5). No credential/DRM/anti-bot circumvention, no redistributing vendor code.

## A1. Multi-OS lab — what is actually possible (verified 2026-10-24)

Host facts: KVM works (`/dev/kvm` rw for user `pc`, Intel VT-x, nested=Y), Docker 29 present (user in `docker` group), 12 cores, 30 GB RAM (about 26 GB free after cleanup), 400 GB disk. QEMU is **not installed** (apt candidate `qemu-system-x86 1:10.2.1`); installing it needs root => user runs one command (A1.2). Everything else below is user-space.

| OS | How | Legality / cost | Notes |
|---|---|---|---|
| **Linux distros** | QEMU/KVM + official cloud images (qcow2) + cloud-init seed ISO; containers (Docker/LXC images) for userland-only checks | free, redistributable | Ubuntu `cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img` (HTTP 200 verified), Debian `cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2` (200 verified), Fedora releases tree (200), AlmaLinux/Rocky GenericCloud, openSUSE, Arch (arch-boxes), Alpine, NixOS |
| **Windows 11 / 10 / Server** | QEMU/KVM + Microsoft **Evaluation Center** ISOs (90-day Windows 11 Enterprise 26H2 x64+Arm64; Windows 10 Enterprise; LTSC; Server 180-day) + virtio-win drivers + autounattend.xml | evaluation licence is fine for testing; rearm/expiry must be tracked, no activation tricks | The fwlink redirects to a registration page (HTTP 301 -> info.microsoft.com landing, verified) => **ISO download is interactive (form)**: user downloads once into `~/vane-lab/iso/`, we automate everything after. Windows on GitHub Actions free runners is the zero-setup alternative for CI-style runs |
| **macOS** | **Only on Apple hardware** (Apple SLA: virtualization permitted only on Apple-branded computers, max 2 extra macOS VMs per host). Options: (a) the user's own Mac (SSH/remote, run the same harness natively); (b) GitHub Actions `macos-26` (M1, 3 vCPU/7 GB) and `macos-15-intel` runners, free for public repos, 4 vCPU/14 GB Intel; (c) paid cloud Mac (AWS EC2 Mac has a 24-hour minimum allocation) — only with user approval | **Hackintosh/OSX-KVM on this PC = EULA violation => explicitly NOT in this plan** | macOS gives us Safari + WebKit-native, Dia, Comet-for-Mac, Atlas-era leftovers, Gemini-in-Chrome |
| **Android / iOS** | out of scope for v1 (needs device farm); note Comet has iOS/Android versions — desk-research cards only | — | revisit after desktop |
| **ChromeOS** | Gemini in Chrome supports Chromebook Plus; desk research only | — | — |

### Task A1.1 — Access probe (do first; read-only)
Ask the user for: (1) Windows machine: physical/remote? RDP/SSH/WinRM reachable from the Linux box (hostname, user)? (2) Mac: physical/remote? SSH enabled (`System Settings > General > Sharing > Remote Login`)? Apple Silicon or Intel? Then record answers in `docs/lab/ACCESS.md` (hostnames + method only, **never credentials; secrets go through the Hermes vault / ssh-agent**). If neither is reachable, fall back to GitHub Actions runners for Windows/macOS measurements (workflow below) — that path needs only a public GitHub repo.

### Task A1.2 — One-time host setup (user runs once; everything after is automated)
```bash
sudo apt-get install -y qemu-system-x86 qemu-utils ovmf swtpm cloud-image-utils virtiofsd
sudo usermod -aG kvm pc          # already effectively true: /dev/kvm is rw for pc via ACL, so skip if `test -w /dev/kvm`
```
Verify: `qemu-system-x86_64 --version` (expect `QEMU emulator version 10.2.1`) and `qemu-img --version`. Windows 11 guests need TPM 2.0 + Secure Boot => `swtpm` + `ovmf` are required (or use the Win11 bypass registry keys inside autounattend — document whichever is chosen).

### Task A1.3 — Lab directory + image catalog (TDD, pure code first)
New package `src/lab/` (separate from `src/bench/` — OS provisioning vs measurement):
- `src/lab/catalog.py`: `IMAGES: Dict[str, ImageSpec]` with fields `id, family (linux|windows), url, sha256_url or sha256, arch, kind (cloud|iso), login, notes`. Test: every entry has `https://` URL, an `arch`, and either a checksum or `checksum_source`; ids unique; `ubuntu-24.04`, `debian-13`, `fedora-*`, `alma-9`, `rocky-9`, `opensuse-leap`, `arch`, `alpine`, `nixos` present.
- `src/lab/vm.py`: pure builders (unit-tested without QEMU): `qemu_argv(image, mem_mb, cpus, ssh_port, seed_iso)` returns the argv list; `cloud_init_user_data(ssh_pubkey, packages)` returns the YAML string; `snapshot_cmd(base, overlay)` -> `qemu-img create -f qcow2 -F qcow2 -b <base> <overlay>`. Always boot from a **copy-on-write overlay** so the downloaded base image stays pristine and every run starts clean (this is also how benchmarks stay comparable run to run).
- `src/lab/runner.py`: `LabVM` context manager: boot overlay with `-enable-kvm -cpu host -machine q35`, wait for SSH, `run(cmd)`, `copy_in/out`, destroy overlay on exit, **kill the QEMU process group** (lesson from the 12 GB orphan leak: always `start_new_session=True` + `killpg`).
- Smoke test (`skipUnless` qemu present): boot Ubuntu 24.04 cloud image, `uname -r` over SSH returns a kernel string, VM torn down, no QEMU process left (`pgrep qemu | wc -l` == 0).

### Task A1.4 — Distro matrix runner
For each distro VM: install the target browsers from the **native packaging path the user would really use** (apt/dnf/zypper/pacman/apk/nix + Flatpak + Snap where applicable), run the same `src/bench/` harness inside the guest via `LabVM.run("python3 -m src.bench.run ...")`, and pull `raw.jsonl` back. Report dimensions: distro x browser x packaging (deb vs snap vs flatpak startup differs a lot — Firefox/Brave snap vs deb is a finding on its own), glibc/musl (Alpine), libc/kernel versions, default sandbox behaviour (AppArmor userns restriction on Ubuntu 24.04+, SELinux on Fedora/Alma/Rocky). Matrix v1 (first 9, all free): Ubuntu 24.04, Ubuntu 26.04, Debian 13, Fedora (latest), AlmaLinux 9, Rocky 9, openSUSE Leap, Arch, Alpine. v2: NixOS, Linux Mint, Pop!_OS, Kali (ISO-only distros need `kind: iso` + unattended install; only add if cloud/qcow2 variants do not exist).
Acceptance: `bench/results/distro-matrix/<run>/REPORT.md` with one row per distro x browser, same claim-gate rules (n>=10 lifecycles, CI-gated ratios). Never mix guest numbers with host numbers: the VM adds overhead, so VM-vs-VM comparisons only, and every report names `vm: qemu-kvm, 4 vCPU, 8 GB`.

### Task A1.5 — Windows lab
1. User downloads Windows 11 Enterprise Evaluation ISO (x64) to `~/vane-lab/iso/` (interactive form; we cannot automate registration) + we fetch `virtio-win.iso` (Fedora project, public URL — verify at execution).
2. `src/lab/windows.py`: build `autounattend.xml` (unit-test: valid XML, contains product-key-free eval install, local admin `vane`, OpenSSH Server enablement, WinRM fallback), pack into an ISO with `genisoimage`/`xorriso`, boot with TPM+OVMF.
3. After first boot over SSH: install Chrome, Edge (preinstalled), Firefox, Brave via `winget` (or download), then run the harness (Python for Windows via winget). Note Windows process model: use `psutil` or `wmic`/`Get-Process` for memory — **`/proc` PSS does not exist on Windows**: add `src/bench/procmem_win.py` using `psutil` private working set (and say so in the report: different memory metric => never compare Windows and Linux memory columns directly).
4. Track the 90-day evaluation expiry in the VM metadata; rebuild from the pristine ISO overlay instead of extending trials.

### Task A1.6 — macOS lab (user's Mac or GitHub Actions; NOT a PC VM)
- If the user's Mac is reachable over SSH: run `src/bench/` natively (Python via Homebrew/uv). Memory metric on macOS = `footprint`/`vmmap` or psutil USS; document it; Safari automation via `safaridriver` (Remote Automation enabled by user once) and WebKit via Playwright. Dia/Comet/Neon are installed by the user from the vendor sites; we only inspect (A5).
- Otherwise use a workflow in a **public** repo (free for public repos): `.github/workflows/bench-mac.yml` with matrix `os: [macos-26, macos-15-intel, windows-latest, windows-11-arm, ubuntu-24.04]` that checks out the repo, installs Python+Playwright browsers, runs `python -m src.bench.run --targets <installed-on-runner> --lifecycles 10`, and uploads `bench/results/*` as artifacts. Caveat: shared runners are noisy (other tenants) => same claim gate, wider CIs, never presented next to the dedicated-hardware numbers. The repo must not contain secrets; `BROWSE_API_KEY` etc. stay out.
- Cost guard: GitHub macOS minute list price is $0.062 for private repos; keep the repo public or cap minutes; EC2 Mac (24 h minimum) only on explicit approval.

## A2. Browser/OS coverage matrix (what "every browser" means, by OS)
| Browser | Linux | Windows | macOS | Automation | Notes |
|---|---|---|---|---|---|
| Chrome / Chromium / Chrome for Testing | yes (done) | yes | yes | CDP | baseline family |
| Edge | yes (done) | native | yes | CDP | |
| Brave | yes (done) | yes | yes | CDP | Shields changes network timing; report with and without |
| Opera | yes (installer pending) | yes | yes | CDP | |
| Vivaldi | **blocked: no CDP port** | test again (may differ) | test again | none on Linux | recorded in manifest |
| Firefox | yes (done, Playwright build) + vendor build | yes | yes | Juggler (PW) / WebDriver BiDi (vendor); CDP removed in 141+ | add vendor Firefox via BiDi (Selenium/geckodriver) to avoid "patched build" caveat |
| Safari / WebKit | WebKit via PW (done, WPE) | — | **Safari native** | safaridriver | needs the Mac |
| Lightpanda | yes (done) | yes (WSL2 binary) | yes (aarch64-macos) | CDP | |
| Servo / Ladybird | optional | optional | optional | WebDriver? | only if automation exists |
| Comet / Dia / Neon / Fellou / Sigma / Genspark | — (Comet: no Linux build) | Comet, Neon | Comet, Dia, Neon | none public | inspection only (A5) |
| Gemini in Chrome / Claude in Chrome / ChatGPT agent | via Chrome | yes | yes | extension surface | inspection of extension packages (A5) |

## A3. What gets measured per OS (kept comparable)
Same fixtures (`/static`, `/spa`, `/heavy`), same lifecycle protocol, same report. Per-OS differences that MUST be disclosed in the report header: memory metric (PSS on Linux, working-set/USS elsewhere), sandbox on/off, power plan/governor, VM vs bare metal, thermal state. A cross-OS table only compares **ratios against that OS's own baseline browser**, never raw milliseconds across OSes/hardware.

## A4. Installed-software footprint per OS (cheap, high-signal for "micro optimization")
For each OS + browser: install size, process count at idle, idle PSS/working set with 0/1/3 tabs, startup time (cold + warm file cache: drop caches via `echo 3 > /proc/sys/vm/drop_caches` needs root => instead compare first-run vs second-run), background network at idle. These feed Phase 4 (what is the real overhead budget a browser spends before doing any work).

## A5. REA (reverse engineering) track — inspect every browser and AI-browser product

**Scope and rules (read first).** Goal = understand architecture, automation surface, extension model, update mechanism, network behaviour and security posture of each product so Vane can interoperate and be positioned honestly. Allowed: analysing binaries/packages you lawfully obtained and run on your own machine, passive observation of your own traffic, reading public docs/changelogs/leaked-nothing. Not allowed: breaking DRM/licence checks, bypassing paywalls or account entitlements, defeating anti-bot/fraud systems, attacking vendor servers, publishing vendor source or private keys, testing against other users' data. Findings that look like vulnerabilities are **reported to the vendor (responsible disclosure) before any publication**. Legal basis to record in `docs/rea/README.md`: interoperability/security-research exceptions differ by country (US DMCA §1201(f)/(j) and the Copyright Office exemptions; EU Software Directive Art. 6 decompilation for interoperability; Turkish FSEK art. 38 allows decompilation for interoperability) — and **EULA clauses can still prohibit it contractually**; user decides risk per vendor; when in doubt stay at "observe, don't decompile".

**Method per target (same template, `docs/rea/<target>.md`):**
1. *Acquire & fingerprint*: version, hash, signature/notarisation status (`codesign -dv`, `Get-AuthenticodeSignature`, `dpkg-sig`/`rpm -K`), package format, update channel URL. Zenity's Comet analysis is the model: Comet = Chromium + Perplexity "Sidecar" SPA + **three custom Chrome extensions** (not on the Web Store; auto-updated from `perplexity.ai/rest/browser/update-crx`) + a *simplified annotated HTML* representation of pages instead of the raw DOM. Verify those claims ourselves rather than citing them.
2. *Static inspection (Linux/Windows/macOS-agnostic)*: unpack the app (Chromium forks: `resources.pak`, `locales/`, bundled extensions under `<app>/…/default_apps` or `Extensions/`; Electron: `app.asar` via `npx @electron/asar extract`; Firefox derivatives: `omni.ja`; CRX: strip header, unzip), list manifests, `permissions`, `host_permissions`, `externally_connectable`, `content_scripts`, background/service-worker entry points, native-messaging hosts, bundled Chromium version vs upstream (security patch lag = a real finding), feature flags/`field_trial` configs, embedded endpoints (`strings`, `grep -o 'https\?://[^"]*'`), telemetry SDKs (Sentry, Segment…). Tools (all free/open): `7z`, `unzip`, `asar`, `strings`, `readelf`/`objdump`, `jq`, `ripgrep`, Ghidra only for native helpers and only when licence-compatible, `crxIntel`-style URL extractors, `js-beautify` + sourcemap recovery for minified bundles, `semgrep` for permission/pattern audit.
3. *Dynamic observation (own machine, own account, test profile)*: run with a clean profile; capture **your own** traffic via `mitmproxy` with the CA installed only in that profile, log hosts/paths/payload *shapes* (not other people's data); `strace -f -e trace=network,openat` (Linux), Process Monitor/Procmon (Windows), `fs_usage`/`dtruss` (macOS, SIP limits dtruss); Chrome internals pages (`chrome://net-export`, `chrome://version`, `chrome://flags`); CDP `Network`/`Fetch` domains when the browser exposes a port; record permission prompts and what the agent sees (the "page representation" sent to the model — that is the core of what Vane's `browse_url` markdown competes with).
4. *Agent surface & safety review* (AI browsers): how is page content separated from user instructions (Brave's published prompt-injection findings in Comet/Fellou/Neon show this is the weak point), confirmation gates before purchases/sends, per-site allowlists, logged-in-session handling, extension-to-sidecar messaging channel. Output = a **threat table** (injection vector, impact, mitigation observed) — useful both for our security design and for honest marketing.
5. *Deliverable per target*: `docs/rea/<target>.md` (architecture diagram in text/ASCII, version+hash, endpoints seen, permissions, update mechanism, what we could not verify), plus `docs/rea/COMPARISON.md` (one table across all targets) and a short "what Vane does differently/better/worse" section that feeds the marketing "Where we lose" page.

**REA task list (each bite-sized, each ends with a commit):**
- **A5.1** `docs/rea/README.md`: rules above + legal-basis note + disclosure policy + per-vendor risk column (`observe-only` vs `static-ok`). Review by the user before any dynamic work.
- **A5.2** `scripts/rea/unpack_crx.py` + test: given a CRX3 file, strip the header (magic `Cr24`, version, header length) and extract the ZIP; fixture = a tiny CRX built in the test; assert manifest.json recovered. Also `scripts/rea/extract_endpoints.py` (regex URL extractor, dedupe, drop W3C/schema noise) with tests on a fixture.
- **A5.3** `scripts/rea/audit_manifest.py` + test: reads a `manifest.json`, flags broad `host_permissions` (`<all_urls>`, `*://*/*`), `externally_connectable` wildcards, `debugger`/`nativeMessaging`/`webRequestBlocking` permissions, remote code (`content_security_policy` with `unsafe-eval`, remote scripts), outputs JSON risk list. Run it on **our own** `extension/manifest.json` first (eat our dog food), then on third-party extensions.
- **A5.4** Chromium-fork inspection on Linux (works today): Brave, Edge, Opera, Vivaldi, Chrome for Testing — unpack bundled extensions, compare bundled Chromium version vs Stable (156.0.8078.47) and list vendor-specific extensions/components. Write cards `docs/rea/{brave,edge,opera,vivaldi}.md`.
- **A5.5** Lightpanda internals (open source — read the source, no REA needed): CDP method coverage vs Chrome (what Playwright/Puppeteer calls fail), Web API gaps — explains where our cascade must escalate. Output feeds `docs/research/lightpanda_gaps.md` and a test list for the escalation logic.
- **A5.6** Windows/macOS AI browsers (needs the machines from A1.1): Comet, Dia, Opera Neon, Edge Copilot, Gemini-in-Chrome, Claude-in-Chrome extension (CRX from the Web Store is public), ChatGPT extension. Static first (A5.2/A5.3 tools), dynamic only for products where `docs/rea/README.md` marks `dynamic-ok`.
- **A5.7** Network posture table: per browser/OS, hosts contacted at idle for 5 minutes with a blank profile (telemetry, safe-browsing, update, AI endpoints). Passive (`ss`, `/proc/net/tcp`, mitmproxy own profile). Feeds privacy positioning of Vane ("what the page URL leaves your machine for").
- **A5.8** `docs/rea/COMPARISON.md` + hand the findings to Phase 5 (extension design: permission minimisation, injection-safe page representation).

## A6. Updated phase order
0 inspect/inventory -> 1 harness (**done**, commit `5f6d90f`) -> 2 install + first run (**done**, `5a77730`, `fadd76d`, `67d88f0`) -> **2b multi-OS lab** (A1.2 -> A1.3 -> A1.4 distro matrix; A1.5 Windows; A1.6 macOS/Actions) -> 3 suites -> **3b REA** (A5.1 first, A5.2–A5.5 on Linux now, A5.6–A5.7 once Windows/Mac access is confirmed) -> 4 optimization (evidence from 2b/3/3b) -> 5 Vane extension (permission design informed by A5.3/A5.6) -> 6 agent tiers + publication.

## A7. Risks specific to this addendum
- macOS legality: the only compliant paths are Apple hardware (user's Mac) or Apple-hardware-backed clouds/runners. The plan never virtualises macOS on this PC.
- Evaluation Windows ISOs expire (90 days) and require an interactive download; plan around rebuilds, not rearm hacks.
- RAM budget: 30 GB host, ~26 GB free: one Windows VM (8 GB) + one Linux VM (4 GB) at a time; never run VMs concurrently with benchmark runs on the host (noise) — the harness already refuses on load > 1.0; extend the guard to refuse when any `qemu-system` process is running.
- Disk: 5–6 GB per Windows image + ~1 GB per Linux cloud image + overlays => budget 80 GB under `~/vane-lab/` (404 GB free).
- REA legal/ethical exposure: contractual (EULA) rather than criminal in most jurisdictions, but it is real. The user decides per vendor; default is observe-only; vulnerabilities go to the vendor first.
- GitHub Actions numbers are noisy and shared; label them as such; keep them out of headline claims.
- Naming: confirm "Vane" has no trademark/package-name conflicts (npm, PyPI, Chrome Web Store, GitHub org, domain) before publication — one search task (A9).

## A8. Open questions for the user (short)
1. Windows/Mac access: how do I reach them (SSH/RDP/WinRM hostname)? Or should I use GitHub Actions public-repo runners first?
2. One-time install: OK to give you the single `apt-get install qemu…` line (A1.2), since sudo needs your password?
3. REA depth per vendor: default is observe-only for commercial AI browsers; tell me which ones you accept static decompilation for.

## A9. Mechanical follow-ups
- Name check + rename task: search npm/PyPI/Chrome Web Store/GitHub/domain for "vane"; if clear, rename extension + docs first, repo/package later (touches imports, systemd unit descriptions, skill docs).
