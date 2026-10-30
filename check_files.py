"""Check and fix broken extractor files."""
import os

for fname in ["multi_direction_extractor", "moe_extractor", "vit_extractor"]:
    path = os.path.join("src/mahoraga", fname + ".py")
    with open(path) as f:
        content = f.read()
    
    print(f"\n=== {fname} ===")
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "_sanitize_model_name" in line or "@dataclass" in line or line.startswith("class "):
            print(f"  L{i+1}: {line[:80]}")
