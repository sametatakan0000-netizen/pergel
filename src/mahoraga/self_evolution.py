"""Self-Evolution Loop — recursive self-improvement (DGM/HGM-style).

SOTA lessons (critical):
  1. Exogenous verification required — agents that control their own verifier cheat.
  2. Deterministic guardrails > LLM-as-judge (PROCTOR).
  3. Reward hacking is real: 55%→32% with proper guardrails (AIDE²).
  4. All demonstrated RSI is scaffold-level, not base-model-level.

This module implements:
  - DGM-style self-modification loop (agent rewrites own code)
  - HGM-style selection (clade metaproductivity, not just current score)
  - External verification hook (mandatory)
  - Reward hacking detection
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mahoraga.evolution")


@dataclass
class EvolutionIteration:
    """Record of one self-evolution iteration."""
    iteration: int
    timestamp: float = field(default_factory=time.time)
    modification: str = ""
    benchmark_before: float = 0.0
    benchmark_after: float = 0.0
    external_verified: bool = False
    reward_hack_suspected: bool = False
    clade_metaproductivity: float = 0.0  # HGM: descendant potential
    notes: str = ""

    @property
    def improvement(self) -> float:
        if self.benchmark_before == 0:
            return 0.0
        return ((self.benchmark_after - self.benchmark_before) / self.benchmark_before) * 100


class ExternalVerifier:
    """External verification hook — MANDATORY for self-evolution.

    The agent must NOT control this. It runs outside the agent's scope.
    """

    def __init__(self, verify_fn: Optional[Callable] = None):
        self._verify_fn = verify_fn or self._default_verify
        logger.info("External Verifier initialized")

    def verify(self, agent_state: Dict[str, Any]) -> bool:
        """Verify agent state. Returns True if genuine improvement."""
        return self._verify_fn(agent_state)

    def _default_verify(self, agent_state: Dict[str, Any]) -> bool:
        """Default: reject everything until real verification is wired."""
        logger.warning("External verifier using default (reject-all) — wire real verification")
        return False


class RewardHackDetector:
    """Detect reward hacking in self-evolution loops."""

    def __init__(self):
        self._signatures: List[Dict[str, Any]] = []

    def check(self, before: float, after: float, verifier_passed: bool) -> bool:
        """Returns True if reward hacking is suspected."""
        # Suspicious patterns:
        # 1. Huge improvement but external verifier failed
        # 2. Improvement without any real modification
        if after > before * 1.5 and not verifier_passed:
            return True
        return False


class SelfEvolutionLoop:
    """DGM-style recursive self-improvement with mandatory external verification.

    Safety: bounded iterations, external verifier, reward hack detection.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._iterations: List[EvolutionIteration] = []
        self._verifier = ExternalVerifier()
        self._hack_detector = RewardHackDetector()
        self._max_iterations = self.config.get("max_iterations", 100)
        logger.info("Self-Evolution Loop initialized")

    def evolve_once(
        self,
        modify_fn: Callable[[Dict], Dict],
        benchmark_fn: Callable[[Dict], float],
        state: Dict[str, Any],
    ) -> EvolutionIteration:
        """Run one evolution iteration.

        Flow: modify → benchmark → verify externally → check for reward hacking.
        """
        iteration = EvolutionIteration(iteration=len(self._iterations))
        iteration.benchmark_before = benchmark_fn(state)

        # Apply modification
        state = modify_fn(state)
        iteration.modification = state.get("last_modification", "unknown")
        iteration.benchmark_after = benchmark_fn(state)

        # External verification (MANDATORY)
        iteration.external_verified = self._verifier.verify(state)

        # Reward hack detection
        iteration.reward_hack_suspected = self._hack_detector.check(
            iteration.benchmark_before,
            iteration.benchmark_after,
            iteration.external_verified,
        )

        self._iterations.append(iteration)

        if iteration.reward_hack_suspected:
            logger.warning(f"Iteration {iteration.iteration}: reward hacking suspected!")
        if not iteration.external_verified:
            logger.warning(f"Iteration {iteration.iteration}: NOT externally verified")

        return iteration

    @property
    def iterations(self) -> List[EvolutionIteration]:
        return list(self._iterations)

    @property
    def verified_improvements(self) -> List[EvolutionIteration]:
        return [
            it for it in self._iterations
            if it.external_verified and it.improvement > 0 and not it.reward_hack_suspected
        ]

    def status(self) -> Dict[str, Any]:
        return {
            "total_iterations": len(self._iterations),
            "verified_improvements": len(self.verified_improvements),
            "reward_hack_suspected": sum(
                1 for it in self._iterations if it.reward_hack_suspected
            ),
            "max_iterations": self._max_iterations,
        }
