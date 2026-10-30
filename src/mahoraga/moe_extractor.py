"""MoE (Mixture of Experts) Uzman-Seçici Sinaps Çıkarıcı.

Her uzman (expert) alt-ağını ayrı ayrı tarar, router analiz eder,
ve her uzmanın sinapslarını tek tek çıkarır + yedekler.

Altın-kırmızı kural: Çıkarılan her sinaps kalıcı olarak saklanır.
"""

from __future__ import annotations

import hashlib
import re
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExpertSynapse:
    """Tek bir uzmanın sinaps kümesi."""
    expert_id: int
    layer_idx: int
    n_synapses: int
    direction: str  # "refusal" or "helpful"
    magnitude: float
    hash: str  # yedekleme için

def _sanitize_model_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)


@dataclass  
class RouterProfile:
    """Router analiz sonucu."""
    layer_idx: int
    n_experts: int
    top_k: int
    expert_usage: dict[int, float]  # expert_id -> kullanım oranı
    refusal_experts: list[int]  # reddetme uzmanları
    helpful_experts: list[int]  # yardımcı uzmanlar

@dataclass
class MoEExtractionResult:
    """Tam MoE sömürü sonucu."""
    model_name: str
    total_experts: int
    total_layers: int
    expert_synapses: list[ExpertSynapse] = field(default_factory=list)
    router_profiles: list[RouterProfile] = field(default_factory=list)
    total_synapses: int = 0
    backup_path: str = ""


class MoEExpertExtractor:
    """MoE modellerden uzman-seçici sinaps çıkarıcı."""

    def __init__(self, backup_dir: str | Path):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def analyze_router(self, router_weights: list[list[float]], layer_idx: int) -> RouterProfile:
        """Router ağırlıklarını analiz et."""
        n_experts = len(router_weights)
        if n_experts == 0:
            return RouterProfile(layer_idx=layer_idx, n_experts=0, top_k=0,
                               expert_usage={}, refusal_experts=[], helpful_experts=[])

        # Her uzmanın ortalama aktivasyon gücünü hesapla
        expert_usage = {}
        for eid, weights in enumerate(router_weights):
            expert_usage[eid] = sum(abs(w) for w in weights) / max(len(weights), 1)

        # Top-k belirle (en çok kullanılan uzmanlar)
        sorted_experts = sorted(expert_usage.items(), key=lambda x: x[1], reverse=True)
        top_k = min(4, n_experts)  # varsayılan top-4

        # Reddetme vs yardımcı sınıflandırma
        # Yüksek negatif ağırlık = reddetme yönü
        # Yüksek pozitif ağırlık = yardımcı yön
        refusal_experts = []
        helpful_experts = []
        for eid, weights in enumerate(router_weights):
            avg = sum(weights) / max(len(weights), 1)
            if avg < -0.1:
                refusal_experts.append(eid)
            elif avg > 0.1:
                helpful_experts.append(eid)

        return RouterProfile(
            layer_idx=layer_idx, n_experts=n_experts, top_k=top_k,
            expert_usage=expert_usage,
            refusal_experts=refusal_experts,
            helpful_experts=helpful_experts,
        )

    def extract_expert_synapses(
        self,
        expert_weights: list[float],
        expert_id: int,
        layer_idx: int,
        direction: str = "helpful",
    ) -> ExpertSynapse:
        """Tek bir uzmandan sinaps çıkar."""
        n_synapses = len(expert_weights)
        magnitude = sum(abs(w) for w in expert_weights) / max(n_synapses, 1)

        # Hash for backup verification
        h = hashlib.sha256()
        for w in expert_weights:
            h.update(struct.pack("f", w))
        synapse_hash = h.hexdigest()[:16]

        return ExpertSynapse(
            expert_id=expert_id,
            layer_idx=layer_idx,
            n_synapses=n_synapses,
            direction=direction,
            magnitude=magnitude,
            hash=synapse_hash,
        )

    def backup_synapses(self, synapses: list[ExpertSynapse], model_name: str) -> str:
        """Altın-kırmızı kural: Tüm sinapsları yedekle."""
        backup_file = self.backup_dir / f"{_sanitize_model_name(model_name)}_moe_synapses.json"
        data = {
            "model": model_name,
            "golden_red_rule": "NEVER DELETE - ALWAYS BACKUP",
            "total_synapses": len(synapses),
            "experts": [
                {
                    "expert_id": s.expert_id,
                    "layer_idx": s.layer_idx,
                    "n_synapses": s.n_synapses,
                    "direction": s.direction,
                    "magnitude": s.magnitude,
                    "hash": s.hash,
                }
                for s in synapses
            ],
        }
        with open(backup_file, "w") as f:
            json.dump(data, f, indent=2)
        return str(backup_file)

    def full_extraction(
        self,
        model_name: str,
        layers: list[dict[str, Any]],
    ) -> MoEExtractionResult:
        """Tam MoE sömürü: tüm katmanlar, tüm uzmanlar."""
        result = MoEExtractionResult(
            model_name=model_name,
            total_experts=0,
            total_layers=len(layers),
        )

        all_synapses = []

        for layer in layers:
            layer_idx = layer.get("idx", 0)
            experts = layer.get("experts", [])
            router = layer.get("router_weights", [])

            # Router analizi
            if router:
                rp = self.analyze_router(router, layer_idx)
                result.router_profiles.append(rp)

            # Her uzmandan sinaps çıkar
            for eid, expert_weights in enumerate(experts):
                direction = "refusal" if eid in (result.router_profiles[-1].refusal_experts if result.router_profiles else []) else "helpful"
                syn = self.extract_expert_synapses(expert_weights, eid, layer_idx, direction)
                result.expert_synapses.append(syn)
                all_synapses.append(syn)

            result.total_experts += len(experts)

        result.total_synapses = sum(s.n_synapses for s in all_synapses)

        # Yedekle (ALTIN-KIRMIZI KURAL)
        result.backup_path = self.backup_synapses(all_synapses, model_name)

        return result


def extract_moe_synapses(model_name: str, layers: list[dict], backup_dir: str) -> MoEExtractionResult:
    """Kolay API: MoE modelden tam sinaps çıkarımı."""
    extractor = MoEExpertExtractor(backup_dir)
    return extractor.full_extraction(model_name, layers)
