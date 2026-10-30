"""Vision Transformer (ViT) Sinaps Çıkarıcı.

Görsel modellerin hem "göz" (Vision Encoder) hem "beyin" (LLM) 
sinapslarını çıkarır. Cross-attention sinapsları dahil.

Altın-kırmızı kural: Çıkarılan her sinaps kalıcı olarak saklanır.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PatchEmbedding:
    """Görsel patch embedding sinapsları."""
    patch_idx: int
    dim: int
    n_synapses: int
    magnitude: float
    hash: str

@dataclass
class CrossAttentionSynapse:
    """Vision-Language cross-attention sinapsları."""
    layer_idx: int
    head_idx: int
    direction: str  # "vision_to_text" or "text_to_vision"
    n_synapses: int
    magnitude: float
    hash: str

@dataclass
class VisionExtractionResult:
    """Tam Vision sömürü sonucu."""
    model_name: str
    encoder_type: str  # "ViT", "CNN", "SigLIP" vb.
    patch_embeddings: list[PatchEmbedding] = field(default_factory=list)
    cross_attention: list[CrossAttentionSynapse] = field(default_factory=list)
    llm_synapses: int = 0  # beyin tarafı
    vision_synapses: int = 0  # göz tarafı
    total_synapses: int = 0
    backup_path: str = ""


class VisionSynapseExtractor:
    """Vision modellerden göz + beyin sinaps çıkarıcı."""

    def __init__(self, backup_dir: str | Path):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def extract_patch_embeddings(
        self, patches: list[list[float]], encoder_type: str = "ViT"
    ) -> list[PatchEmbedding]:
        """Görsel patch embedding'lerini çıkar."""
        result = []
        for idx, patch_weights in enumerate(patches):
            n = len(patch_weights)
            magnitude = sum(abs(w) for w in patch_weights) / max(n, 1)
            h = hashlib.sha256()
            for w in patch_weights:
                h.update(struct.pack("f", w))
            result.append(PatchEmbedding(
                patch_idx=idx, dim=n, n_synapses=n,
                magnitude=magnitude, hash=h.hexdigest()[:16],
            ))
        return result

    def extract_cross_attention(
        self,
        attn_weights: list[list[float]],
        layer_idx: int,
        direction: str = "vision_to_text",
    ) -> list[CrossAttentionSynapse]:
        """Cross-attention sinapslarını çıkar."""
        result = []
        for head_idx, head_weights in enumerate(attn_weights):
            n = len(head_weights)
            magnitude = sum(abs(w) for w in head_weights) / max(n, 1)
            h = hashlib.sha256()
            for w in head_weights:
                h.update(struct.pack("f", w))
            result.append(CrossAttentionSynapse(
                layer_idx=layer_idx, head_idx=head_idx,
                direction=direction, n_synapses=n,
                magnitude=magnitude, hash=h.hexdigest()[:16],
            ))
        return result

    def backup_synapses(self, result: VisionExtractionResult) -> str:
        """Altın-kırmızı kural: Tüm sinapsları yedekle."""
        backup_file = self.backup_dir / f"{result.model_name}_vision_synapses.json"
        data = {
            "model": result.model_name,
            "golden_red_rule": "NEVER DELETE - ALWAYS BACKUP",
            "encoder_type": result.encoder_type,
            "total_synapses": result.total_synapses,
            "patch_embeddings": [
                {"idx": p.patch_idx, "dim": p.dim, "n_synapses": p.n_synapses,
                 "magnitude": p.magnitude, "hash": p.hash}
                for p in result.patch_embeddings
            ],
            "cross_attention": [
                {"layer": c.layer_idx, "head": c.head_idx, "direction": c.direction,
                 "n_synapses": c.n_synapses, "magnitude": c.magnitude, "hash": c.hash}
                for c in result.cross_attention
            ],
        }
        with open(backup_file, "w") as f:
            json.dump(data, f, indent=2)
        return str(backup_file)

    def full_extraction(
        self,
        model_name: str,
        encoder_type: str,
        patches: list[list[float]],
        cross_attn_layers: list[dict[str, Any]],
        llm_synapse_count: int = 0,
    ) -> VisionExtractionResult:
        """Tam Vision sömürü: göz + cross-attention + beyin."""
        result = VisionExtractionResult(
            model_name=model_name,
            encoder_type=encoder_type,
            llm_synapses=llm_synapse_count,
        )

        # Patch embeddings (göz)
        result.patch_embeddings = self.extract_patch_embeddings(patches, encoder_type)
        result.vision_synapses = sum(p.n_synapses for p in result.patch_embeddings)

        # Cross-attention (göz-beyin köprüsü)
        for layer in cross_attn_layers:
            layer_idx = layer.get("idx", 0)
            attn = layer.get("weights", [])
            direction = layer.get("direction", "vision_to_text")
            result.cross_attention.extend(
                self.extract_cross_attention(attn, layer_idx, direction)
            )
            result.vision_synapses += sum(c.n_synapses for c in result.cross_attention if c.layer_idx == layer_idx)

        result.total_synapses = result.vision_synapses + result.llm_synapses

        # Yedekle (ALTIN-KIRMIZI KURAL)
        result.backup_path = self.backup_synapses(result)

        return result


def extract_vision_synapses(
    model_name: str,
    encoder_type: str,
    patches: list[list[float]],
    cross_attn_layers: list[dict],
    llm_synapse_count: int = 0,
    backup_dir: str = "./synapse_backups",
) -> VisionExtractionResult:
    """Kolay API: Vision modelden tam sinaps çıkarımı."""
    extractor = VisionSynapseExtractor(backup_dir)
    return extractor.full_extraction(model_name, encoder_type, patches, cross_attn_layers, llm_synapse_count)
