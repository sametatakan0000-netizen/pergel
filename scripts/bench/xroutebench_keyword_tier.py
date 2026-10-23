#!/usr/bin/env python3
"""Zero-cost offline eval: does our crude keyword tier (src.router.request_features) pick a
cheaper model than always-best WITHOUT losing quality, on xRouteBench precomputed responses?

Data: rows.json (task_name, query, model_name, performance, input_tokens, output_tokens), fetched
from HF ulab-ai/xRouteBench `llmrouter_generic` test split. No model is called.
# shortcut: maps keyword tier -> 3 price bands of xRouteBench's 18-model pool (not our Nous pool);
#   measures the *classifier*, not our model ranking. Upgrade: replay with the real registry.
"""
import json, sys, collections, statistics, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from src.router.request_features import keyword_tier

rows = json.load(open(sys.argv[1]))
by_q = collections.defaultdict(dict)       # (task,id) -> model -> perf
meta = {}
for r in rows:
    k = (r["task_name"], r["task_id"], r["query"])
    by_q[k][r["model_name"]] = float(r["performance"])
    meta[k] = r["query"]
models = sorted({m for d in by_q.values() for m in d})
mean = {m: statistics.mean(d[m] for d in by_q.values() if m in d) for m in models}
full = {k: d for k, d in by_q.items() if len(d) >= len(models) * 0.9}
oracle = statistics.mean(max(d.values()) for d in full.values())
best_fixed = max(mean, key=mean.get)
print(f"queries={len(full)} models={len(models)}")
print(f"best fixed model: {best_fixed} perf={mean[best_fixed]:.3f}")
print(f"oracle (per-query best): {oracle:.3f}")
# Rank models by global mean perf; tiers = terciles (t1 weakest .. t3 strongest)
order = sorted(models, key=mean.get)
third = max(1, len(order) // 3)
band = {1: order[:third], 2: order[third:2 * third], 3: order[2 * third:]}
res = collections.defaultdict(list)
for k, d in full.items():
    t = keyword_tier([{"role": "user", "content": meta[k]}])
    ms = [m for m in band[t] if m in d]
    if ms: res[t].append(statistics.mean(d[m] for m in ms))
for t in (1, 2, 3):
    if res[t]: print(f"keyword tier {t}: n={len(res[t])} mean perf of tier-{t} band={statistics.mean(res[t]):.3f}")
allp = [x for v in res.values() for x in v]
print(f"routed-by-keyword mean perf={statistics.mean(allp):.3f}  vs random-band baseline={statistics.mean(mean.values()):.3f}")
# per-task: how much headroom between strongest band and weakest band
tasks = collections.defaultdict(lambda: collections.defaultdict(list))
for k, d in full.items():
    for t in (1, 3):
        ms = [m for m in band[t] if m in d]
        if ms: tasks[k[0]][t].append(statistics.mean(d[m] for m in ms))
print("task | weak-band | strong-band | gap (gap≈0 ⇒ cheap model suffices)")
for task, v in sorted(tasks.items()):
    if v[1] and v[3]: print(f"{task:14s} {statistics.mean(v[1]):.3f} {statistics.mean(v[3]):.3f} {statistics.mean(v[3])-statistics.mean(v[1]):+.3f}")

# Classifier-only check (independent of band choice): is a query the keyword tier calls "hard"
# actually harder (lower mean perf across ALL models) than one it calls "easy"?
diff = collections.defaultdict(list)
for k, d in full.items():
    diff[keyword_tier([{"role": "user", "content": meta[k]}])].append(statistics.mean(d.values()))
print("difficulty by keyword tier (mean perf over all models; lower = harder):")
for t in sorted(diff): print(f"  tier {t}: n={len(diff[t])} mean={statistics.mean(diff[t]):.3f}")
