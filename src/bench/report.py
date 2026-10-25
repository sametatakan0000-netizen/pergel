"""Markdown report. Ratios only when 95% CIs do not overlap; failures shown, never hidden."""
import json
import re
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


# ---------------------------------------------------------------------------
# Task 3.5 — reported numbers (vendor/third-party, cited; never mixed with ours)
# ---------------------------------------------------------------------------

REQUIRED_REPORTED_FIELDS = ("claim", "value", "source_url", "retrieved", "measured_by")
_REPORTED_BY = ("vendor", "third-party")


def load_reported(path: str = "bench/reported.json") -> List[Dict[str, str]]:
    """Load the vendor/third-party reported-numbers table.

    Every entry must carry claim, value, source_url (http/https), retrieved
    (YYYY-MM-DD) and measured_by in {"vendor", "third-party"}; anything else
    is rejected loudly rather than silently dropped — an uncited number must
    never reach a report.
    """
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        raise ValueError("reported.json must contain a JSON list of entries")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"reported entry must be an object: {entry!r}")
        for field in REQUIRED_REPORTED_FIELDS:
            if not str(entry.get(field, "")).strip():
                raise ValueError(f"reported entry missing {field!r}: {entry!r}")
        if entry["measured_by"] not in _REPORTED_BY:
            raise ValueError(
                f"reported entry measured_by must be one of {_REPORTED_BY}: {entry!r}"
            )
        if not entry["source_url"].startswith(("http://", "https://")):
            raise ValueError(f"reported entry source_url must be http(s): {entry!r}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["retrieved"]):
            raise ValueError(f"reported entry retrieved must be YYYY-MM-DD: {entry!r}")
    return entries


def render_reported(entries: List[Dict[str, str]]) -> str:
    """Vendor/third-party figures in their own separate section, cited and dated."""
    lines = ["## Reported by others — not reproduced here", "",
             "Vendor and third-party figures with source and retrieval date. "
             "These were never measured on our hardware and are never mixed with our own results.", ""]
    for entry in entries:
        lines.append(
            f"- **{entry['claim']}** — {entry['value']} "
            f"({entry['measured_by']}-reported, retrieved {entry['retrieved']}; "
            f"source: {entry['source_url']})"
        )
        if entry.get("note"):
            lines.append(f"  - note: {entry['note']}")
    return "\n".join(lines)
