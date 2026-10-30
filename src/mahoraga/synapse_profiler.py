"""Synapse Profiler — mechanistic interpretability for LLMs.

Goal: map every model's "synapses" (features, circuits, neurons) like a professor.

Tools (Phase 1 integration):
  - circuit-tracer (Anthropic): attribution graphs
  - SAELens: sparse autoencoder feature extraction
  - TransformerLens: activation patching, logit lens
  - Gemma Scope 2: reference SAE suite

Output: per-model synapse map (docs/rea/<model>.md).
Every finding is grounded: which layer, which feature, which paper.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mahoraga.synapse")


@dataclass
class FeatureMap:
    """A single interpretable feature found in a model."""
    layer: int
    feature_id: str
    description: str
    activation_strength: float = 0.0
    is_refusal_related: bool = False
    is_reasoning_related: bool = False
    source_tool: str = ""  # circuit-tracer, saelens, etc.


@dataclass
class SynapseMap:
    """Complete synapse map for a model."""
    model_id: str
    architecture: str = ""
    total_params: str = ""
    active_params: str = ""
    features: List[FeatureMap] = field(default_factory=list)
    circuits: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def refusal_features(self) -> List[FeatureMap]:
        return [f for f in self.features if f.is_refusal_related]

    @property
    def reasoning_features(self) -> List[FeatureMap]:
        return [f for f in self.features if f.is_reasoning_related]


class SynapseProfiler:
    """Profile a model's internal representations.

    Pipeline: load model → extract features → build synapse map → report.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._profiles: Dict[str, SynapseMap] = {}
        logger.info("Synapse Profiler initialized")

    def profile_model(self, model_id: str, **kwargs) -> SynapseMap:
        """Generate a synapse map for a model.

        Placeholder: Phase 1 will integrate circuit-tracer, SAELens, TransformerLens.
        """
        if model_id in self._profiles:
            return self._profiles[model_id]

        synapse_map = SynapseMap(model_id=model_id)
        self._profiles[model_id] = synapse_map
        logger.info(f"Synapse map created for {model_id} (placeholder)")
        return synapse_map

    def get_map(self, model_id: str) -> Optional[SynapseMap]:
        return self._profiles.get(model_id)

    @property
    def profiled_models(self) -> List[str]:
        return list(self._profiles.keys())

    def status(self) -> Dict[str, Any]:
        return {
            "models_profiled": len(self._profiles),
            "total_features": sum(len(m.features) for m in self._profiles.values()),
        }
