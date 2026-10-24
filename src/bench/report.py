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
