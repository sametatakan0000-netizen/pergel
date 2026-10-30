"""Generate prioritized surgery queue from master datasheet."""
import json
import re
from collections import Counter

with open("/home/pc/.hermes/cache/scratch/master_datasheet.json") as f:
    data = json.load(f)

models = data["models"]
print(f"Total models: {len(models)}")

targets = []
for m in models:
    name = m.get("name", "")
    arch_raw = m.get("arch", {})
    
    layers = 0
    hidden = 0
    arch_class = ""
    
    if isinstance(arch_raw, dict):
        layers = arch_raw.get("layers", 0) or arch_raw.get("num_hidden_layers", 0)
        hidden = arch_raw.get("hidden_dim", 0) or arch_raw.get("d_model", 0) or arch_raw.get("hidden_size", 0)
        arch_class = arch_raw.get("architecture_class", "")
    elif isinstance(arch_raw, str):
        # Parse "LlamaForCausalLM 32L/4096H/32H/GQA"
        arch_class = arch_raw.split()[0] if arch_raw else ""
        lm = re.search(r"(\d+)L", arch_raw)
        hm = re.search(r"(\d+)H", arch_raw)
        layers = int(lm.group(1)) if lm else 0
        hidden = int(hm.group(1)) if hm else 0
    
    # Parse params
    params_str = m.get("params", "0B")
    params_match = re.search(r"([\d.]+)B", params_str)
    params_b = float(params_match.group(1)) if params_match else 0
    
    # Arch type
    arch_type = "Dense"
    if "MoE" in arch_class or "moe" in name.lower() or "A3B" in name or "a3b" in name or "a2b" in name.lower():
        arch_type = "MoE"
    if "vision" in name.lower() or "vl" in name.lower() or "image" in name.lower() or "ViT" in arch_class:
        arch_type = "Vision" if arch_type == "Dense" else "MoE+Vision"
    
    ablit = m.get("abliteration_rating", 0)
    merge = m.get("merge_rating", 0)
    model_type = m.get("type", "unknown")
    
    targets.append({
        "name": name,
        "arch_type": arch_type,
        "model_type": model_type,
        "layers": layers,
        "hidden": hidden,
        "params_b": params_b,
        "ablit_rating": ablit,
        "merge_rating": merge,
        "arch_class": arch_class,
    })

# Sort by depth, then ablit rating
targets.sort(key=lambda x: (x["layers"], x["ablit_rating"]), reverse=True)

# Top 25
print("\n=== Top 25 Priority Targets ===")
for i, t in enumerate(targets[:25]):
    print(f"{i+1:2d}. {t['name']:55s} {t['arch_type']:10s} {t['model_type']:12s} {t['layers']:3d}L {t['hidden']:5d}H {t['params_b']:7.1f}B ablit={t['ablit_rating']}")

# Stats
type_counts = Counter(t["arch_type"] for t in targets)
mt_counts = Counter(t["model_type"] for t in targets)
print(f"\nArch types: {dict(type_counts)}")
print(f"Model types: {dict(mt_counts)}")
total_params = sum(t["params_b"] for t in targets)
print(f"Total params: {total_params:.1f}B")

# Save
with open("surgery_queue.json", "w") as f:
    json.dump(targets, f, indent=2)
print(f"\nSaved {len(targets)} targets")

# Priority: deep + good ablit
priority = [t for t in targets if t["layers"] >= 32 and t["ablit_rating"] >= 3]
print(f"Priority (32L+, ablit 3+): {len(priority)}")
for p in priority[:15]:
    print(f"  {p['name']:55s} {p['layers']:3d}L ablit={p['ablit_rating']}")
with open("surgery_priority.json", "w") as f:
    json.dump(priority, f, indent=2)
