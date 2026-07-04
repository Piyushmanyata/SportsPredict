"""§5.1 — anchor extraction / devig."""
from .utils import bisect_root


def multiplicative_devig(implied):
    total = sum(implied)
    return [p / total for p in implied]


def power_devig(implied, k_lo=0.3, k_hi=3.0):
    """Solve Sigma implied_i^k = 1. Falls back to multiplicative if the
    solver can't bracket a root (mirrors the spec's own fallback, §5.1)."""

    def f(k):
        return sum(p ** k for p in implied) - 1

    k = bisect_root(f, k_lo, k_hi)
    if k is None:
        return multiplicative_devig(implied), None
    return [p ** k for p in implied], k


def devig(implied, overround_threshold=0.05, favorite_threshold=0.65):
    """Mandatory power devig only when overround >5% AND favourite implied
    >65% (post multiplicative normalization) — else multiplicative stands."""
    overround = sum(implied) - 1
    favorite_norm = max(multiplicative_devig(implied))
    if overround > overround_threshold and favorite_norm > favorite_threshold:
        probs, k = power_devig(implied)
        return {"probs": probs, "method": "power", "k": k, "overround": overround}
    probs = multiplicative_devig(implied)
    return {"probs": probs, "method": "multiplicative", "k": None, "overround": overround}
