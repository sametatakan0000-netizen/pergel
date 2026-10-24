"""CLI: python -m src.bench.run --targets a,b --scenarios static,spa,heavy --baseline a --out DIR

Refuses to run on a busy machine (load > 1.0) unless --force; a forced run is flagged in env.json.
"""
import argparse
import json
import os
import sys
from typing import Callable, Dict, List

from src.bench.env import capture_env
from src.bench.fixture_server import MARKERS, fixture_server
from src.bench.report import render_markdown
from src.bench.runner import Scenario, Target, run_cell

MAX_LOAD_1M = 1.0
# id -> adapter factory. Real targets are added lazily by src.bench.targets (installed binaries only).
TARGET_REGISTRY: Dict[str, Callable[[], object]] = {}

SCENARIOS = {
    "static": Scenario("static", "/static", MARKERS["static"]),
    "spa": Scenario("spa", "/spa", MARKERS["spa"]),
    "heavy": Scenario("heavy", "/heavy?n=2000", MARKERS["heavy"]),
}


def _load_real_targets() -> None:
    try:
        from src.bench import targets
        targets.register_installed(TARGET_REGISTRY)
    except ImportError:
        pass  # targets module arrives with the install phase


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(prog="src.bench.run")
    ap.add_argument("--targets", required=True)
    ap.add_argument("--scenarios", default="static,spa,heavy")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--lifecycles", type=int, default=10)
    ap.add_argument("--warmups", type=int, default=3)
    ap.add_argument("--fetches", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true", help="run even when load > %.1f" % MAX_LOAD_1M)
    args = ap.parse_args(argv)

    load = os.getloadavg()[0]
    if load > MAX_LOAD_1M and not args.force:
        print(f"refusing: 1-min load {load:.2f} > {MAX_LOAD_1M} (use --force to override)", file=sys.stderr)
        return 2
    _load_real_targets()
    wanted = [t for t in args.targets.split(",") if t]
    unknown = [t for t in wanted if t not in TARGET_REGISTRY]
    if unknown:
        print(f"unknown targets: {unknown}; known: {sorted(TARGET_REGISTRY)}", file=sys.stderr)
        return 3
    scenarios = [SCENARIOS[s] for s in args.scenarios.split(",") if s in SCENARIOS]

    os.makedirs(args.out, exist_ok=True)
    env = capture_env()
    env["forced"] = bool(args.force and load > MAX_LOAD_1M)  # True only when --force actually overrode the guard
    rows: List[Dict] = []
    with fixture_server() as base:
        for tid in wanted:
            target = Target(tid, TARGET_REGISTRY[tid])
            for sc in scenarios:
                rows += run_cell(target, sc, base, args.lifecycles, args.warmups, args.fetches)
    with open(os.path.join(args.out, "raw.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    json.dump(env, open(os.path.join(args.out, "env.json"), "w"), indent=2)
    with open(os.path.join(args.out, "REPORT.md"), "w") as fh:
        fh.write(render_markdown(rows, env, baseline_id=args.baseline))
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
