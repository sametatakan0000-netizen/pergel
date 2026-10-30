"""Batch Surgery 2 — Non-gated models only."""
import json
from src.mahoraga.real_surgery import RealSurgery

# Load queue
with open("surgery_queue.json") as f:
    queue = json.load(f)

# Skip gated families (google/*, meta-llama/*) — need auth
# Focus on open models: Qwen, Mistral, DeepSeek, etc.
gated_families = ["google/", "meta-llama/"]

open_targets = []
for t in queue:
    name = t["name"]
    if any(name.startswith(g) for g in gated_families):
        continue
    if t["params_b"] > 50:  # skip huge models for now
        continue
    if t["layers"] < 24:  # only deep models
        continue
    open_targets.append(name)

# Already done
done = ["Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct"]
open_targets = [t for t in open_targets if t not in done]

print(f"Open targets available: {len(open_targets)}")
for t in open_targets[:10]:
    print(f"  {t}")

# Take next 3
batch = open_targets[:3]
print(f"\nSurgery batch: {batch}")

surgery = RealSurgery(backup_dir="./synapse_backups", work_dir="./surgery_work")
results = surgery.batch_surgery(batch)

print("\n" + "="*60)
total = 0
for r in results:
    status = "✅" if r["status"] == "completed" else "❌"
    print(f"{status} {r['model']:45s} {r['synapses']:>15,} sinaps")
    total += r['synapses']
print(f"\n🔥 Batch total: {total:,} sinaps")
