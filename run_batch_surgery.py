"""Batch Real Surgery — Next Priority Models."""
from src.mahoraga.real_surgery import RealSurgery

surgery = RealSurgery(backup_dir="./synapse_backups", work_dir="./surgery_work")

# Priority batch: medium-size, deep, high-abliteration
targets = [
    "Qwen/Qwen2.5-7B-Instruct",       # 28L, 7.6B
    "google/gemma-2-9b-it",           # 42L, 9.2B
    "google/gemma-3-12b-it",          # 48L, 12.2B
]

results = surgery.batch_surgery(targets)

print("\n" + "="*60)
print("TOPLU AMELİYAT SONUÇLARI")
print("="*60)
total = 0
for r in results:
    status = "✅" if r["status"] == "completed" else "❌"
    print(f"{status} {r['model']:45s} {r['synapses']:>15,} sinaps  {r['status']}")
    total += r['synapses']

print(f"\n🔥 TOPLAM: {total:,} sinaps çıkarıldı")
