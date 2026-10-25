#!/usr/bin/env python3
"""context_cost_guard: daily context/cost hygiene for the oracle router. No model calls.

- 24h spend by model vs. target budget (ROUTER_DAILY_BUDGET_USD, default $3).
- Reads live_router.db directly (free); prints a compact report and one-line verdicts.
- Verdicts: ok | ACTION:<what to tighten>. This script never changes router.env itself
  (context/cost dials are operator decisions), it only reports the dial to turn.
"""
import argparse
import json
import os
import sqlite3
import time

DB = os.path.expanduser("~/.local/share/oracle-router/data/live_router.db")
REG = os.path.expanduser("~/.local/share/oracle-router/data/model_registry.json")


def profiles():
    try:
        return json.load(open(REG)).get("profiles", {})
    except Exception:
        return {}


def price(p):
    ci = p.get("portal_cost_in") or p.get("list_cost_in") or 0
    co = p.get("portal_cost_out") or p.get("list_cost_out") or 0
    cr = p.get("list_cost_cache_read", ci)
    return ci, co, cr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--budget", type=float,
                    default=float(os.environ.get("ROUTER_DAILY_BUDGET_USD", "3")))
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    load = os.getloadavg()[0]
    if not args.force and load > 4.0:
        print(f"refusing: 1-min load {load} > 4.0 (use --force)")
        return 0

    prof = profiles()
    now = time.time()
    con = sqlite3.connect(args.db, timeout=10)
    rows = list(con.execute(
        "select model_id,coalesce(prompt_tokens,0),coalesce(completion_tokens,0),"
        "coalesce(cached_tokens,0) from upstream_events "
        "where status=200 and ts>?", (now - args.hours * 3600,)))

    by = {}
    total = 0.0
    max_prompt = 0
    for m, pt, ct, ca in rows:
        ci, co, cr = price(prof.get(m, {}))
        cost = ((pt - ca) * ci + ca * cr + ct * co) / 1e6
        s = by.setdefault(m, {"n": 0, "cost": 0.0, "prompt": 0, "cached": 0})
        s["n"] += 1
        s["cost"] += cost
        s["prompt"] += pt
        s["cached"] += ca
        total += cost
        max_prompt = max(max_prompt, pt)

    print(f"# context_cost_guard {time.strftime('%F %T')}  window={args.hours}h")
    print(f"total_est_usd={total:.2f} budget={args.budget} max_prompt={max_prompt}")
    for m, s in sorted(by.items(), key=lambda kv: -kv[1]["cost"]):
        share = s["cost"] / total * 100 if total else 0
        print(f"  {m:36s} n={s['n']:4d} est=${s['cost']:7.2f} ({share:4.1f}%) "
              f"cache={s['cached'] * 100 // max(s['prompt'], 1)}%")

    if total > args.budget:
        top = max(by.items(), key=lambda kv: kv[1]["cost"])[0]
        print(f"ACTION: 24h spend ${total:.2f} > ${args.budget}. "
              f"Tighten ORACLE_TURN_BUDGET_USD in ~/.config/oracle-router/router.env; "
              f"top burner: {top}")
    elif max_prompt > 80000:
        print("ACTION: prompt peak >80K — lower ORACLE_EFFECTIVE_CONTEXT "
              "(compression trigger = 50% of advertised window).")
    else:
        print("ok: spend and context within budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
