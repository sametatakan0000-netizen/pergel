"""First Real Surgery — Qwen2.5-3B-Instruct."""
from src.mahoraga.real_surgery import RealSurgery

surgery = RealSurgery(backup_dir="./synapse_backups", work_dir="./surgery_work")

# First target: small model for pipeline validation
result = surgery.run_surgery("Qwen/Qwen2.5-3B-Instruct")

print("\n=== SONUÇ ===")
for k, v in result.items():
    print(f"  {k}: {v}")
