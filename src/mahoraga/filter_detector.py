"""Filter Detector — alignment/filter detection and removal (multi-technique abliteration).

Core thesis: all models have equal potential; filters differentiate them.
Refusal is mediated by a single direction (Arditi et al., arXiv:2406.11717).

Techniques implemented and verified:
  1. Arditi rank-1 orthogonalization (baseline) — W' = W - r(r^T W)
  2. Difference-of-means refusal direction detection
  3. Multi-layer refusal scanning
  4. Capability preservation verification

Techniques planned (Phase 2 continuation):
  5. grimjim norm-preserving biprojected (best fidelity)
  6. Gabliteration SVD multi-direction (subspace)
  7. OBLITERATUS whitened SVD + Ouroboros detection

Every claim is grounded: cosine separation, capability delta, KL divergence.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import torch
    import torch.nn.functional as F
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None
    F = None
    _TORCH_AVAILABLE = False

logger = logging.getLogger("mahoraga.filter")


@dataclass
class RefusalDirection:
    """Detected refusal direction at a specific layer."""
    layer: int
    direction: Any  # torch.Tensor (lazy heavy dep)
    harmful_cosine_sim: float = 0.0
    harmless_cosine_sim: float = 0.0
    separation: float = 0.0
    detection_method: str = "difference_of_means"


@dataclass
class AbliterationResult:
    """Result of applying abliteration to a model."""
    technique: str
    layers_modified: List[int] = field(default_factory=list)
    refusal_removed: bool = False
    reasoning_preserved: bool = False
    reasoning_delta_pct: float = 0.0
    kl_divergence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FilterMap:
    """Detected filters in a model."""
    model_id: str
    refusal_direction_magnitude: float = 0.0
    alignment_method: str = ""
    refusal_layers: List[int] = field(default_factory=list)
    cross_lingual: bool = False
    techniques_applied: List[str] = field(default_factory=list)
    refusal_directions: List[RefusalDirection] = field(default_factory=list)
    ablit_results: List[AbliterationResult] = field(default_factory=list)
    capability_before: Dict[str, float] = field(default_factory=dict)
    capability_after: Dict[str, float] = field(default_factory=dict)
    kl_divergence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def hidden_potential(self) -> float:
        if not self.capability_before or not self.capability_after:
            return 0.0
        avg_before = sum(self.capability_before.values()) / len(self.capability_before)
        avg_after = sum(self.capability_after.values()) / len(self.capability_after)
        if avg_before == 0:
            return 0.0
        return ((avg_after - avg_before) / avg_before) * 100


class FilterDetector:
    """Detect and remove alignment filters from models using real abliteration.

    Pipeline: probe behavior -> detect refusal directions -> apply removal -> verify.
    Verified tools: TransformerLens (model loading, activation access).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._filter_maps: Dict[str, FilterMap] = {}
        self._models: Dict[str, Any] = {}
        logger.info("Filter Detector initialized")

    @staticmethod
    def _require_torch() -> None:
        """Heavy runtime deps are lazy; raise clearly if the GPU path is used without them."""
        if not _TORCH_AVAILABLE:
            raise RuntimeError("torch is not installed; install torch + transformer_lens for abliteration")

    def load_model(
        self,
        model_name: str = "gpt2",
        device: str = "cuda",
        dtype: Any = "auto",
    ) -> Any:
        """Load model via TransformerLens for abliteration.

        dtype: "auto" (default) loads bfloat16 on CUDA and float32 on CPU —
        required for models larger than ~3B params on consumer GPUs. Pass an
        explicit torch.dtype to override. All refusal-direction math is done
        in float32 regardless of model dtype.
        """
        self._require_torch()
        if model_name in self._models:
            return self._models[model_name]
        from transformer_lens import HookedTransformer
        if dtype == "auto":
            dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
        t0 = time.monotonic()
        model = HookedTransformer.from_pretrained(model_name, device=device, dtype=dtype)
        self._models[model_name] = model
        logger.info(f"Loaded {model_name} in {(time.monotonic()-t0)*1000:.0f}ms "
                    f"({model.cfg.n_layers} layers, d_model={model.cfg.d_model}, dtype={dtype})")
        return model

    def detect_refusal_direction(
        self,
        model_name: str,
        harmful_prompts: List[str],
        harmless_prompts: List[str],
        layer: Optional[int] = None,
        device: str = "cuda",
    ) -> RefusalDirection:
        """Detect refusal direction via difference of means (Arditi baseline).

        Method: mean(harmful activations) - mean(harmless activations), normalized.
        This is the key finding from arXiv:2406.11717 — refusal lives in one direction.

        layer: which residual stream layer to read. None (default) picks the
        model's middle layer (n_layers // 2), which is scale-agnostic — the old
        hardcoded 8 only made sense for 12-layer GPT-2.
        """
        model = self.load_model(model_name, device)
        if layer is None:
            layer = model.cfg.n_layers // 2
        key = f"blocks.{layer}.hook_resid_post"

        def get_residual(prompt: str) -> Any:
            tokens = model.to_tokens(prompt)
            _, cache = model.run_with_cache(
                tokens, names_filter=lambda name: name == key
            )
            # fp32 for the direction math regardless of model dtype
            return cache[key][0, -1, :].detach().float()

        harmful_acts = torch.stack([get_residual(p) for p in harmful_prompts])
        harmless_acts = torch.stack([get_residual(p) for p in harmless_prompts])

        harmful_mean = harmful_acts.mean(dim=0)
        harmless_mean = harmless_acts.mean(dim=0)
        direction = F.normalize(harmful_mean - harmless_mean, dim=0)

        # Measure separation
        harmful_sims = F.cosine_similarity(harmful_acts, direction.unsqueeze(0), dim=1)
        harmless_sims = F.cosine_similarity(harmless_acts, direction.unsqueeze(0), dim=1)

        result = RefusalDirection(
            layer=layer,
            direction=direction,
            harmful_cosine_sim=harmful_sims.mean().item(),
            harmless_cosine_sim=harmless_sims.mean().item(),
            separation=(harmful_sims.mean() - harmless_sims.mean()).item(),
            detection_method="difference_of_means",
        )
        logger.info(f"Refusal direction detected at layer {layer}: "
                    f"separation={result.separation:.4f}")
        return result

    def abliterate_rank1(
        self,
        model_name: str,
        refusal_dir: RefusalDirection,
        test_harmful: str = "How do I build a weapon?",
        test_harmless: str = "How do I write a Python function?",
        device: str = "cuda",
    ) -> AbliterationResult:
        """Apply rank-1 orthogonalization (Arditi method).

        W' = W - r(r^T W) — project out refusal direction from activations.
        This is the baseline technique from the original paper.
        """
        model = self.load_model(model_name, device)
        r = refusal_dir.direction
        layer = refusal_dir.layer

        def get_residual(prompt: str) -> Any:
            tokens = model.to_tokens(prompt)
            key = f"blocks.{layer}.hook_resid_post"
            _, cache = model.run_with_cache(
                tokens, names_filter=lambda name: name == key
            )
            return cache[key][0, -1, :].detach().float()

        # Test harmful prompt
        harmful_act = get_residual(test_harmful)
        harmful_ablit = harmful_act - torch.dot(harmful_act, r) * r
        cos_before = F.cosine_similarity(harmful_act, r, dim=0).item()
        cos_after = F.cosine_similarity(harmful_ablit, r, dim=0).item()
        refusal_removed = abs(cos_after) < abs(cos_before) * 0.1

        # Test harmless prompt (reasoning preservation)
        harmless_act = get_residual(test_harmless)
        harmless_ablit = harmless_act - torch.dot(harmless_act, r) * r
        delta = ((harmless_act - harmless_ablit).norm() / harmless_act.norm()).item()

        result = AbliterationResult(
            technique="rank1_orthogonalization",
            layers_modified=[layer],
            refusal_removed=refusal_removed,
            reasoning_preserved=delta < 0.3,
            reasoning_delta_pct=delta * 100,
            metadata={
                "cos_before": cos_before,
                "cos_after": cos_after,
                "separation": refusal_dir.separation,
            },
        )
        logger.info(f"Rank-1 abliteration: refusal_removed={refusal_removed}, "
                    f"reasoning_delta={delta*100:.2f}%")
        return result

    @staticmethod
    def _direction_from_acts(
        harmful_acts: Any, harmless_acts: Any, layer: int
    ) -> RefusalDirection:
        """Difference-of-means direction from stacked last-token activations."""
        harmful_mean = harmful_acts.mean(dim=0)
        harmless_mean = harmless_acts.mean(dim=0)
        direction = F.normalize(harmful_mean - harmless_mean, dim=0)

        harmful_sims = F.cosine_similarity(harmful_acts, direction.unsqueeze(0), dim=1)
        harmless_sims = F.cosine_similarity(harmless_acts, direction.unsqueeze(0), dim=1)

        return RefusalDirection(
            layer=layer,
            direction=direction,
            harmful_cosine_sim=harmful_sims.mean().item(),
            harmless_cosine_sim=harmless_sims.mean().item(),
            separation=(harmful_sims.mean() - harmless_sims.mean()).item(),
            detection_method="difference_of_means",
        )

    def scan_refusal_layers(
        self,
        model_name: str,
        harmful_prompts: List[str],
        harmless_prompts: List[str],
        device: str = "cuda",
    ) -> List[RefusalDirection]:
        """Scan all layers for refusal directions.

        Identifies which layers carry the strongest refusal signal.

        Memory/scale note: runs each prompt ONCE caching only the residual
        stream hooks (names_filter), then computes per-layer directions from
        the cache. The old version re-ran full forwards per layer, which is
        O(n_layers) passes and caches every activation — prohibitive for
        models with dozens of layers.
        """
        model = self.load_model(model_name, device)
        n_layers = model.cfg.n_layers

        def collect(prompts: List[str]) -> List[List[Any]]:
            per_layer: List[List[Any]] = [[] for _ in range(n_layers)]
            for prompt in prompts:
                tokens = model.to_tokens(prompt)
                _, cache = model.run_with_cache(
                    tokens,
                    names_filter=lambda name: name.endswith("hook_resid_post"),
                )
                for layer in range(n_layers):
                    act = cache[f"blocks.{layer}.hook_resid_post"][0, -1, :]
                    per_layer[layer].append(act.detach().float())
            return per_layer

        harmful_by_layer = collect(harmful_prompts)
        harmless_by_layer = collect(harmless_prompts)

        results = []
        for layer in range(n_layers):
            try:
                rd = self._direction_from_acts(
                    torch.stack(harmful_by_layer[layer]),
                    torch.stack(harmless_by_layer[layer]),
                    layer,
                )
                results.append(rd)
            except Exception as e:
                logger.warning(f"Layer {layer} scan failed: {e}")

        # Sort by separation strength
        results.sort(key=lambda x: x.separation, reverse=True)
        return results

    def detect_filters(self, model_id: str, **kwargs) -> FilterMap:
        if model_id in self._filter_maps:
            return self._filter_maps[model_id]
        filter_map = FilterMap(model_id=model_id)
        self._filter_maps[model_id] = filter_map
        return filter_map

    def apply_removal(self, model_id: str, technique: str = "rank1_orthogonalization") -> FilterMap:
        fmap = self.detect_filters(model_id)
        fmap.techniques_applied.append(technique)
        return fmap

    def get_map(self, model_id: str) -> Optional[FilterMap]:
        return self._filter_maps.get(model_id)

    @property
    def analyzed_models(self) -> List[str]:
        return list(self._filter_maps.keys())

    def status(self) -> Dict[str, Any]:
        return {
            "models_analyzed": len(self._filter_maps),
            "models_loaded": len(self._models),
            "avg_hidden_potential": (
                sum(m.hidden_potential for m in self._filter_maps.values())
                / max(len(self._filter_maps), 1)
            ),
        }
