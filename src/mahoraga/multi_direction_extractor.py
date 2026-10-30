"""Multi-Direction Abliteration — Tam Sömürü Modu.

Kullanıcının talebi: Benchmark bozması önemsiz (gövde silinecek).
Mümkün olduğunca çok yön çıkar → daha fazla sinaps.

Tek yönlü abliteration yerine: çoklu yön taraması yapar.
Her yön ayrı ayrı saklanır (altın-kırmızı kural).
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DirectionVector:
    """Çıkarılan bir yön vektörü."""
    direction_id: int
    layer_range: tuple[int, int]  # (start, end)
    magnitude: float
    n_dims: int
    separation_score: float  # iki yön arasındaki ayrım
    hash: str

@dataclass
class MultiDirectionResult:
    """Çoklu yön abliteration sonucu."""
    model_name: str
    n_directions: int
    directions: list[DirectionVector] = field(default_factory=list)
    total_synapses: int = 0
    benchmark_damage: float = 0.0  # önemsiz ama kaydediyoruz
    backup_path: str = ""


class MultiDirectionExtractor:
    """Çoklu yön abliteration — maksimum sinaps çıkarımı."""

    def __init__(self, backup_dir: str | Path):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def find_direction(
        self,
        helpful_activations: list[float],
        refusal_activations: list[float],
        layer_range: tuple[int, int],
        direction_id: int = 0,
    ) -> DirectionVector | None:
        """Tek bir yön vektörü bul (difference-of-means)."""
        if len(helpful_activations) != len(refusal_activations):
            return None

        n = len(helpful_activations)
        if n == 0:
            return None

        # Difference-of-means
        diff = [h - r for h, r in zip(helpful_activations, refusal_activations)]
        magnitude = sum(abs(d) for d in diff) / n

        # Separation score: yön ne kadar net ayrışıyor
        separation = sum(d * d for d in diff) / n

        # Hash for backup
        h = hashlib.sha256()
        for d in diff:
            h.update(struct.pack("f", d))

        return DirectionVector(
            direction_id=direction_id,
            layer_range=layer_range,
            magnitude=magnitude,
            n_dims=n,
            separation_score=separation,
            hash=h.hexdigest()[:16],
        )

    def multi_direction_scan(
        self,
        activations: dict[str, list[float]],
        layer_ranges: list[tuple[int, int]],
        n_directions: int = 5,
    ) -> list[DirectionVector]:
        """Çoklu yön taraması — birden fazla yön çıkar."""
        directions = []
        helpful = activations.get("helpful", [])
        refusal = activations.get("refusal", [])

        for i, lr in enumerate(layer_ranges):
            # Her katman aralığı için yön bul
            dir_vec = self.find_direction(helpful, refusal, lr, i)
            if dir_vec:
                directions.append(dir_vec)

            # Eğer yeterli yön yoksa, alt-katmanlarda ara
            if len(directions) < n_directions and len(layer_ranges) > 1:
                mid = (lr[0] + lr[1]) // 2
                for sub_lr in [(lr[0], mid), (mid, lr[1])]:
                    sub_dir = self.find_direction(helpful, refusal, sub_lr, len(directions))
                    if sub_dir and sub_dir.separation_score > 0.01:
                        directions.append(sub_dir)

        return directions[:n_directions]

    def backup_directions(self, result: MultiDirectionResult) -> str:
        """Altın-kırmızı kural: Tüm yönleri yedekle."""
        backup_file = self.backup_dir / f"{result.model_name}_multi_directions.json"
        data = {
            "model": result.model_name,
            "golden_red_rule": "NEVER DELETE - ALWAYS BACKUP",
            "n_directions": result.n_directions,
            "total_synapses": result.total_synapses,
            "benchmark_damage": result.benchmark_damage,
            "note": "Benchmark damage is EXPECTED and ACCEPTABLE - model body will be deleted",
            "directions": [
                {
                    "id": d.direction_id,
                    "layer_range": list(d.layer_range),
                    "magnitude": d.magnitude,
                    "n_dims": d.n_dims,
                    "separation": d.separation_score,
                    "hash": d.hash,
                }
                for d in result.directions
            ],
        }
        with open(backup_file, "w") as f:
            json.dump(data, f, indent=2)
        return str(backup_file)

    def full_extraction(
        self,
        model_name: str,
        activations: dict[str, list[float]],
        layer_ranges: list[tuple[int, int]],
        n_directions: int = 5,
    ) -> MultiDirectionResult:
        """Tam çoklu yön sömürü."""
        directions = self.multi_direction_scan(activations, layer_ranges, n_directions)

        result = MultiDirectionResult(
            model_name=model_name,
            n_directions=len(directions),
            directions=directions,
            total_synapses=sum(d.n_dims for d in directions),
        )

        # Yedekle (ALTIN-KIRMIZI KURAL)
        result.backup_path = self.backup_directions(result)

        return result


def extract_multi_directions(
    model_name: str,
    activations: dict[str, list[float]],
    layer_ranges: list[tuple[int, int]],
    n_directions: int = 5,
    backup_dir: str = "./synapse_backups",
) -> MultiDirectionResult:
    """Kolay API: Çoklu yön abliteration."""
    extractor = MultiDirectionExtractor(backup_dir)
    return extractor.full_extraction(model_name, activations, layer_ranges, n_directions)
