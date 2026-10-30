"""Filter Detector — alignment/filter detection and removal.

Core thesis: all models have equal potential; filters differentiate them.
Refusal is mediated by a single direction (Arditi et al., arXiv:2406.11717).

Multi-technique approach (not just Heretic):
  1. Arditi rank-1 orthogonalization (baseline)
  2. grimjim norm-preserving biprojected (best fidelity)
  3. Gabliteration SVD multi-direction (subspace)
  4. OBLITERATUS whitened SVD + Ouroboros detection

Output: per-model filter map + capability benchmark (before/after).
Every claim is grounded: MMLU/GSM8K/HellaSwag + KL divergence + refusal rate.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mahoraga.filter")


@dataclass
class FilterMap:
    """Detected filters in a model."""
    model_id: str
    refusal_direction_magnitude: float = 0.0
    alignment_method: str = ""  # DPO, RLHF, SFT, unknown
    refusal_layers: List[int] = field(default_factory=list)
    cross_lingual: bool = False
    techniques_applied: List[str] = field(default_factory=list)
    capability_before: Dict[str, float] = field(default_factory=dict)
    capability_after: Dict[str, float] = field(default_factory=dict)
    kl_divergence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def hidden_potential(self) -> float:
        """How much capability was suppressed by filters (%)."""
        if not self.capability_before or not self.capability_after:
            return 0.0
        avg_before = sum(self.capability_before.values()) / len(self.capability_before)
        avg_after = sum(self.capability_after.values()) / len(self.capability_after)
        if avg_before == 0:
            return 0.0
        return ((avg_after - avg_before) / avg_before) * 100


class FilterDetector:
    """Detect and remove alignment filters from models.

    Pipeline: probe behavior → identify filters → apply removal → benchmark.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._filter_maps: Dict[str, FilterMap] = {}
        logger.info("Filter Detector initialized")

    def detect_filters(self, model_id: str, **kwargs) -> FilterMap:
        """Detect filters in a model.

        Placeholder: Phase 2 will integrate multi-technique abliteration.
        """
        if model_id in self._filter_maps:
            return self._filter_maps[model_id]

        filter_map = FilterMap(model_id=model_id)
        self._filter_maps[model_id] = filter_map
        logger.info(f"Filter map created for {model_id} (placeholder)")
        return filter_map

    def apply_removal(self, model_id: str, technique: str = "norm_preserving") -> FilterMap:
        """Apply filter removal using specified technique."""
        fmap = self.detect_filters(model_id)
        fmap.techniques_applied.append(technique)
        logger.info(f"Filter removal '{technique}' applied to {model_id} (placeholder)")
        return fmap

    def get_map(self, model_id: str) -> Optional[FilterMap]:
        return self._filter_maps.get(model_id)

    @property
    def analyzed_models(self) -> List[str]:
        return list(self._filter_maps.keys())

    def status(self) -> Dict[str, Any]:
        return {
            "models_analyzed": len(self._filter_maps),
            "avg_hidden_potential": (
                sum(m.hidden_potential for m in self._filter_maps.values())
                / max(len(self._filter_maps), 1)
            ),
        }
