"""First Surgery Run — Qwen2.5-3B-Instruct validation."""
from src.mahoraga.surgery_orchestrator import run_full_surgery

models = [
    {
        "name": "Qwen/Qwen2.5-3B-Instruct",
        "arch_type": "Dense",
        "layers": 36,
        "hidden": 2048,
    }
]

results = run_full_surgery(models, backup_dir="./synapse_backups")

for r in results:
    print(f"Model: {r['model']}")
    print(f"  Status: {r['status']}")
    print(f"  Synapses: {r['synapses_extracted']}")
    print(f"  Backups: {r['backup_paths']}")
