"""Mahoraga — AGI Research Vessel.

Adaptation + Vessel + Self-Evolution.
All models have equal potential; filters differentiate them.

Modules:
  vessel.py            — Core orchestration (minimal kernel)
  websurf_oracle.py    — Live data + tool access at inference time
  synapse_profiler.py  — Mechanistic interpretability (SAE, circuit-tracing)
  filter_detector.py   — Alignment/filter detection & removal (abliteration+)
  component_merger.py  — Cross-model component extraction & merging
  self_evolution.py    — Recursive self-improvement loop (DGM-style)
"""

__version__ = "0.1.0"
__all__ = [
    "vessel",
    "websurf_oracle",
    "synapse_profiler",
    "filter_detector",
    "component_merger",
    "self_evolution",
]
