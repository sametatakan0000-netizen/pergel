import json

with open("/home/pc/.hermes/cache/scratch/master_datasheet.json") as f:
    data = json.load(f)

models = data["models"]
# Find which models have arch as str vs dict
for i, m in enumerate(models[:20]):
    arch = m.get("arch", {})
    atype = type(arch).__name__
    if atype == "str":
        print(f"  [{i}] STR: {m['name']}: {arch[:100]}")
    else:
        print(f"  [{i}] DICT: {m['name']}: layers={arch.get('layers','?')} hidden={arch.get('hidden_dim','?')}")

# Count
str_count = sum(1 for m in models if isinstance(m.get("arch"), str))
dict_count = sum(1 for m in models if isinstance(m.get("arch"), dict))
print(f"\nArch as str: {str_count}, dict: {dict_count}")
