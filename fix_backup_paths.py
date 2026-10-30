"""Fix backup path sanitization in all extractors."""
import re
import os

for mod_name in ["multi_direction_extractor", "moe_extractor", "vit_extractor"]:
    path = os.path.join("src/mahoraga", mod_name + ".py")
    with open(path) as f:
        content = f.read()
    
    if "_sanitize_model_name" not in content:
        # Add import
        content = content.replace("import hashlib", "import hashlib\nimport re")
        
        # Add helper function before first class
        helper = "def _sanitize_model_name(name: str) -> str:\n    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)\n\n"
        content = content.replace("class ", helper + "class ", 1)
        
        # Fix backup paths
        content = content.replace(
            'f"{model_name}_',
            'f"{_sanitize_model_name(model_name)}_'
        )
        content = content.replace(
            'f"{result.model_name}_',
            'f"{_sanitize_model_name(result.model_name)}_'
        )
        
        with open(path, "w") as f:
            f.write(content)
        print(f"Fixed {mod_name}.py")
    else:
        print(f"{mod_name}.py already fixed")

print("Done!")
