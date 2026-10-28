"""Runs target x scenario cells; one row per fresh-process lifecycle."""
import statistics
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List

from src.bench.procmem import TreeSampler

# A single lifecycle (browser start + warmups + sampled fetches) is capped by
# this wall clock. A GUI browser that fails to bind headless CDP (e.g. Vivaldi)
# would otherwise block the whole run forever on connect_over_cdp.
DEFAULT_LIFECYCLE_TIMEOUT_S = 90.0


@dataclass(frozen=True)
class Scenario:
    id: str
    path: str
    marker: str


@dataclass(frozen=True)
class Target:
    id: str
    make_adapter: Callable[[], object]


def _run_lifecycle(target: Target, scenario: Scenario, url: str, warmups: int,
                   fetches: int) -> Dict:
    """One fresh-process lifecycle. Raises if the adapter hangs — caller bounds it."""
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
    return {"cold_start_ms": cold_ms, "success_rate": len(wins) / len(results),
            "fetch_ms_median": statistics.median(wins) if wins else None,
            "peak_pss_kib": sampler.peak_pss_kib, "cpu_s": sampler.cpu_seconds}


def run_cell(target: Target, scenario: Scenario, base_url: str, lifecycles: int = 10,
             warmups: int = 3, fetches: int = 10,
             timeout_s: float = DEFAULT_LIFECYCLE_TIMEOUT_S) -> List[Dict]:
    rows: List[Dict] = []
    url = base_url + scenario.path
    for i in range(lifecycles):
        box: Dict = {}
        done = threading.Event()

        def _work():
            try:
                box["out"] = _run_lifecycle(target, scenario, url, warmups, fetches)
            except BaseException as exc:  # noqa: BLE001 - report, never stall the run
                box["err"] = exc
            finally:
                done.set()

        th = threading.Thread(target=_work, daemon=True, name=f"{target.id}-{i}")
        th.start()
        if not done.wait(timeout_s):
            # Hung (e.g. connect_over_cdp blocked). Mark and move on.
            rows.append({"target": target.id, "scenario": scenario.id, "lifecycle": i,
                         "timed_out": True, "cold_start_ms": None, "success_rate": 0.0,
                         "fetch_ms_median": None, "peak_pss_kib": None, "cpu_s": None})
            continue
        if "err" in box:
            rows.append({"target": target.id, "scenario": scenario.id, "lifecycle": i,
                         "error": f"{type(box['err']).__name__}: {box['err']}",
                         "timed_out": False, "cold_start_ms": None, "success_rate": 0.0,
                         "fetch_ms_median": None, "peak_pss_kib": None, "cpu_s": None})
            continue
        rows.append({"target": target.id, "scenario": scenario.id, "lifecycle": i,
                     "timed_out": False, **box["out"]})
    return rows
