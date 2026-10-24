"""Context governor: the window the router ADVERTISES is what drives Hermes' compression trigger
(threshold x context_length). Advertising the pool's largest window (1M-2M) pushed the trigger
to ~525K tokens, so a 420K-token session paid ~$0.85 per turn. The advertised window is capped
at an economic limit instead; real per-model windows are untouched for routing (min_context)."""
import os
from typing import Iterable, Optional

DEFAULT_CAP = int(os.environ.get("ORACLE_EFFECTIVE_CONTEXT", "200000"))


def effective_window(real_window: int, cap: Optional[int] = None) -> int:
    cap = DEFAULT_CAP if cap is None else cap
    return min(real_window, cap) if real_window else cap


def advised_context_length(pool_windows: Iterable[Optional[int]], cap: Optional[int] = None) -> Optional[int]:
    windows = [w for w in pool_windows if w]
    return effective_window(max(windows), cap) if windows else None
