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
