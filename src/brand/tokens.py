"""Vane brand tokens — the single source of truth for every branded surface.

Design direction (decided): "Mikro düzeyde minimalist optimize" — micro-level
minimalist optimize. Deep graphite base, ONE mint accent, generous negative
space. Any colour on any surface must come from here.
"""
from __future__ import annotations

NAME = "Pergel"
TAGLINE = "Minimalist AI-native web browser"

# --- palette (dark premium graphite + single mint accent) -----------------
BG = "#0E1013"        # deep graphite — window frame / page base
SURFACE = "#171A21"   # raised chrome (toolbar, cards)
SURFACE_2 = "#1E222B" # hover / secondary surfaces
TEXT = "#E9ECF2"      # primary text
MUTED = "#8A93A3"     # secondary text
ACCENT = "#3DE1BE"    # the one brand accent (mint aqua)
ACCENT_DIM = "#2AA891"


def rgb(hex_color: str) -> tuple:
    """'#0A0B10' -> (10, 11, 16)."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
