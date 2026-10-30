import json

with open("/home/pc/.hermes/cache/scratch/master_datasheet.json") as f:
    data = json.load(f)

models = data["models"]

# Find a model with string arch
for m in models:
    if isinstance(m.get("arch"), str):
        print(f"Model: {m['name']}")
        for k, v in m.items():
            if k == "arch":
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {str(v)[:120]}")
        break

# Also find one from a different family
for m in models:
    if isinstance(m.get("arch"), str) and "Llama" in m.get("name", ""):
        print(f"\nModel: {m['name']}")
        for k, v in m.items():
            if k == "arch":
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {str(v)[:120]}")
        break
