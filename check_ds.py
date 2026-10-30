import json

with open("/home/pc/.hermes/cache/scratch/master_datasheet.json") as f:
    data = json.load(f)

print(f"Type: {type(data)}")
if isinstance(data, dict):
    print(f"Keys: {list(data.keys())[:10]}")
    for k in list(data.keys())[:3]:
        v = data[k]
        print(f"  {k}: {type(v).__name__}")
        if isinstance(v, list):
            print(f"    len={len(v)}, first={type(v[0]).__name__ if v else 'empty'}")
            if v and isinstance(v[0], dict):
                print(f"    first keys: {list(v[0].keys())[:10]}")
        elif isinstance(v, dict):
            print(f"    keys: {list(v.keys())[:10]}")
elif isinstance(data, list):
    print(f"Length: {len(data)}")
    if data:
        print(f"First item type: {type(data[0]).__name__}")
        if isinstance(data[0], dict):
            print(f"First item keys: {list(data[0].keys())[:15]}")
