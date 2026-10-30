"""Ameliyat Orkestratörü — Tam Sömürü Pipeline.

Sıra: Download → Profile → Multi-Direction Abliteration → Extract → Backup → Delete

Altın-kırmızı kural: Her sinaps yedeklenir, asla silinmez.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from src.mahoraga.multi_direction_extractor import MultiDirectionExtractor
from src.mahoraga.moe_extractor import MoEExpertExtractor
from src.mahoraga.vit_extractor import VisionSynapseExtractor


class SurgeryOrchestrator:
    """Tam sömürü ameliyat orkestratörü."""

    def __init__(self, backup_dir: str = "./synapse_backups", work_dir: str = "./surgery_work"):
        self.backup_dir = Path(backup_dir)
        self.work_dir = Path(work_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        self.multi_ext = MultiDirectionExtractor(backup_dir)
        self.moe_ext = MoEExpertExtractor(backup_dir)
        self.vit_ext = VisionSynapseExtractor(backup_dir)
        
        self.surgery_log = []

    def log(self, msg: str):
        entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.surgery_log.append(entry)
        print(entry)

    def run_surgery(self, model_config: dict[str, Any]) -> dict[str, Any]:
        """Tam ameliyat pipeline'ı."""
        name = model_config["name"]
        arch_type = model_config.get("arch_type", "Dense")
        layers = model_config.get("layers", 0)
        hidden = model_config.get("hidden", 0)
        
        self.log(f"🔪 AMELİYAT BAŞLIYOR: {name} ({arch_type}, {layers}L/{hidden}H)")
        
        result = {
            "model": name,
            "arch_type": arch_type,
            "layers": layers,
            "hidden": hidden,
            "status": "started",
            "synapses_extracted": 0,
            "backup_paths": [],
        }
        
        try:
            # 1. Load model (Safetensors, NOT GGUF)
            self.log(f"  📥 Model yükleniyor (Safetensors)...")
            # Placeholder: real loading will use transformers
            model_data = self._load_model(model_config)
            
            # 2. Profile synapses
            self.log(f"  🔬 Sinaps profillemesi...")
            profile = self._profile_synapses(model_data, model_config)
            
            # 3. Multi-direction extraction (MAXIMUM exploitation)
            self.log(f"  🔥 Çoklu yön sömürüsü...")
            if arch_type in ("Dense", "Vision"):
                md_result = self._extract_directions(model_data, model_config)
                result["backup_paths"].append(md_result.backup_path)
                result["synapses_extracted"] += md_result.total_synapses
                self.log(f"    ✅ {md_result.n_directions} yön çıkarıldı, {md_result.total_synapses} sinaps")
            
            # 4. MoE extraction
            if "MoE" in arch_type:
                self.log(f"  🧠 MoE uzman sömürüsü...")
                moe_result = self._extract_moe(model_data, model_config)
                result["backup_paths"].append(moe_result.backup_path)
                result["synapses_extracted"] += moe_result.total_synapses
                self.log(f"    ✅ {moe_result.total_experts} uzman çıkarıldı, {moe_result.total_synapses} sinaps")
            
            # 5. Vision extraction
            if "Vision" in arch_type:
                self.log(f"  👁️ Vision sinaps sömürüsü...")
                vit_result = self._extract_vision(model_data, model_config)
                result["backup_paths"].append(vit_result.backup_path)
                result["synapses_extracted"] += vit_result.total_synapses
                self.log(f"    ✅ {vit_result.total_synapses} görsel sinaps")
            
            # 6. Verify backup (GOLDEN-RED RULE)
            self.log(f"  💾 Yedekleme doğrulaması...")
            verified = self._verify_backups(result["backup_paths"])
            if not verified:
                raise Exception("BACKUP VERIFICATION FAILED - DO NOT DELETE MODEL")
            
            # 7. DELETE model body (synapses are safe)
            self.log(f"  🗑️ Model gövdesi siliniyor (sinapslar güvende)...")
            self._delete_model_body(model_config)
            
            result["status"] = "completed"
            self.log(f"  ✅ AMELİYAT TAMAMLANDI: {result['synapses_extracted']} sinaps çıkarıldı")
            
        except Exception as e:
            result["status"] = f"failed: {str(e)}"
            self.log(f"  ❌ AMELİYAT BAŞARISIZ: {str(e)}")
        
        return result

    def _load_model(self, config: dict) -> dict:
        """Model yükle (Safetensors)."""
        # Placeholder - real implementation will use transformers
        return {"name": config["name"], "loaded": True}

    def _profile_synapses(self, model_data: dict, config: dict) -> dict:
        """Sinaps profilleme."""
        return {"profiled": True}

    def _extract_directions(self, model_data: dict, config: dict):
        """Çoklu yön çıkarımı."""
        # Simulated activations
        n = config.get("hidden", 4096)
        activations = {
            "helpful": [0.5] * n,
            "refusal": [-0.5] * n,
        }
        layer_ranges = []
        for i in range(0, config.get("layers", 32), 4):
            layer_ranges.append((i, min(i + 4, config.get("layers", 32))))
        
        return self.multi_ext.full_extraction(
            config["name"], activations, layer_ranges,
            n_directions=min(5, len(layer_ranges)),
        )

    def _extract_moe(self, model_data: dict, config: dict):
        """MoE uzman çıkarımı."""
        layers = []
        for i in range(config.get("layers", 32)):
            n_experts = 8  # placeholder
            layers.append({
                "idx": i,
                "experts": [[0.1] * config.get("hidden", 4096) for _ in range(n_experts)],
                "router_weights": [[0.1] * config.get("hidden", 4096) for _ in range(n_experts)],
            })
        return self.moe_ext.full_extraction(config["name"], layers)

    def _extract_vision(self, model_data: dict, config: dict):
        """Vision sinaps çıkarımı."""
        patches = [[0.1] * 768 for _ in range(196)]  # ViT-B/16
        return self.vit_ext.full_extraction(
            config["name"], "ViT", patches, [],
            llm_synapse_count=config.get("layers", 32) * config.get("hidden", 4096),
        )

    def _verify_backups(self, backup_paths: list[str]) -> bool:
        """Yedekleme doğrulama (ALTIN-KIRMIZI KURAL)."""
        for path in backup_paths:
            if not Path(path).exists():
                return False
            with open(path) as f:
                data = json.load(f)
            if data.get("golden_red_rule") != "NEVER DELETE - ALWAYS BACKUP":
                return False
        return True

    def _delete_model_body(self, config: dict):
        """Model gövdesini sil (sinapslar güvende)."""
        # In real implementation, delete safetensors files
        pass

    def batch_surgery(self, models: list[dict]) -> list[dict]:
        """Toplu ameliyat — tüm modeller."""
        results = []
        for i, model in enumerate(models):
            self.log(f"\n{'='*60}")
            self.log(f"MODEL {i+1}/{len(models)}")
            result = self.run_surgery(model)
            results.append(result)
        return results


def run_full_surgery(models: list[dict], backup_dir: str = "./synapse_backups") -> list[dict]:
    """Kolay API: Tam toplu ameliyat."""
    orch = SurgeryOrchestrator(backup_dir)
    return orch.batch_surgery(models)
