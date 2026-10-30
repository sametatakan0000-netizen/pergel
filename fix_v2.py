"""Fix: move _sanitize_model_name before @dataclass decorators."""
import os

for fname in ["multi_direction_extractor", "moe_extractor", "vit_extractor"]:
    path = os.path.join("src/mahoraga", fname + ".py")
    with open(path) as f:
        content = f.read()
    
    # Remove the misplaced function (between @dataclass and class)
    broken = """@dataclass
def _sanitize_model_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

class"""
    fixed_class = "class"
    content = content.replace(broken, fixed_class)
    
    # Also handle the version with double newline
    broken2 = """@dataclass
def _sanitize_model_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

"""
    content = content.replace(broken2, "")
    
    # Now add it properly BEFORE the first @dataclass
    helper = """def _sanitize_model_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)


"""
    if "_sanitize_model_name" not in content.split("@dataclass")[0]:
        content = content.replace("@dataclass", helper + "@dataclass", 1)
    
    with open(path, "w") as f:
        f.write(content)
    print(f"Fixed {fname}.py")

print("Done!")
