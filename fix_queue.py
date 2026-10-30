"""Clean surgery queue: remove GGUF-only and gated repos."""
import json

with open("surgery_queue.json") as f:
    queue = json.load(f)

# Gated families (need HF auth)
gated = ["google/", "meta-llama/"]

# GGUF-only repos (no safetensors)
gguf_only = [t["name"] for t in queue if "GGUF" in t["name"] and "abliterated" in t["name"].lower()]

clean = []
skipped_gated = 0
skipped_gguf = 0
skipped_huge = 0

for t in queue:
    name = t["name"]
    
    # Skip gated
    if any(name.startswith(g) for g in gated):
        skipped_gated += 1
        continue
    
    # Skip GGUF-only repos
    if "GGUF" in name and ("abliterated" in name.lower() or "heretic" in name.lower()):
        skipped_gguf += 1
        continue
    
    # Skip huge models (>50B) for now
    if t["params_b"] > 50:
        skipped_huge += 1
        continue
    
    clean.append(t)

# Sort by depth
clean.sort(key=lambda x: (x["layers"], x["ablit_rating"]), reverse=True)

print(f"Total: {len(queue)}")
print(f"Skipped gated: {skipped_gated}")
print(f"Skipped GGUF-only: {skipped_gguf}")
print(f"Skipped huge (>50B): {skipped_huge}")
print(f"Clean targets: {len(clean)}")

# Already done
done = ["Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct"]
remaining = [t for t in clean if t["name"] not in done]
print(f"\nRemaining: {len(remaining)}")

print("\n=== Next 15 Targets ===")
for i, t in enumerate(remaining[:15]):
    print(f"{i+1:2d}. {t['name']:55s} {t['arch_type']:10s} {t['layers']:3d}L {t['params_b']:7.1f}B ablit={t['ablit_rating']}")

with open("surgery_queue_clean.json", "w") as f:
    json.dump(remaining, f, indent=2)
print(f"\nSaved to surgery_queue_clean.json")
