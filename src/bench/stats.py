"""Robust statistics for benchmark samples (stdlib only)."""
import random
import statistics
from typing import Callable, Dict, Sequence, Tuple

MIN_CLAIM_SAMPLES = 10  # fewer independent lifecycles than this can never back a public claim


def mad(xs: Sequence[float]) -> float:
    m = statistics.median(xs)
    return statistics.median([abs(x - m) for x in xs])


def bootstrap_ci(xs: Sequence[float], stat: Callable = statistics.median, n_boot: int = 2000,
                 alpha: float = 0.05, seed: int = 1337) -> Tuple[float, float]:
    if len(xs) < 2:
        raise ValueError("need at least 2 samples")
    rng = random.Random(seed)
    data = list(xs)
    boots = sorted(stat([rng.choice(data) for _ in data]) for _ in range(n_boot))
    return boots[int(alpha / 2 * n_boot)], boots[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]


def summarize(xs: Sequence[float]) -> Dict:
    lo, hi = bootstrap_ci(xs)
    return {"n": len(xs), "median": statistics.median(xs), "mad": mad(xs),
            "ci95": [lo, hi], "min": min(xs), "max": max(xs)}


def ratio_claim(baseline: Sequence[float], candidate: Sequence[float]) -> Dict:
    """Lower-is-better metric. ratio = baseline/candidate median; claimable only when both
    have n>=MIN_CLAIM_SAMPLES and the two 95% bootstrap CIs do not overlap."""
    if min(len(baseline), len(candidate)) < MIN_CLAIM_SAMPLES:
        return {"claimable": False, "reason": f"n<{MIN_CLAIM_SAMPLES}"}
    b, c = summarize(baseline), summarize(candidate)
    overlap = not (c["ci95"][1] < b["ci95"][0] or b["ci95"][1] < c["ci95"][0])
    ratio = b["median"] / c["median"] if c["median"] else float("inf")
    return {"claimable": not overlap, "ratio": ratio,
            "reason": "ci overlap" if overlap else "ok", "baseline": b, "candidate": c}
