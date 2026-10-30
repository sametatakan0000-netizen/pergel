"""GECE BOYU OTONOM AMELİYAT — 90 model, tam sömürü.

Her model: indir -> safetensors çıkar -> yedekle -> gövde sil
Hata toleranslı: başarısız modeller atlanır, devam eder.
"""

import json
import time
import traceback
from pathlib import Path
from src.mahoraga.real_surgery import RealSurgery

PROGRESS_FILE = "surgery_progress.json"
QUEUE_FILE = "surgery_queue_clean.json"

def load_progress():
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "total_synapses": 0}

def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f, indent=2)

def main():
    with open(QUEUE_FILE) as f:
        queue = json.load(f)
    
    prog = load_progress()
    done_names = set(prog["completed"] + prog["failed"])
    remaining = [t for t in queue if t["name"] not in done_names]
    
    print(f"Queue: {len(queue)} | Done: {len(prog['completed'])} | Failed: {len(prog['failed'])} | Remaining: {len(remaining)}")
    print(f"Total synapses so far: {prog['total_synapses']:,}")
    print(f"\nStarting autonomous surgery...\n")
    
    surgery = RealSurgery(backup_dir="./synapse_backups", work_dir="./surgery_work")
    
    for i, target in enumerate(remaining):
        name = target["name"]
        print(f"\n[{i+1}/{len(remaining)}] {name} ({target['layers']}L, {target['params_b']}B)")
        
        try:
            result = surgery.run_surgery(name)
            
            if result["status"] == "completed":
                prog["completed"].append(name)
                prog["total_synapses"] += result["synapses"]
                print(f"  ✅ {result['synapses']:,} sinaps | Total: {prog['total_synapses']:,}")
            else:
                prog["failed"].append(name)
                print(f"  ❌ {result['status']}")
                
        except Exception as e:
            prog["failed"].append(name)
            print(f"  ❌ Exception: {e}")
            traceback.print_exc()
        
        save_progress(prog)
    
    print(f"\n{'='*60}")
    print(f"GECE AMELİYATI TAMAMLANDI")
    print(f"  Completed: {len(prog['completed'])}")
    print(f"  Failed: {len(prog['failed'])}")
    print(f"  TOTAL SYNAPSES: {prog['total_synapses']:,}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
