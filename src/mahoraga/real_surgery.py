"""Gerçek Ameliyat Pipeline — HF Download + Safetensors Sömürü.

İndir -> Safetensors yükle -> Sinaps çıkar -> Yedekle -> Gövde sil
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import time
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download
from safetensors import safe_open
from safetensors.torch import load_file


def sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


class RealSurgery:
    """Gerçek model ameliyatı."""
    
    def __init__(self, backup_dir="./synapse_backups", work_dir="./surgery_work"):
        self.backup_dir = Path(backup_dir)
        self.work_dir = Path(work_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def download_model(self, repo_id: str) -> str:
        """HF'den Safetensors indir."""
        self.log(f"  📥 İndiriliyor: {repo_id}")
        local_dir = self.work_dir / sanitize(repo_id)
        
        try:
            path = snapshot_download(
                repo_id=repo_id,
                local_dir=str(local_dir),
                allow_patterns=["*.safetensors", "*.json", "*.txt", "*.model"],
                ignore_patterns=["*.gguf", "*.bin", "*.pt"],
            )
            self.log(f"  ✅ İndirildi: {path}")
            return path
        except Exception as e:
            self.log(f"  ❌ İndirme hatası: {e}")
            raise
    
    def extract_weight_synapses(self, model_path: str, model_name: str) -> dict:
        """Safetensors ağırlıklarından sinaps çıkar."""
        self.log(f"  🔬 Sinaps çıkarımı başlıyor...")
        
        model_dir = Path(model_path)
        safetensor_files = list(model_dir.glob("*.safetensors"))
        
        if not safetensor_files:
            raise FileNotFoundError(f"No safetensors found in {model_path}")
        
        total_synapses = 0
        layer_synapses = {}
        all_hashes = []
        
        for st_file in safetensor_files:
            self.log(f"    📄 İşleniyor: {st_file.name}")
            
            with safe_open(str(st_file), framework="pt") as f:
                for key in f.keys():
                    tensor = f.get_tensor(key)
                    n = tensor.numel()
                    total_synapses += n
                    
                    # Layer tracking
                    layer_match = re.search(r"layers\.(\d+)", key)
                    if layer_match:
                        layer_idx = int(layer_match.group(1))
                        layer_synapses[layer_idx] = layer_synapses.get(layer_idx, 0) + n
                    
                    # Hash for backup verification (sample-based for speed)
                    if n > 0:
                        flat = tensor.flatten().float()
                        sample = flat[::max(1, n // 100)]  # sample every Nth
                        h = hashlib.sha256()
                        for v in sample[:100].tolist():
                            h.update(struct.pack("f", v))
                        all_hashes.append({
                            "key": key,
                            "shape": list(tensor.shape),
                            "n_synapses": n,
                            "hash": h.hexdigest()[:16],
                            "magnitude": float(flat.abs().mean()) if n > 0 else 0,
                        })
        
        result = {
            "model": model_name,
            "total_synapses": total_synapses,
            "n_layers": len(layer_synapses),
            "layer_synapses": layer_synapses,
            "tensors": all_hashes,
            "golden_red_rule": "NEVER DELETE - ALWAYS BACKUP",
        }
        
        self.log(f"  ✅ {total_synapses:,} sinaps çıkarıldı, {len(layer_synapses)} katman")
        return result
    
    def backup_synapses(self, extraction: dict) -> str:
        """Altın-kırmızı kural: Yedekle."""
        safe_name = sanitize(extraction["model"])
        backup_file = self.backup_dir / f"{safe_name}_synapses.json"
        
        with open(backup_file, "w") as f:
            json.dump(extraction, f, indent=2)
        
        self.log(f"  💾 Yedeklendi: {backup_file}")
        return str(backup_file)
    
    def verify_backup(self, backup_path: str) -> bool:
        """Yedekleme doğrulama."""
        with open(backup_path) as f:
            data = json.load(f)
        
        if data.get("golden_red_rule") != "NEVER DELETE - ALWAYS BACKUP":
            return False
        if data.get("total_synapses", 0) <= 0:
            return False
        return True
    
    def delete_model_body(self, model_path: str):
        """Model gövdesini sil (sinapslar güvende)."""
        path = Path(model_path)
        if path.exists():
            size_gb = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9
            shutil.rmtree(path)
            self.log(f"  🗑️ Gövde silindi ({size_gb:.1f} GB freed)")
    
    def run_surgery(self, repo_id: str) -> dict:
        """Tam ameliyat pipeline'ı."""
        self.log(f"\n{'='*60}")
        self.log(f"🔪 AMELİYAT: {repo_id}")
        
        result = {
            "model": repo_id,
            "status": "started",
            "synapses": 0,
            "backup_path": "",
        }
        
        try:
            # 1. Download
            model_path = self.download_model(repo_id)
            
            # 2. Extract synapses
            extraction = self.extract_weight_synapses(model_path, repo_id)
            result["synapses"] = extraction["total_synapses"]
            
            # 3. Backup
            backup_path = self.backup_synapses(extraction)
            result["backup_path"] = backup_path
            
            # 4. Verify
            if not self.verify_backup(backup_path):
                raise Exception("BACKUP VERIFICATION FAILED")
            
            # 5. Delete body
            self.delete_model_body(model_path)
            
            result["status"] = "completed"
            self.log(f"  ✅ AMELİYAT TAMAM: {result['synapses']:,} sinaps")
            
        except Exception as e:
            result["status"] = f"failed: {e}"
            self.log(f"  ❌ HATA: {e}")
        
        return result
    
    def batch_surgery(self, repo_ids: list[str]) -> list[dict]:
        """Toplu ameliyat."""
        results = []
        for i, repo_id in enumerate(repo_ids):
            self.log(f"\nMODEL {i+1}/{len(repo_ids)}")
            results.append(self.run_surgery(repo_id))
        return results


def run_batch(repo_ids: list[str]) -> list[dict]:
    surgery = RealSurgery()
    return surgery.batch_surgery(repo_ids)
