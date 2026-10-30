import json

with open("/home/pc/.hermes/cache/scratch/master_datasheet.json") as f:
    data = json.load(f)

models = data["models"]
m = models[0]
print("Sample model:")
for k, v in m.items():
    print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")

print(f"\nSecond model:")
m2 = models[1]
for k, v in m2.items():
    print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")
